"""Open Photoshop's native New dialog; never create a document or retry."""
import ctypes
from ctypes import wintypes as W


class Keyboard(ctypes.Structure):
    _fields_ = [('vk', W.WORD), ('scan', W.WORD), ('flags', W.DWORD),
                ('time', W.DWORD), ('extra', ctypes.c_size_t)]


class Mouse(ctypes.Structure):
    _fields_ = [('dx', W.LONG), ('dy', W.LONG), ('data', W.DWORD),
                ('flags', W.DWORD), ('time', W.DWORD), ('extra', ctypes.c_size_t)]


class Payload(ctypes.Union):
    _fields_ = [('keyboard', Keyboard), ('mouse', Mouse)]


class Input(ctypes.Structure):
    _fields_ = [('type', W.DWORD), ('payload', Payload)]


def open_new_dialog(gui, root, user=None):
    user = user or ctypes.WinDLL('user32', use_last_error=True)
    # Do not combine our command with modifiers physically held by the user.
    for key in (0x10, 0x11, 0x12, 0x5B, 0x5C):
        if user.GetAsyncKeyState(key) & 0x8000:
            raise RuntimeError('请先松开 Ctrl／Alt／Shift／Win，再选择新建文档')
    if gui.GetForegroundWindow() != root:
        raise RuntimeError('Photoshop 焦点已改变，未打开新建窗口')
    user.SendInput.argtypes = [W.UINT, ctypes.POINTER(Input), ctypes.c_int]
    user.SendInput.restype = W.UINT
    def key(vk, up=False):
        return Input(1, Payload(keyboard=Keyboard(vk, 0, 2 if up else 0, 0, 0)))
    sequence = (Input * 4)(key(0x11), key(0x4E), key(0x4E, True), key(0x11, True))
    accepted = user.SendInput(4, sequence, ctypes.sizeof(Input))
    if accepted != 4:
        # Release only the injected keys after partial acceptance. Never retry
        # a New command, whose result could already be visible in Photoshop.
        if accepted:
            cleanup = (Input * 2)(key(0x4E, True), key(0x11, True))
            user.SendInput(2, cleanup, ctypes.sizeof(Input))
        raise RuntimeError('系统未完整接受新建窗口快捷键，请检查 Photoshop')
    return {'message': '已发送 Photoshop 原生新建窗口请求', 'channel': 'photoshop-native-shortcut', 'shortcut': 'Ctrl+N'}
