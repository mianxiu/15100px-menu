"""Scoped Photoshop hotkeys and a separate C++ Dear ImGui menu process."""
import ctypes
from ctypes import wintypes as W
import logging
import os
from pathlib import Path
import subprocess
import threading
import time
import secrets
import json
from functools import wraps
from .window_icons import WindowIcons
from .settings import DEFAULTS, chord, ALIASES, MODIFIERS
from .paths import ROOT, runtime_dir, overlay_command
from .panel_context import PanelContext, panel_flags

TITLE = "Photoshop Menu - Actions"


def window_transition(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        with self.window_lock:
            return method(self, *args, **kwargs)
    return call


def shape_editor_allowed(panel, shape, hold, context=None):
    context=context or {}
    from .shape_paint import editor_matches
    return bool(hold and shape.get('available') is True and panel.get('kind')=='layers' and not panel.get('input_focused')
                and editor_matches(shape,context)
                and not context.get('locked') and not context.get('background'))


def process_parent(pid):
    """Windows venv python.exe can launch a second Python process."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    class Entry(ctypes.Structure):
        _fields_ = [("size", W.DWORD), ("usage", W.DWORD), ("pid", W.DWORD),
                    ("heap", ctypes.c_size_t), ("module", W.DWORD), ("threads", W.DWORD),
                    ("parent", W.DWORD), ("priority", W.LONG), ("flags", W.DWORD), ("name", W.WCHAR*260)]
    kernel.CreateToolhelp32Snapshot.argtypes, kernel.CreateToolhelp32Snapshot.restype = [W.DWORD,W.DWORD], W.HANDLE
    kernel.Process32FirstW.argtypes, kernel.Process32FirstW.restype = [W.HANDLE,ctypes.POINTER(Entry)], W.BOOL
    kernel.Process32NextW.argtypes, kernel.Process32NextW.restype = [W.HANDLE,ctypes.POINTER(Entry)], W.BOOL
    kernel.CloseHandle.argtypes, kernel.CloseHandle.restype = [W.HANDLE], W.BOOL
    snapshot = kernel.CreateToolhelp32Snapshot(2,0)
    if snapshot == ctypes.c_void_p(-1).value:
        return None
    try:
        entry = Entry()
        entry.size = ctypes.sizeof(entry)
        more = kernel.Process32FirstW(snapshot,ctypes.byref(entry))
        while more:
            if entry.pid == pid:
                return entry.parent
            more = kernel.Process32NextW(snapshot,ctypes.byref(entry))
        return None
    finally:
        kernel.CloseHandle(snapshot)


class KeyState:
    def __init__(self, shortcuts=None):
        self.held = set()
        self.consumed = set()
        self.pending_toggle = None
        self.toggle_used = False
        self.configure(shortcuts or DEFAULTS["shortcuts"])

    def configure(self, shortcuts):
        if getattr(self, "shortcuts", None) == shortcuts:
            return
        self.shortcuts = dict(shortcuts)
        self.bindings = {name: chord(value) for name, value in shortcuts.items()}

    def event(self, key, down, scoped):
        key = ALIASES.get(key, key)
        repeated = key in self.held
        self.held.add(key) if down else self.held.discard(key)
        if not down and key in self.consumed:
            self.consumed.discard(key)
            if key == self.pending_toggle:
                action = "hold_release" if scoped and not self.toggle_used else "hold_cancel"
                self.pending_toggle = None
                return True, action
            return True, None
        if not scoped or not down:
            return bool(down and key in self.consumed), None
        matches = [(name, keys) for name, keys in self.bindings.items()
                   if keys and keys[-1] == key and set(keys).issubset(self.held)
                   and (self.held & MODIFIERS) == (set(keys) & MODIFIERS)]
        if matches:
            name, _ = max(matches, key=lambda item: len(item[1]))
            self.consumed.add(key)
            if name == "toggle":
                if not repeated:
                    self.pending_toggle, self.toggle_used = key, False
                    return True, "hold_begin"
                return True, None
            if self.pending_toggle is not None:
                self.toggle_used = True
            return True, None if repeated else name
        # Withhold Tab only if it is a configured combination prefix.
        if key == 9 and not self.held & MODIFIERS and any(9 in keys[:-1] for keys in self.bindings.values()):
            self.consumed.add(key)
            return True, None
        if self.pending_toggle is not None and key != self.pending_toggle:
            self.toggle_used = True
        return key in self.consumed, None


def panel_bounds(ps_rect, work_rect, cursor, width, height):
    left, top = max(ps_rect[0], work_rect[0]), max(ps_rect[1], work_rect[1])
    right, bottom = min(ps_rect[2], work_rect[2]), min(ps_rect[3], work_rect[3])
    if right <= left or bottom <= top:
        raise ValueError("Photoshop 窗口没有可用的显示区域")
    width, height = min(width, right-left), min(height, bottom-top)
    return max(left, min(cursor[0], right-width)), max(top, min(cursor[1], bottom-height)), width, height


def pie_bounds(ps_rect, work_rect, cursor, scale, home=False, color_editor=False):
    width, height = round((920 if color_editor else 820 if home else 620)*scale), round((620 if color_editor else 440 if home else 500)*scale)
    # The color editor is left of the radial controls. Reserve asymmetric
    # space instead of forcing the mouse to the middle of the entire window.
    anchor = round(650*scale) if color_editor else round(270*scale) if home else width//2
    return panel_bounds(ps_rect, work_rect,
                        (cursor[0]-anchor, cursor[1]-height//2), width, height)


def show_popup(gui, hwnd, owner, bounds):
    """Showing an iconified GLFW viewport does not restore its render surface."""
    import win32con as c
    gui.SetWindowLong(hwnd, c.GWL_HWNDPARENT, owner)
    if gui.IsIconic(hwnd):
        gui.ShowWindow(hwnd, c.SW_RESTORE)
    gui.SetWindowPos(hwnd, c.HWND_TOP, *bounds, c.SWP_SHOWWINDOW)


class Desktop:
    def __init__(self, url, notify, settings=None, runtime=None):
        self.url, self.notify = url, notify
        self.settings = settings or dict(DEFAULTS)
        self.runtime = Path(runtime) if runtime else runtime_dir()
        self.target = self.hwnd = None
        self.visible = False
        self.hold_active = False
        self.restore_pending = False
        self.menu_epoch = 0
        self.menu_context_requester=None
        self.menu_context_pending=None
        self.menu_context_active=None
        self.menu_context_canceller=None
        self.document_caption = None
        self.caption_window = 0
        self.stop = threading.Event()
        self.icons = None
        self.process = None
        self.token = secrets.token_hex(24)
        self.message = "桌面功能未启动"
        self.native = None
        self.native_lock = threading.Lock()
        self.native_payload = None
        self.menu_lock = threading.Lock()
        self.menu_thread = None
        self.menu_ready = threading.Event()
        self.window_lock = threading.RLock()
        self.panel_context = None
        self.layer_context_provider=None
        self.layer_monitor=None
        self.layer_context={}
        self.menu_layer_context=None

    def start(self):
        import win32gui
        self.gui = win32gui
        self.panel_context = PanelContext(win32gui)
        self.icons = WindowIcons()
        self.ready = threading.Event()
        host = ROOT / "native/HotkeyHost.exe"
        if not host.is_file():
            raise RuntimeError("缺少 Windows 热键组件，请运行 tools/build-hotkey-host.ps1")
        self._spawn_native()
        self.thread = threading.Thread(target=self._native_events, name="photoshop-hotkeys", daemon=True)
        self.thread.start()
        self.ready.wait(3)
        if not self.ready.is_set() or self.native.poll() is not None:
            raise RuntimeError("Windows 热键组件未能启动，请查看服务日志")
        self.monitor = threading.Thread(target=self._monitor, name="photoshop-window", daemon=True)
        self.monitor.start()
        if self.layer_context_provider:
            self.layer_monitor=threading.Thread(target=self._monitor_layer_context,name='photoshop-layer-cache',daemon=True)
            self.layer_monitor.start()
        self._launch_overlay()

    def _spawn_native(self):
        with self.native_lock:
            if self.stop.is_set():
                return
            self.native = subprocess.Popen([str(ROOT / "native/HotkeyHost.exe"), "--parent", str(os.getpid())], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                bufsize=1, creationflags=0x08000000)
            self.native_payload = None
        self._native_config()

    def _native_config(self):
        if not self.native or self.native.poll() is not None:
            return
        payload = json.dumps({"enabled": self.settings["enabled"],
            "text_input": bool(self.panel_context and (self.panel_context.current['kind'] == 'text' or self.panel_context.current.get('input_focused'))),
            "color_editor": bool(self.visible and getattr(self,'color_editor_active',False)),
            "diagnostic_trace": bool(getattr(self,"diagnostic_trace",False)),
            "remote_compatibility": self.settings.get("remote_compatibility",False),
            "right_click_open": False,
            "hwnd": self.hwnd or 0, "visible": self.visible,
            "bindings": {name: list(chord(value)) for name,value in self.settings["shortcuts"].items()}})
        with self.native_lock:
            if self.stop.is_set() or not self.native or self.native.poll() is not None:
                return
            if payload != self.native_payload:
                try:
                    self.native.stdin.write(payload + "\n")
                    self.native.stdin.flush()
                    self.native_payload = payload
                except (OSError, ValueError):
                    logging.exception("Native hotkey settings failed")

    def _native_events(self):
        while not self.stop.is_set():
            self._read_native_events()
            self.ready.clear()
            if self.stop.is_set():
                break
            self.message = "热键进程已停止，正在自动恢复"
            logging.error("Native hotkey process stopped; restarting")
            old = self.native
            if old.poll() is None:
                old.terminate()
                old.wait(3)
            old.stdin.close()
            old.stdout.close()
            delay = 1
            while not self.stop.wait(delay):
                try:
                    self._spawn_native()
                    break
                except OSError:
                    logging.exception("Native hotkey restart failed")
                    delay = min(delay * 2, 30)

    def _read_native_events(self):
        try:
            for line in self.native.stdout:
                event = json.loads(line)
                if event.get("type") == "ready":
                    self.message = "C++ / Win32 原生热键 · 仅 Photoshop 前台生效"
                    self.ready.set()
                elif event.get('type') == 'panel.click':
                    if self.panel_context:
                        self.panel_context.record_click(event['hwnd'], event['root'])
                elif event.get("type") == "action":
                    logging.info('Native hook action: %s cursor=%s', event['action'], event.get('cursor'))
                    self.notify({'action':event['action'],'cursor':event['cursor']} if 'cursor' in event else event['action'])
                elif event.get('type') == 'trigger.trace':
                    from collections import deque
                    if not hasattr(self,'trigger_events'):self.trigger_events=deque(maxlen=64)
                    if getattr(self,'diagnostic_trace',False):self.trigger_events.append(event)
                    logging.info('Configured menu trigger decision: %s',event)
                elif event.get('type') == 'caps.trace':
                    logging.info('CapsLock hook decision: %s', event)
                elif event.get('type') == 'hook.health':
                    logging.info('Native hook health: %s', event)
                elif event.get('type') == 'caps.state':
                    logging.info('CapsLock system state: %s', event)
                elif event.get('type') == 'activation.trace':
                    logging.info('Photoshop activation click: %s', event)
                elif event.get('type') == 'activation.foreground':
                    self.activation_snapshot=event
                    logging.info('Photoshop activation foreground: %s', event)
                elif event.get("type") == "configured":
                    logging.debug("Native hotkey settings acknowledged")
                else:
                    logging.error("Native hotkey error: %s", event)
        except Exception:
            logging.exception("Native hotkey event stream failed")

    def _launch_overlay(self):
        if self.process and self.process.poll() is None:
            return
        self.hwnd = None
        self.menu_ready.clear()
        self.runtime.mkdir(parents=True, exist_ok=True)
        with (self.runtime / "overlay.log").open("a", encoding="utf-8") as log:
            self.process = subprocess.Popen(overlay_command(self.url, self.token, self.runtime),
                                            cwd=str(ROOT), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log,
                                            text=True, encoding='utf-8', bufsize=1,
                                            creationflags=0x08000000)
        self.menu_thread = threading.Thread(target=self._menu_events, args=(self.process,), name='imgui-menu', daemon=True)
        self.menu_thread.start()
        if not self.menu_ready.wait(5):
            raise RuntimeError('Dear ImGui 菜单未就绪，请查看 overlay.log')

    def _menu_events(self, process):
        try:
            for line in process.stdout:
                event = json.loads(line)
                if event.get('type') == 'ready':
                    self.graphics=event.get('graphics',{})
                    self.attach(event['hwnd'], event['pid'], self.token)
                    self.menu_ready.set()
                elif event.get('type') == 'graphics':
                    self.graphics=event.get('graphics',{})
                    logging.info('Menu graphics: %s',self.graphics)
                elif event.get('type') == 'action':
                    logging.info('Dear ImGui menu action: %s', event['action'])
                    self.notify({'action':event['action'], 'menu_epoch':event.get('session',self.menu_epoch),
                        **({'params':event['params']} if 'params' in event else {})})
                elif event.get('type') == 'selection':
                    logging.info('Menu release decision: %s', event)
        except Exception:
            logging.exception('Dear ImGui menu event stream failed')
        finally:
            if self.process is process:
                self.hwnd, self.visible = None, False
                self.menu_ready.clear()

    def event(self, event):
        if event.get('type') not in ('status', 'operation', 'notice', 'popup.prepare', 'document', 'diagnostic.progress','mask.preview','preview.progress'):
            return
        preview=getattr(self,'mask_preview',None)
        if preview and event.get('type')=='preview.progress' and event.get('epoch')==preview.epoch:
            # A newly opened busy menu observes the same original transaction.
            event={**event,'epoch':self.menu_epoch}
        if preview and preview.epoch==self.menu_epoch and preview.phase=='preview':
            # Only the owning editor remains interactive. Other consumers still
            # receive the real busy/pending state and cannot submit operations.
            if event.get('type')=='status':
                event={**event,'data':{**event['data'],'photoshop':{**event['data']['photoshop'],
                    'busy':False,'uxp_recovery':{},'mask_preview':True}}}
            elif event.get('type')=='operation':event={**event,'busy':False}
        with self.menu_lock:
            if self.process and self.process.poll() is None:
                try:
                    self.process.stdin.write(json.dumps(event, ensure_ascii=False) + '\n')
                    self.process.stdin.flush()
                except (OSError, ValueError):
                    logging.exception('Dear ImGui menu update failed')

    def attach(self, hwnd, pid, token):
        import win32process
        if not self.process or self.process.poll() is not None or token != self.token or type(hwnd) is not int or type(pid) is not int:
            raise ValueError("无效的操作菜单连接")
        if pid != self.process.pid and process_parent(pid) != self.process.pid:
            raise ValueError("操作菜单进程不属于当前后台")
        if not self.gui.IsWindow(hwnd) or win32process.GetWindowThreadProcessId(hwnd)[1] != pid:
            raise ValueError("操作菜单窗口不匹配")
        self.hwnd = hwnd
        self.visible = False
        self.gui.ShowWindow(hwnd, 0)
        self.icons.apply(hwnd)
        self._native_config()

    def _workspace_root(self, hwnd):
        from .photoshop_windows import workspace_root
        return workspace_root(self.gui, hwnd)

    def _is_photoshop(self, hwnd):
        return bool(self._workspace_root(hwnd))

    @window_transition
    def _scope(self):
        if not self.settings["enabled"]:
            return False
        hwnd = self.gui.GetForegroundWindow()
        if self._is_photoshop(hwnd):
            # Floating document windows can be hidden/replaced when PS changes
            # active documents. Keep popup ownership on the stable workspace.
            self.target = self._workspace_root(hwnd)
            self.caption_window = hwnd
            return True
        # Windows can retain our hidden popup as foreground while restoring
        # focus. It still belongs to this PS session, unlike a foreign app.
        owned = self._is_menu_window(hwnd)
        if not owned:
            self.restore_pending = False
        return bool((self.visible or self.restore_pending) and owned and self._is_photoshop(self.target))

    def _is_menu_window(self, hwnd):
        if not hwnd or not self.hwnd or not self.gui.IsWindow(hwnd):
            return False
        if hwnd == self.hwnd:
            return True
        import win32process
        try:
            owner = win32process.GetWindowThreadProcessId(self.hwnd)[1]
            return bool(owner and win32process.GetWindowThreadProcessId(hwnd)[1] == owner)
        except Exception:
            return False

    @window_transition
    def require_action_focus(self, allow_home=False):
        if not self._scope():
            raise RuntimeError("图层操作仅在 Photoshop 或由其唤出的操作菜单中可用")
        if self.panel_context:
            panel = self.panel_context.current if self.visible else self.panel_context.snapshot(self.target)
            if panel['kind'] == 'text' or panel.get('input_focused'):
                raise RuntimeError('正在编辑输入框，请先退出输入再执行图层操作')
            if panel['kind'] == 'home' and not allow_home:
                raise RuntimeError('当前为 Photoshop 首页，请进入文档后执行图层操作')

    @window_transition
    def require_move_context(self, name):
        # The open generic menu deliberately has no reordering operations.
        # Keep standalone PS chords unchanged; block stale menu/native-hook
        # dispatches too, rather than just hiding their buttons.
        if (name in ('moveToTop','moveToBottom','moveUp','moveDown') and self.visible
                and self.panel_context and self.panel_context.current['kind']=='generic'):
            raise RuntimeError('通用操作不提供图层移动，请在图层面板重新打开菜单')

    @window_transition
    def outside_click(self, point):
        if not self.visible or not self.hwnd:
            return False
        rect = self.gui.GetWindowRect(self.hwnd)
        if rect[0] <= point[0] < rect[2] and rect[1] <= point[1] < rect[3]:
            return False
        scoped = self._scope()
        self.visible = False
        self.notify("dismiss")
        return scoped

    def _monitor_layer_context(self):
        # Independent of UIA/focus inspection and the window lock. A slow panel
        # lookup must not leave the next menu with old selection eligibility.
        from .layer_context import unavailable
        while not self.stop.is_set():
            try:
                self.layer_context=self.layer_context_provider()
                self._cancel_closed_menu_context()
                self._resume_completed_menu()
                self._publish_menu_context()
                self._finish_menu_context()
            except Exception:
                self.layer_context=unavailable()
                logging.exception('Layer cache monitor failed')
            if self.stop.wait(.04):break

    def _monitor(self):
        next_icon_refresh = 0
        while not self.stop.wait(.1):
            try:
                with self.window_lock:
                    scoped = self._scope()
                    if scoped:
                        self._refresh_document_name()
                    if not self.visible and self.panel_context and self._is_photoshop(self.gui.GetForegroundWindow()):
                        self.panel_context.snapshot(self.target)
                    if self.hwnd and not self.gui.IsWindow(self.hwnd):
                        self.hwnd, self.visible = None, False
                    if self.hwnd and time.monotonic() >= next_icon_refresh:
                        self.icons.apply(self.hwnd)
                        next_icon_refresh = time.monotonic() + 2
                    if self.visible and (not scoped or not self._is_photoshop(self.target)):
                        logging.info('Menu auto-hide: scoped=%s foreground=%s target=%s target_valid=%s',
                                     scoped, self.gui.GetForegroundWindow(), self.target, self._is_photoshop(self.target))
                        self.hide(restore=False)
                    self._native_config()
            except Exception:
                logging.exception("Window monitor failed")

    @window_transition
    def apply_settings(self, settings):
        self.settings = settings
        if not settings["enabled"]:
            self.hide(restore=False)
        self._native_config()

    def open(self, context=False, hold=False, origin=None):
        u = ctypes.WinDLL("user32", use_last_error=True)
        u.SetThreadDpiAwarenessContext.argtypes, u.SetThreadDpiAwarenessContext.restype = [W.HANDLE], W.HANDLE
        previous = u.SetThreadDpiAwarenessContext(W.HANDLE(-4))
        try:
            return self._open(context, hold, origin) if origin is not None else self._open(context, hold)
        finally:
            if previous:
                u.SetThreadDpiAwarenessContext(previous)

    def _refresh_document_name(self):
        from .document_caption import document_name
        from .photoshop_windows import workspace_root
        try:
            root = workspace_root(self.gui, self.target)
            if not root:
                return
            source = self.caption_window if (self.caption_window and
                workspace_root(self.gui, self.caption_window) == root and
                self.gui.GetClassName(self.caption_window) == 'OWL.DocumentWindow') else root
            name = document_name(self.gui.GetWindowText(source))
            if name and name != self.document_caption:
                self.document_caption = name
                self.event({'type':'document', 'name':name})
        except Exception:
            logging.debug('Document caption unavailable', exc_info=True)

    @window_transition
    def _open(self, context=False, hold=False, origin=None):
        open_started = time.perf_counter()
        import win32api
        import win32con as c
        hwnd = self.gui.GetForegroundWindow()
        foreground = hwnd
        if self.restore_pending and self._is_menu_window(hwnd) and self._is_photoshop(self.target):
            hwnd = self.target
        if not self.settings["enabled"] or not self._is_photoshop(hwnd):
            raise RuntimeError("请先让 Photoshop 主窗口获得焦点，再唤出操作菜单")
        from .photoshop_windows import workspace_root
        cursor = win32api.GetCursorPos()
        root = workspace_root(self.gui, hwnd)
        rect = self.gui.GetWindowRect(root)
        hovered = self.gui.WindowFromPoint(cursor)
        if workspace_root(self.gui, hovered) == root:
            floating = self.gui.GetWindowRect(self.gui.GetAncestor(hovered, 2))
            rect = (min(rect[0], floating[0]), min(rect[1], floating[1]),
                    max(rect[2], floating[2]), max(rect[3], floating[3]))
        if not (rect[0] <= cursor[0] < rect[2] and rect[1] <= cursor[1] < rect[3]):
            raise RuntimeError("鼠标需要位于 Photoshop 窗口内")
        if hold and origin is not None:cursor=tuple(origin)
        self.target = root
        self.caption_window = hwnd
        self._refresh_document_name()
        if not self.hwnd or not self.gui.IsWindow(self.hwnd):
            self._launch_overlay()
            raise RuntimeError("操作菜单正在初始化，请稍后再试")
        u = ctypes.WinDLL("user32", use_last_error=True)
        u.GetDpiForWindow.argtypes, u.GetDpiForWindow.restype = [W.HWND], W.UINT
        scale = (u.GetDpiForWindow(hwnd) or 96) / 96
        work = win32api.GetMonitorInfo(win32api.MonitorFromPoint(cursor, c.MONITOR_DEFAULTTONEAREST))["Work"]
        panel = self.panel_context.snapshot(hwnd) if self.panel_context else {'kind': 'generic'}
        self.menu_layer_context=None
        if self.layer_context_provider and panel.get('kind')!='home':
            from .layer_context import fresh,unavailable
            self.menu_layer_context=dict(self.layer_context) if fresh(self.layer_context) else unavailable()
        self.menu_context_pending=None
        if hold and panel.get('kind')=='layers' and self.menu_context_requester:
            # Reserve an identity-protected refresh, but do not touch UXP files
            # before showing. Windows read-sharing retries run on the existing
            # layer monitor, outside the window/input lock.
            self.menu_context_pending={'epoch':self.menu_epoch+1,'unpublished':True,'deadline':time.monotonic()+10}
            from .layer_context import unavailable
            self.menu_layer_context=unavailable()
        from .shape_paint import metadata
        shape=metadata((self.menu_layer_context or {}).get('shape_editor'))
        self.color_editor_active=shape_editor_allowed(panel,shape,hold,self.menu_layer_context)
        if not self.color_editor_active:shape={'available':False}
        width = min(self.settings["menu_width"],260) if context else self.settings["menu_width"]
        height = min(self.settings["menu_height"],240) if context else self.settings["menu_height"]
        bounds = panel_bounds(rect, work, cursor, round(width*scale), round(height*scale))
        if hold:
            bounds = pie_bounds(rect, work, cursor, scale, home=panel.get('kind')=='home',color_editor=self.color_editor_active or bool(self.menu_context_pending))
        # Recheck after setup: focus can change while a hotkey request is queued.
        if self.gui.GetForegroundWindow() != foreground or not self._is_photoshop(hwnd):
            raise RuntimeError("Photoshop 焦点已改变，已取消唤出")
        self.visible = True
        self.restore_pending = False
        context_ready = time.perf_counter()
        logging.info('Menu panel context: %s', panel)
        # Apply context, input protection, layout and session together before
        # showing. Avoid three synchronous renderer-thread round trips.
        self.menu_epoch += 1
        flags = panel_flags(panel, context, hold)
        if self.menu_layer_context is not None:
            from .layer_context import flags as layer_flags
            flags |= layer_flags(self.menu_layer_context)
        self.gui.SendMessage(self.hwnd, 0x8011, flags, self.menu_epoch)
        if hold and origin is not None:self.gui.SendMessage(self.hwnd,0x8017,origin[0],origin[1])
        class CopyData(ctypes.Structure):
            _fields_=[('tag',ctypes.c_size_t),('size',W.DWORD),('data',ctypes.c_void_p)]
        payload=json.dumps(shape,ensure_ascii=False).encode('utf-8')
        if len(payload)>65534:raise RuntimeError('形状颜色信息超出菜单限制')
        buffer=ctypes.create_string_buffer(payload)
        packet=CopyData(0x53485045,len(payload)+1,ctypes.cast(buffer,ctypes.c_void_p))
        self.gui.SendMessage(self.hwnd,0x4a,0,ctypes.addressof(packet))
        show_popup(self.gui, self.hwnd, root, bounds)
        try:
            self.gui.SetForegroundWindow(self.hwnd)
        except Exception:
            pass
        self._native_config()
        logging.info('Menu shown: hwnd=%s foreground=%s target=%s', self.hwnd, self.gui.GetForegroundWindow(), hwnd)
        logging.info('Menu open timing: setup/context=%.1fms show=%.1fms total=%.1fms',
                     (context_ready-open_started)*1000, (time.perf_counter()-context_ready)*1000,
                     (time.perf_counter()-open_started)*1000)
        return {"message": "操作菜单已打开", "panel_context": panel,'layer_context':self.menu_layer_context}

    @window_transition
    def _resume_completed_menu(self):
        # Only an already-visible success feedback may recover. Never show or
        # activate a window, bypass focus/input guards, or submit a PS mutation.
        if not self.visible or not self.hwnd or not self.menu_context_requester:return
        panel=self.panel_context.current if self.panel_context else {}
        if panel.get('kind')!='layers' or panel.get('input_focused') or not self._scope():return
        if self.gui.SendMessage(self.hwnd,0x8018,0,0)!=1:return
        pending=self.menu_context_pending
        if pending and pending.get('resume') and time.monotonic()<=pending['deadline']:return
        if time.monotonic()<getattr(self,'completion_retry_at',0):return
        self.completion_retry_at=time.monotonic()+2
        self.menu_context_pending={'epoch':self.menu_epoch,'unpublished':True,
                                   'deadline':time.monotonic()+10,'resume':True}

    def _cancel_closed_menu_context(self):
        with self.window_lock:
            request=getattr(self,'menu_context_active',None)
            if not request or self.visible and request['epoch']==self.menu_epoch:return
        cancel=getattr(self,'menu_context_canceller',None)
        if cancel:cancel(request)
        with self.window_lock:
            if self.menu_context_active is request:self.menu_context_active=None

    def _publish_menu_context(self):
        with self.window_lock:
            pending=self.menu_context_pending
            if not pending or not pending.get('unpublished'):return
            if not self.visible or self.menu_epoch!=pending['epoch'] or self.stop.is_set() or time.monotonic()>pending['deadline']:
                self.menu_context_pending=None;return
            pending['unpublished']=False  # Exactly one publication per menu.
        try:request=self.menu_context_requester(pending['epoch'])
        except Exception:
            logging.exception('Fresh menu context request failed');request=None
        with self.window_lock:
            # Retain the published ID even if close/reopen raced publication.
            # The monitor cancels it outside this lock on its next iteration.
            if request:self.menu_context_active=request
            if self.menu_context_pending is not pending:return
            if request and self.visible and self.menu_epoch==pending['epoch'] and not self.stop.is_set():
                request['deadline']=min(request['deadline'],pending['deadline'])
                if pending.get('resume'):request['resume']=True
                self.menu_context_pending=request
            else:self.menu_context_pending=None

    @window_transition
    def _finish_menu_context(self):
        pending=self.menu_context_pending
        if not pending:return
        if not self.visible or self.menu_epoch!=pending['epoch'] or time.monotonic()>pending['deadline']:
            self.menu_context_pending=None;return
        if 'id' not in pending:return
        try:
            snapshot=json.loads((pending['folder']/'menu-context-result.json').read_text('utf-8-sig'))
            if snapshot.get('menu_request_id')!=pending['id']:return
            phase=snapshot.get('menu_phase','completed')
            if phase not in ('basic','completed') or pending.get('applied_phase')==phase:return
            from .layer_context import validate,flags
            value=validate(snapshot,pending['session'])
            if value.get('kind') in ('unknown','none'):return
            if pending.get('applied_phase')=='basic' and any(
                    value.get(key)!=(self.menu_layer_context or {}).get(key) for key in ('session','document_id','layer_ids')):
                self.menu_context_pending=None;return
            panel=self.panel_context.current
            if panel.get('kind')!='layers' or panel.get('input_focused') or not self._scope():return
            from .shape_paint import metadata
            shape=metadata(value.get('shape_editor'))
            active=shape_editor_allowed(panel,shape,True,value)
            resume=pending.get('resume',False)
            payload=json.dumps({'epoch':pending['epoch'],'flags':flags(value),
                                **({'resume':True,'next_epoch':pending['epoch']+1} if resume else {}),
                                'shape':shape if active else {'available':False}}).encode('utf-8')
            class CopyData(ctypes.Structure):
                _fields_=[('tag',ctypes.c_size_t),('size',W.DWORD),('data',ctypes.c_void_p)]
            buffer=ctypes.create_string_buffer(payload);packet=CopyData(0x4d435458,len(payload)+1,ctypes.cast(buffer,ctypes.c_void_p))
            if self.gui.SendMessage(self.hwnd,0x4a,0,ctypes.addressof(packet)):
                if resume:
                    self.menu_epoch+=1;pending['epoch']=self.menu_epoch
                    pending.pop('resume',None);self.hold_active=False
                self.menu_layer_context=dict(value);self.color_editor_active=active
                if phase=='completed':self.menu_context_pending=None
                else:
                    pending['applied_phase']=phase
                    # A matching fresh basic result proves acceptance. Give its
                    # optional read a bounded completion window; never rewrite
                    # the request expiry or extend any modifying operation.
                    pending['deadline']=max(pending['deadline'],pending.get('completion_deadline',pending['deadline']))
                self._native_config()
        except (OSError,ValueError,KeyError):return

    def require_menu_layer_target(self,name,target):
        if name=='shape.paint' and not getattr(self,'color_editor_active',False):
            from .tasks import TaskCancelled
            raise TaskCancelled('形状颜色仅在图层面板菜单可用；本次未修改')
        if self.layer_context_provider:
            from .layer_context import require_menu_target
            require_menu_target(self.menu_layer_context,name,target)

    def context(self):
        return self.open(context=True)

    @window_transition
    def require_home(self):
        self.require_action_focus(allow_home=True)
        from .photoshop_windows import workspace_root
        root = workspace_root(self.gui, self.target or self.gui.GetForegroundWindow())
        if not root or not self.panel_context or not self.panel_context.home_visible(root):
            raise RuntimeError('Photoshop 已离开首页，请重新打开菜单选择操作')
        return root

    @window_transition
    def new_document(self):
        root = self.require_home()
        self.hide()
        from .native_commands import open_new_dialog
        return open_new_dialog(self.gui, root)

    @window_transition
    def hold_begin(self, cursor=None):
        if self.visible:
            self.hide()
        result = self.open(hold=True,origin=cursor) if cursor is not None else self.open(hold=True)
        self.hold_active = True
        return result

    @window_transition
    def hold_release(self, cursor=None):
        if not self.hold_active or not self.visible:
            return {"message": "操作菜单已收起"}
        self.hold_active = False
        if not self._scope():
            return self.hide(restore=False)
        # Resolve the physical cursor against rendered row rectangles in the
        # menu process; keyboard selection and stale hover never execute.
        if cursor is None:
            # Compatibility callers still resolve in the renderer; production
            # hook releases provide a frozen physical-key-up position.
            self.gui.SendMessage(self.hwnd, 0x800e, 0, 0)
        else:
            self.gui.SendMessage(self.hwnd, 0x8015, cursor[0], cursor[1])
        return {"message": "已结束菜单选择"}

    @window_transition
    def hold_pin(self):
        if not self.visible or not self.hold_active:
            return {"message": "操作菜单已收起"}
        if not self._scope():
            return self.hide(restore=False)
        self.hold_active = False
        self.gui.SendMessage(self.hwnd, 0x8010, 1, 0)
        return {"message": "操作菜单已固定"}

    @window_transition
    def hold_cancel(self):
        if self.hold_active:
            return self.hide(restore=False)
        return {"message": "操作菜单已收起"}

    @window_transition
    def hide(self, restore=True):
        preview=getattr(self,'mask_preview',None)
        if preview:
            preview.cancel()
            # Explicit close hides immediately. Cancellation/restoration keeps
            # its original transaction and remains observable in the backend.
            preview.feedback_shown=True

        # Hiding the window can activate a different application's window.
        # Capture ownership before ShowWindow, including ImGui submenus.
        foreground = self.gui.GetForegroundWindow()
        owned_foreground = self._is_menu_window(foreground)
        # A focus-neutral close must not strand our own hidden foreground.
        # Preserve session ownership until an actual foreign foreground is
        # observed; restore controls focus movement, not session validity.
        self.restore_pending = bool(owned_foreground and self.target)
        self.visible = False
        self.hold_active = False
        if self.hwnd and self.gui.IsWindow(self.hwnd):
            self.gui.ShowWindow(self.hwnd, 0)
        self._native_config()
        if restore and owned_foreground and self._is_photoshop(self.target):
            try:
                self.gui.SetForegroundWindow(self.target)
            except Exception:
                logging.info('Photoshop focus restore refused: before=%s target=%s', foreground, self.target)
        logging.info('Menu hidden: restore=%s before=%s after=%s', restore, foreground, self.gui.GetForegroundWindow())
        return {"message": "操作菜单已收起"}

    def dismiss(self):
        return self.hide(restore=False)

    @window_transition
    def toggle(self):
        if self.visible:
            # Closing is a menu action, not a script action: text-input guards
            # must not prevent CapsLock from closing a paused menu.
            if not self._scope():
                raise RuntimeError('请先让 Photoshop 或其菜单获得焦点')
            if getattr(self,'color_editor_active',False):
                self.gui.SendMessage(self.hwnd,0x8016,0,0)
                return {'message':'已结束形状颜色调整'}
            return self.hide()
        return self.open()

    def close(self):
        self.stop.set()
        if self.native:
            try:
                self.native.stdin.close()
                self.native.wait(3)
            except (OSError, subprocess.TimeoutExpired):
                self.native.terminate()
                self.native.wait(3)
            self.native.stdout.close()
        for name in ("thread", "monitor", "layer_monitor"):
            if getattr(self, name, None):
                getattr(self, name).join(2)
        if self.process and self.process.poll() is None:
            if self.hwnd and self.gui.IsWindow(self.hwnd):
                self.gui.PostMessage(self.hwnd, 0x0010, 0, 0)
            try:
                self.process.wait(3)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                self.process.wait(3)
        if self.icons:
            self.icons.close()
        if self.menu_thread:
            self.menu_thread.join(2)
        if self.process:
            for stream in (self.process.stdin, self.process.stdout):
                if stream:
                    stream.close()


class Tray:
    def __init__(self, notify):
        self.notify, self.hwnd = notify, None
        self.ready = threading.Event()
        self.error = ""

    def start(self):
        self.thread = threading.Thread(target=self._run, name="photoshop-tray", daemon=True)
        self.thread.start()
        self.ready.wait(3)

    def _run(self):
        import win32api
        import win32con as c
        import win32gui as g
        icon_added = False
        icons = WindowIcons()
        instance, name = win32api.GetModuleHandle(None), "PhotoshopMenuTray"
        def procedure(hwnd, message, wparam, lparam):
            if message == c.WM_USER + 1:
                if lparam == c.WM_LBUTTONDBLCLK:
                    self.notify("control")
                elif lparam == c.WM_RBUTTONUP:
                    menu = g.CreatePopupMenu()
                    try:
                        g.AppendMenu(menu, c.MF_STRING, 1, "打开后台管理")
                        g.AppendMenu(menu, c.MF_STRING, 2, "退出服务")
                        g.SetForegroundWindow(hwnd)
                        selected = g.TrackPopupMenu(menu, c.TPM_RETURNCMD | c.TPM_RIGHTBUTTON, *win32api.GetCursorPos(), 0, hwnd, None)
                        if selected:
                            self.notify("control" if selected == 1 else "quit")
                        g.PostMessage(hwnd, c.WM_NULL, 0, 0)
                    finally:
                        g.DestroyMenu(menu)
                return 0
            if message == c.WM_CLOSE:
                g.DestroyWindow(hwnd)
                return 0
            if message == c.WM_DESTROY:
                g.PostQuitMessage(0)
                return 0
            return g.DefWindowProc(hwnd, message, wparam, lparam)
        try:
            wc = g.WNDCLASS()
            wc.hInstance, wc.lpszClassName, wc.lpfnWndProc = instance, name, procedure
            wc.hIcon = icons.load(32)
            g.RegisterClass(wc)
            self.hwnd = g.CreateWindow(name, name, 0, 0, 0, 0, 0, 0, 0, instance, None)
            tray_dpi = icons.u.GetDpiForWindow(g.FindWindow('Shell_TrayWnd', None)) or 96
            tray_icon = icons.load(max(16, round(16 * tray_dpi / 96)))
            g.Shell_NotifyIcon(g.NIM_ADD, (self.hwnd, 1, g.NIF_ICON | g.NIF_MESSAGE | g.NIF_TIP, c.WM_USER + 1, tray_icon, TITLE))
            icon_added = True
            self.ready.set()
            g.PumpMessages()
        except Exception as exc:
            self.error = str(exc)
            logging.exception("Tray failed")
        finally:
            if icon_added:
                try:
                    g.Shell_NotifyIcon(g.NIM_DELETE, (self.hwnd, 1))
                except Exception:
                    pass
            self.hwnd = None
            self.ready.set()
            try:
                g.UnregisterClass(name, instance)
            except Exception:
                pass
            icons.close()

    def close(self):
        if self.hwnd:
            import win32gui
            win32gui.PostMessage(self.hwnd, 0x0010, 0, 0)
        if getattr(self, "thread", None):
            self.thread.join(3)
