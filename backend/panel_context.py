"""Read-only Photoshop panel detection. Never called from a low-level hook."""
import ctypes
from ctypes import wintypes as W
import threading
import logging
import re
import unicodedata
from .photoshop_windows import workspace_root

LABELS = {'generic': '通用操作', 'canvas': '画布', 'layers': '图层', 'home': 'Photoshop 首页',
          'text': '输入控件'}
PANEL_IDS = {'generic': 0, 'canvas': 1, 'layers': 2, 'text': 3, 'home': 4}
# Native IDs measured together on the real Layers palette. These distinguish
# the blend/filter selectors and opacity/fill inputs from similar palettes;
# counts or empty localized labels alone must never enable layer operations.
LAYER_CONTROLS = frozenset({('PSViewC',0), ('ComboBox',2490), ('ComboBox',2493),
                            ('Edit',6093), ('Edit',6097), ('ScrollBar',6098)})
# Complete identity from the user's PS 25.5.1 diagnostic. Keep signatures
# separate: mixing IDs from different palettes/versions must not match.
LAYER_CONTROLS_PS25 = frozenset({('PSViewC',0), ('ComboBox',2490), ('ComboBox',2493),
                               ('Edit',6092), ('Edit',6093), ('ScrollBar',6094)})
LAYER_SIGNATURES = (LAYER_CONTROLS,LAYER_CONTROLS_PS25)


def panel_flags(panel, context=False, hold=False):
    # Reserve bit 5 for Home without changing the existing input/layout bits.
    return (PANEL_IDS[panel['kind']] & 3) | (32 if panel['kind'] == 'home' else 0) | (int(bool(panel.get('input_focused'))) << 2) | (int(context) << 3) | (int(hold) << 4)


def panel_label(text):
    # Native localized labels can contain full-width punctuation, access keys,
    # nonbreaking spaces or directional marks. Match labels, never substrings.
    text = unicodedata.normalize('NFKC', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Cf')
    text = re.sub(r'\(&?[A-Za-z]\)', '', text).replace('&', '')
    return ''.join(text.split()).rstrip(':').casefold()


def classify_chain(chain, layer_labels=(), layer_controls=()):
    """Nearest control first; require multiple layer-specific controls."""
    classes = [item[0] for item in chain]
    if classes and classes[0] in ('Edit', 'RichEdit20W', 'RichEdit50W', 'ComboBox'):
        return 'text'
    if 'OWL.WelcomeScreenView' in classes:
        return 'home'
    if 'OWL.Document' in classes:
        return 'canvas'
    labels = {panel_label(text) for text in layer_labels}
    if 'OWL.Palette' in classes and (
        {'fill', 'lock', 'opacity'} <= labels or
        {'填充', '锁定', '不透明度'} <= labels or
        any(signature <= set(layer_controls) for signature in LAYER_SIGNATURES)
    ):
        return 'layers'
    return 'generic'


class PanelContext:
    def __init__(self, gui):
        self.gui = gui
        self.lock = threading.Lock()
        self.read_serial = 0
        self.click_revision = 0
        self.clicked = None
        self.previous_focus = None
        self.current = self.result('generic', 'fallback')

    @staticmethod
    def result(kind, source, hwnd=0):
        return {'kind': kind, 'label': LABELS[kind], 'source': source, 'hwnd': hwnd}

    def record_click(self, hwnd, root):
        # A click is the active editor in Photoshop even when OWL keeps the
        # keyboard focus on its document view. Never use mouse hover as focus.
        with self.lock:
            self.click_revision += 1
            self.clicked = (hwnd, workspace_root(self.gui, root) or root)
            self.previous_focus = None

    def describe(self, hwnd, root):
        gui = self.gui
        root = workspace_root(gui, root) or root
        if not hwnd or not gui.IsWindow(hwnd):
            return 'generic'
        chain, palette, seen = [], None, set()
        while hwnd and hwnd != root and hwnd not in seen and len(chain) < 32:
            seen.add(hwnd)
            name = gui.GetClassName(hwnd)
            chain.append((name, ''))
            if name == 'OWL.Palette' and palette is None:
                palette = hwnd
            # A floating dock is owned by Photoshop but its parent is the
            # desktop. Validate that owner via the same workspace gate as
            # hover/focus; never accept an arbitrary owned modal dialog.
            if name == 'OWL.Dock' and workspace_root(gui, hwnd) == root:
                hwnd = root
                break
            hwnd = gui.GetParent(hwnd)
        if hwnd != root:
            return 'generic'
        labels, controls = [], []
        if palette:
            def collect(child, unused):
                if not gui.IsWindowVisible(child):return
                parent, visited = gui.GetParent(child), set()
                while parent and parent != palette and parent not in visited and len(visited)<32:
                    visited.add(parent)
                    if gui.GetClassName(parent)=='OWL.Palette':return
                    parent=gui.GetParent(parent)
                if parent!=palette:return
                name=gui.GetClassName(child)
                if name == 'Static':
                    labels.append(gui.GetWindowText(child))
                elif name in ('ComboBox','Edit','ScrollBar','PSViewC'):
                    controls.append((name,gui.GetDlgCtrlID(child)))
            gui.EnumChildWindows(palette, collect, None)
        return classify_chain(chain, labels, controls)

    def focus_window(self, root):
        import win32process
        class Info(ctypes.Structure):
            _fields_ = [('cbSize', W.DWORD), ('flags', W.DWORD),
                        ('hwndActive', W.HWND), ('hwndFocus', W.HWND),
                        ('hwndCapture', W.HWND), ('hwndMenuOwner', W.HWND),
                        ('hwndMoveSize', W.HWND), ('hwndCaret', W.HWND),
                        ('rcCaret', W.RECT)]
        info = Info(cbSize=ctypes.sizeof(Info))
        user = ctypes.WinDLL('user32', use_last_error=True)
        user.GetGUIThreadInfo.argtypes = [W.DWORD, ctypes.POINTER(Info)]
        user.GetGUIThreadInfo.restype = W.BOOL
        thread = win32process.GetWindowThreadProcessId(root)[0]
        return info.hwndFocus if user.GetGUIThreadInfo(thread, ctypes.byref(info)) else 0

    def layer_list_window(self, hwnd, root):
        """Freeze only the verified Layers list, outside any input callback."""
        gui=self.gui
        if self.describe(hwnd,root)!='layers':return 0
        palette=hwnd
        for _ in range(32):
            if not palette or palette==root:return 0
            if gui.GetClassName(palette)=='OWL.Palette':break
            palette=gui.GetParent(palette)
        else:return 0
        found=[]
        def collect(child,_):
            if (gui.GetClassName(child)!='PSViewC' or gui.GetDlgCtrlID(child)!=0
                    or not gui.IsWindowVisible(child)):return
            parent=gui.GetParent(child)
            for _ in range(32):
                if parent==palette:found.append(child);return
                if not parent or gui.GetClassName(parent)=='OWL.Palette':return
                parent=gui.GetParent(parent)
        gui.EnumChildWindows(palette,collect,None)
        return found[0] if len(found)==1 else 0

    def home_visible(self, root):
        found = False
        def collect(hwnd, unused):
            nonlocal found
            if self.gui.GetClassName(hwnd) == 'OWL.WelcomeScreenView' and self.gui.IsWindowVisible(hwnd):
                left, top, right, bottom = self.gui.GetWindowRect(hwnd)
                found = found or (right > left and bottom > top)
        self.gui.EnumChildWindows(root, collect, None)
        return found

    def hover_window(self, root):
        import win32api
        user = ctypes.WinDLL('user32', use_last_error=True)
        user.SetThreadDpiAwarenessContext.argtypes = [W.HANDLE]
        user.SetThreadDpiAwarenessContext.restype = W.HANDLE
        previous = user.SetThreadDpiAwarenessContext(W.HANDLE(-4))
        try:
            hwnd = self.gui.WindowFromPoint(win32api.GetCursorPos())
            # Do not treat another application's overlapping window as PS.
            return hwnd if hwnd and workspace_root(self.gui, hwnd) == (workspace_root(self.gui, root) or root) else 0
        finally:
            if previous:
                user.SetThreadDpiAwarenessContext(previous)

    def snapshot(self, root, accept=None):
        """Fresh native reads never hold the state lock or serialize opening.

        A newer reader/click fences late background publication. The caller
        still receives its own fresh read; no old cached eligibility is used.
        """
        for attempt in range(2):
            with self.lock:
                self.read_serial += 1
                serial,revision=self.read_serial,self.click_revision
                clicked,previous=self.clicked,self.previous_focus
            try:
                value,clicked,focus=self._read_snapshot(root,clicked,previous)
            except Exception:
                logging.debug('Panel context unavailable', exc_info=True)
                value,clicked,focus=self.result('generic','fallback'),clicked,previous
            with self.lock:
                if revision!=self.click_revision:continue
                if serial==self.read_serial and (accept is None or accept()):
                    self.current=value
                    self.clicked,self.previous_focus=clicked,focus
                return dict(value)
        # Repeated click changes cannot safely identify the editor. Fail
        # closed for this invocation; the next fresh snapshot can recover.
        return {**self.result('generic','changed'),'input_focused':True}

    def _read_snapshot(self, root, clicked, previous_focus):
        root = workspace_root(self.gui, root) or root
        focus = self.focus_window(root)
        focused = self.describe(focus, root)
        if previous_focus is not None and focus != previous_focus and focused != 'generic':
            clicked = None
        kind, source, hwnd = focused, 'keyboard-focus', focus
        if clicked and clicked[1] == root and self.gui.IsWindow(clicked[0]):
            clicked_kind = self.describe(clicked[0], root)
            # Inputs with real keyboard focus win; otherwise the last clicked
            # editor is more informative than OWL's retained document focus.
            if focused != 'text':
                kind, source, hwnd = clicked_kind, 'last-click', clicked[0]
        hovered = self.hover_window(root)
        if hovered:
            kind, source, hwnd = self.describe(hovered, root), 'hover', hovered
        # Home can be shown even with documents open, and floating palettes
        # can remain above it. Visible Home wins over retained editor context.
        if kind != 'text' and self.home_visible(root):
            kind, source = 'home', 'visible-home'
        if kind == 'generic':
            source = 'fallback'
        value = self.result(kind, source, hwnd or 0)
        value['input_focused'] = focused == 'text'
        return value,clicked,focus
