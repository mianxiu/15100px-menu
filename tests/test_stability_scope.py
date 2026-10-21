import os
import types
import unittest
from unittest.mock import Mock,patch
from backend.stability_metrics import host_scope


class ScopeTests(unittest.TestCase):
    def test_authorized_app_switches_allowed_foreign_or_missing_process_stops(self):
        front=[2]
        names={1:'Photoshop.exe',2:'chrome.exe',3:'DeepSeek Harness.exe',4:'QQ.exe'}
        api=types.SimpleNamespace(OpenProcess=lambda _,__,pid:types.SimpleNamespace(pid=pid,Close=lambda:None))
        gui=types.SimpleNamespace(GetForegroundWindow=lambda:front[0])
        process=types.SimpleNamespace(EnumProcesses=lambda:[1,2,3,4],
            GetModuleFileNameEx=lambda handle,_:names[handle.pid],GetWindowThreadProcessId=lambda hwnd:(1,hwnd))
        with patch.dict('sys.modules',win32api=api,win32gui=gui,win32process=process):
            pid,check=host_scope();self.assertEqual(pid,1)
            for allowed in (2,3,1,os.getpid()):front[0]=allowed;check()
            for denied in (4,0,999):
                front[0]=denied
                with self.assertRaises(RuntimeError):check()
            with self.assertRaises(RuntimeError):host_scope()
