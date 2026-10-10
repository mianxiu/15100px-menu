import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from backend.control_window import ControlWindow, TITLE


@unittest.skipUnless(os.name=='nt','Windows management window')
class ControlWindowTests(unittest.TestCase):
    def test_same_title_from_other_profile_cannot_be_found_or_closed(self):
        control=ControlWindow('http://localhost')
        control.owned_pids={100}
        control.icons=SimpleNamespace(detach=Mock(),close=Mock())
        def enum(callback,extra):
            callback(21,extra);callback(20,extra)
        with patch('win32gui.EnumWindows',side_effect=enum),patch('win32gui.GetWindowText',return_value=TITLE), \
             patch('win32gui.IsWindow',return_value=True),patch('win32process.GetWindowThreadProcessId',side_effect=lambda hwnd:(0,100 if hwnd==20 else 200)), \
             patch('win32gui.PostMessage') as close:
            self.assertEqual(control._find_window(),20)
            control.hwnd=21;control.close()
            close.assert_not_called();control.icons.detach.assert_not_called()
            control.hwnd=20;control.close()
            close.assert_called_once()

    def test_profile_arguments_with_spaces_match_exactly(self):
        with tempfile.TemporaryDirectory(prefix='Edge profiles ') as folder:
            control=ControlWindow('http://localhost',Path(folder)/'one')
            profile=str((control.runtime/'control-profile').resolve())
            command=subprocess.list2cmdline(['msedge.exe','--user-data-dir='+profile])
            wrong=subprocess.list2cmdline(['msedge.exe','--user-data-dir='+profile+'-other'])
            wmi=SimpleNamespace(ExecQuery=lambda query:[SimpleNamespace(ProcessId=100,CommandLine=command),SimpleNamespace(ProcessId=200,CommandLine=wrong)])
            with patch('win32com.client.GetObject',return_value=wmi):
                self.assertEqual(control._profile_pids(),{100})
