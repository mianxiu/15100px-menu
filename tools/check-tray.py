"""Check this service's notification registration, optionally exercising Explorer recovery."""
import ctypes
from ctypes import wintypes as W
import time
import win32gui as g
import win32process


def check_tray(service_pid, recover=False):
    windows = []
    def collect(hwnd, unused):
        if g.GetClassName(hwnd) == 'PhotoshopMenuTray' and win32process.GetWindowThreadProcessId(hwnd)[1] == service_pid:
            windows.append(hwnd)
    g.EnumWindows(collect, None)
    assert len(windows) == 1, 'Expected exactly one tray window owned by this service'
    hwnd = windows[0]
    class Guid(ctypes.Structure):
        _fields_ = [('a', W.DWORD), ('b', W.WORD), ('c', W.WORD), ('d', ctypes.c_ubyte*8)]
    class Identity(ctypes.Structure):
        _fields_ = [('size', W.DWORD), ('hwnd', W.HWND), ('uid', W.UINT), ('guid', Guid)]
    identity = Identity()
    identity.size, identity.hwnd, identity.uid = ctypes.sizeof(identity), hwnd, 1
    query = ctypes.WinDLL('shell32').Shell_NotifyIconGetRect
    query.argtypes, query.restype = [ctypes.POINTER(Identity), ctypes.POINTER(W.RECT)], ctypes.c_long
    def registered():
        rect = W.RECT()
        if query(ctypes.byref(identity), ctypes.byref(rect)) != 0:
            return None
        return [rect.left, rect.top, rect.right, rect.bottom]
    assert registered(), 'Tray window exists but Windows has no notification icon'
    if recover:
        # Remove only this test service's icon; never restart Explorer or touch other icons.
        g.Shell_NotifyIcon(g.NIM_DELETE, (hwnd, 1))
        assert registered() is None, 'Test icon was not removed'
        g.PostMessage(hwnd, g.RegisterWindowMessage('TaskbarCreated'), 0, 0)
        until = time.monotonic()+8
        while not registered() and time.monotonic() < until:
            time.sleep(.05)
        assert registered(), 'Tray icon did not recover after TaskbarCreated'
    return {'hwnd': hwnd, 'registered': True, 'rect': registered(), 'recovery_checked': recover,
            'visual_checked': False, 'real_explorer_restart_checked': False}
