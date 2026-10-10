"""Read-only panel diagnostics against the currently running Photoshop."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ctypes
import json
import win32gui
from backend.panel_context import PanelContext

user = ctypes.WinDLL('user32')
user.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
user.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
root = win32gui.FindWindow('Photoshop', None)
if not root:
    raise SystemExit('Photoshop is not running')
detector = PanelContext(win32gui)
candidates = []
def inspect(hwnd, unused):
    if win32gui.IsWindowVisible(hwnd) and win32gui.GetClassName(hwnd) == 'PSViewC':
        kind = detector.describe(hwnd, root)
        candidates.append({'hwnd':hwnd, 'kind':kind, 'rect':win32gui.GetWindowRect(hwnd)})
win32gui.EnumChildWindows(root, inspect, None)
print(json.dumps({'focus':detector.snapshot(root), 'panels':candidates}, ensure_ascii=True))
