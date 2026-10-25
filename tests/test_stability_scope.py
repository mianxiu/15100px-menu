import types
import unittest
from unittest.mock import patch
from backend.stability_metrics import host_scope


class ScopeTests(unittest.TestCase):
    def test_any_foreground_allowed_but_original_process_required(self):
        names={1:'Photoshop.exe',2:'QQ.exe'};created={1:10,2:20}
        class Handle:
            def __init__(self,pid):self.pid=pid
            def Close(self):pass
        def open_process(_,__,pid):
            if pid not in names:raise OSError('gone')
            return Handle(pid)
        api=types.SimpleNamespace(OpenProcess=open_process)
        process=types.SimpleNamespace(EnumProcesses=lambda:list(names),
            GetModuleFileNameEx=lambda handle,_:names[handle.pid],
            GetProcessTimes=lambda handle:{'CreationTime':created[handle.pid]})
        with patch.dict('sys.modules',win32api=api,win32process=process):
            pid,check=host_scope();self.assertEqual(pid,1);check()
            created[1]=11
            with self.assertRaises(RuntimeError):check()
            created[1]=10;names[1]='other.exe'
            with self.assertRaises(RuntimeError):check()
            del names[1]
            with self.assertRaises(RuntimeError):check()
            with self.assertRaises(RuntimeError):host_scope()
            names.update({1:'Photoshop.exe',3:'Photoshop.exe'});created[3]=30
            with self.assertRaises(RuntimeError):host_scope()
