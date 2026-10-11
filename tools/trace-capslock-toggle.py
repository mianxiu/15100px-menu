"""Read Windows' CapsLock toggle bit without installing hooks or sending input.

GetKeyState is a Windows message-queue state sample, not a hardware LED query.
This observer pumps its queue and records changes plus periodic baselines.
Create OUTPUT/stop-toggle to stop. No automatic timeout.
"""
import argparse
import ctypes
from ctypes import wintypes as W
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    user = ctypes.WinDLL('user32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetTickCount64.restype = ctypes.c_ulonglong
    user.GetKeyState.argtypes = [ctypes.c_int]
    user.GetKeyState.restype = ctypes.c_short
    user.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user.GetAsyncKeyState.restype = ctypes.c_short
    user.GetForegroundWindow.restype = W.HWND
    user.GetWindowThreadProcessId.argtypes = [W.HWND, ctypes.POINTER(W.DWORD)]
    user.GetClassNameW.argtypes = [W.HWND, W.LPWSTR, ctypes.c_int]
    user.PeekMessageW.argtypes = [ctypes.POINTER(W.MSG), W.HWND, W.UINT, W.UINT, W.UINT]
    user.TranslateMessage.argtypes = [ctypes.POINTER(W.MSG)]
    user.DispatchMessageW.argtypes = [ctypes.POINTER(W.MSG)]
    user.DispatchMessageW.restype = ctypes.c_ssize_t
    logger = logging.getLogger('caps.toggle')
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(args.output / 'toggle.jsonl', maxBytes=8*1024*1024,
                                  backupCount=15, encoding='utf-8')
    logger.addHandler(handler)
    message = W.MSG()
    previous = None
    heartbeat = 0
    logger.info(json.dumps({'type':'observer.start', 'pid':os.getpid(), 'time':time.time()}))
    try:
        while not (args.output / 'stop-toggle').exists():
            while user.PeekMessageW(ctypes.byref(message), None, 0, 0, 1):
                user.TranslateMessage(ctypes.byref(message))
                user.DispatchMessageW(ctypes.byref(message))
            state = user.GetKeyState(20)
            toggled = bool(state & 1)
            now = time.monotonic()
            if toggled != previous or now >= heartbeat:
                hwnd = user.GetForegroundWindow()
                pid = W.DWORD()
                user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                name = ctypes.create_unicode_buffer(64)
                user.GetClassNameW(hwnd, name, len(name))
                logger.info(json.dumps({'type':'caps.state' if toggled != previous else 'caps.baseline',
                    'time':time.time(), 'tick_ms':kernel.GetTickCount64(),
                    'toggle_on':toggled, 'previous':previous, 'get_key_state':state,
                    'async_down':bool(user.GetAsyncKeyState(20) & 0x8000),
                    'hwnd':hwnd or 0, 'pid':pid.value, 'window_class':name.value,
                    'source':'GetKeyState; observer queue'}, ensure_ascii=False))
                previous = toggled
                heartbeat = now + 1
            time.sleep(.008)
    finally:
        logger.info(json.dumps({'type':'observer.stop', 'time':time.time()}))
        handler.close()


if __name__ == '__main__':
    main()
