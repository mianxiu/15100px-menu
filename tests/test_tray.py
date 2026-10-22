import unittest
import os
from pathlib import Path
import runpy
from unittest.mock import Mock, patch

import win32con as c
import win32gui as g

from backend.desktop import Tray


class TrayTests(unittest.TestCase):
    def run_tray(self, failures, messages):
        tray = Tray(Mock())
        icons = Mock()
        icons.u.GetDpiForWindow.return_value = 96
        icons.u.SetTimer.return_value = 1
        icons.load.return_value = 123
        state = {}
        def register(wc):
            state['procedure'] = wc.lpfnWndProc
        def pump():
            for message, wparam in messages:
                state['procedure'](42, message, wparam, 0)
        with patch('backend.desktop.WindowIcons', return_value=icons), \
             patch.object(g, 'RegisterWindowMessage', return_value=0xc123), \
             patch.object(g, 'RegisterClass', side_effect=register), \
             patch.object(g, 'CreateWindow', return_value=42), \
             patch.object(g, 'FindWindow', return_value=43), \
             patch.object(g, 'PumpMessages', side_effect=pump), \
             patch.object(g, 'UnregisterClass'), \
             patch.object(g, 'Shell_NotifyIcon') as notify, \
             patch('backend.desktop.logging.exception'):
            def registration(operation, data):
                if operation == g.NIM_ADD and failures:
                    fail = failures.pop(0)
                    if fail:
                        raise RuntimeError('Explorer not ready')
            notify.side_effect = registration
            tray._run()
        return tray, icons, notify

    def test_explorer_restart_readds_icon_without_reopening_control(self):
        tray, icons, notify = self.run_tray([], [(0xc123, 0), (0xc123, 0)])
        self.assertEqual([v.args[0] for v in notify.call_args_list], [g.NIM_ADD, g.NIM_MODIFY, g.NIM_MODIFY, g.NIM_DELETE])
        self.assertFalse(tray.error)
        tray.notify.assert_not_called()
        icons.u.SetTimer.assert_not_called()
        icons.close.assert_called_once()

    def test_startup_failure_keeps_pump_and_retry_clears_error(self):
        tray, icons, notify = self.run_tray([True, False], [(c.WM_TIMER, 1)])
        self.assertEqual([v.args[0] for v in notify.call_args_list], [g.NIM_ADD]*2+[g.NIM_DELETE])
        icons.u.SetTimer.assert_called_once_with(42, 1, 1000, None)
        self.assertFalse(tray.error)
        self.assertTrue(tray.ready.is_set())

    def test_retries_are_bounded_and_taskbar_event_can_recover(self):
        messages = [(c.WM_TIMER, 1)]*5+[(0xc123, 0)]
        tray, icons, notify = self.run_tray([True]*6+[False], messages)
        self.assertEqual(icons.u.SetTimer.call_count, 5)
        self.assertEqual([v.args[0] for v in notify.call_args_list], [g.NIM_ADD]*7+[g.NIM_DELETE])
        self.assertFalse(tray.error)

    def test_exhausted_registration_is_reported(self):
        tray, icons, notify = self.run_tray([True]*6, [(c.WM_TIMER, 1)]*5)
        self.assertIn('Explorer not ready', tray.error)
        self.assertEqual(icons.u.SetTimer.call_count, 5)
        self.assertTrue(all(v.args[0] == g.NIM_ADD for v in notify.call_args_list))

    def test_real_shell_registration_recovers_without_restarting_explorer(self):
        check = runpy.run_path(str(Path(__file__).resolve().parents[1]/'tools/check-tray.py'))['check_tray']
        tray = Tray(Mock())
        tray.start()
        try:
            self.assertFalse(tray.error)
            self.assertTrue(check(os.getpid(), recover=True)['registered'])
            g.SendMessage(tray.hwnd, g.RegisterWindowMessage('TaskbarCreated'), 0, 0)
            self.assertFalse(tray.error)
            tray.notify.assert_not_called()
        finally:
            tray.close()
        self.assertFalse(tray.thread.is_alive())
