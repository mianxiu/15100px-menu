"""Read-only Photoshop panel detection. Never called from a low-level hook."""
import ctypes
from ctypes import wintypes as W
import threading
import logging
from .photoshop_windows import workspace_root

LABELS = {'generic': '通用操作', 'canvas': '画布', 'layers': '图层',
          'text': '输入控件'}
PANEL_IDS = {'generic': 0, 'canvas': 1, 'layers': 2, 'text': 3}


def classify_chain(chain, layer_labels=()):
    """Nearest control first; require multiple layer-specific controls."""
    classes = [item[0] for item in chain]
    if classes and classes[0] in ('Edit', 'RichEdit20W', 'RichEdit50W', 'ComboBox'):
        return 'text'
    if 'OWL.Document' in classes:
        return 'canvas'
    labels = {text.strip().rstrip(':：').casefold() for text in layer_labels}
    if 'OWL.Palette' in classes and (
        {'fill', 'lock', 'opacity'} <= labels or
        {'填充', '锁定', '不透明度'} <= labels
    ):
        return 'layers'
    return 'generic'


class PanelContext:
    def __init__(self, gui):
        self.gui = gui
        self.lock = threading.Lock()
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
            if name == 'OWL.Palette':
                palette = hwnd
            hwnd = gui.GetParent(hwnd)
        if hwnd != root:
            return 'generic'
        labels = []
        if palette:
            def collect(child, unused):
                if gui.IsWindowVisible(child) and gui.GetClassName(child) == 'Static':
                    labels.append(gui.GetWindowText(child))
            gui.EnumChildWindows(palette, collect, None)
        return classify_chain(chain, labels)

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

    def snapshot(self, root):
        """Resolve on a worker, preserving panel context while popup has focus."""
        with self.lock:
            try:
                return self._snapshot_locked(root)
            except Exception:
                # PS may destroy/recreate controls during a workspace change.
                logging.debug('Panel context unavailable', exc_info=True)
                self.current = self.result('generic', 'fallback')
                return dict(self.current)

    def _snapshot_locked(self, root):
        root = workspace_root(self.gui, root) or root
        clicked = self.clicked
        focus = self.focus_window(root)
        focused = self.describe(focus, root)
        if self.previous_focus is not None and focus != self.previous_focus and focused != 'generic':
            self.clicked = clicked = None
        self.previous_focus = focus
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
        if kind == 'generic':
            source = 'fallback'
        self.current = self.result(kind, source, hwnd or 0)
        self.current['input_focused'] = focused == 'text'
        return dict(self.current)
