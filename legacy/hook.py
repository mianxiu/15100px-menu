def hook(FocusCallback,*log:bool):
    import sys
    import time
    import ctypes
    import ctypes.wintypes

    EVENT_SYSTEM_FOCUS = 0x0003
    WINEVENT_OUTOFCONTEXT = 0x0000

    user32 = ctypes.windll.user32
    ole32 = ctypes.windll.ole32

    WinEventProcType = ctypes.WINFUNCTYPE(
        None,
        ctypes.wintypes.HANDLE,
        ctypes.wintypes.DWORD,
        ctypes.wintypes.HWND,
        ctypes.wintypes.LONG,
        ctypes.wintypes.LONG,
        ctypes.wintypes.DWORD,
        ctypes.wintypes.DWORD,
    )


    def run(
        hWinEventHook, event, hwnd, idObject, idChild, dwEventThread, dwmsEventTime
    ):
        # length = user32.GetWindowTextLengthA(hwnd)
        # buff = ctypes.create_string_buffer(length + 1)
        # # user32.GetWindowTextA(hwnd, buff, length + 1)
        # user32.GetClassNameA(hwnd,buff,length+1)
        # className = buff.value.decode('utf-8')
        # if className == windowsClassName:
            FocusCallback()
            # if log: print("The Window is Focus, Class Name: ",className)
        # else:
            # print(className)


    WinEventProc = WinEventProcType(run)

    user32.SetWinEventHook.restype = ctypes.wintypes.HANDLE
    hook = user32.SetWinEventHook(
        EVENT_SYSTEM_FOCUS, EVENT_SYSTEM_FOCUS, 0, WinEventProc, 0, 0, WINEVENT_OUTOFCONTEXT
    )
    if hook == 0:
        print("SetWinEventHook failed")
        sys.exit(1)

    msg = ctypes.wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) != 0:
        time.sleep(1)
        user32.TranslateMessageW(msg)
        user32.DispatchMessageW(msg)

    user32.UnhookWinEvent(hook)
    ole32.CoUninitialize()


# def callback(): 
#     import win32gui
#     hwdn = win32gui.GetForegroundWindow()
#     print(win32gui.GetClassName(hwdn))
    
# hook(callback,True)