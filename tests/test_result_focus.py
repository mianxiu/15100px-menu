import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from backend.desktop import Desktop


class ResultFocusTests(unittest.TestCase):
    def desktop(self,front):
        desktop=Desktop.__new__(Desktop);desktop.window_lock=threading.RLock()
        desktop.gui=SimpleNamespace(EnumWindows=lambda callback,_:callback(10,None),
            SetForegroundWindow=Mock(),GetForegroundWindow=lambda:front[0],SendMessageTimeout=Mock())
        desktop._is_photoshop=lambda hwnd:hwnd==10
        desktop._workspace_root=lambda hwnd:10 if hwnd==10 else 0
        desktop.hide=Mock();desktop.require_action_focus=Mock()
        return desktop

    def test_delayed_activation_waits_once_outside_lock_then_checks_focus(self):
        front=[20];desktop=self.desktop(front)
        def activate(*args):
            self.assertFalse(desktop.window_lock._is_owned());front[0]=10
        desktop.gui.SendMessageTimeout.side_effect=activate
        desktop.focus_search_result()
        desktop.gui.SetForegroundWindow.assert_called_once_with(10)
        desktop.gui.SendMessageTimeout.assert_called_once_with(10,0,0,0,2,200)
        desktop.require_action_focus.assert_called_once()

    def test_already_active_adds_no_wait(self):
        desktop=self.desktop([10]);desktop.gui.SetForegroundWindow.side_effect=OSError('activation refused');desktop.focus_search_result()
        desktop.gui.SetForegroundWindow.assert_not_called()
        desktop.gui.SendMessageTimeout.assert_not_called();desktop.require_action_focus.assert_called_once()

    def test_activation_error_can_only_continue_after_verified_actual_focus(self):
        front=[20];desktop=self.desktop(front);desktop.gui.SetForegroundWindow.side_effect=OSError('not acknowledged')
        desktop.gui.SendMessageTimeout.side_effect=lambda *args:front.__setitem__(0,10)
        desktop.focus_search_result();desktop.require_action_focus.assert_called_once()
        front[0]=20;desktop.require_action_focus.reset_mock();desktop.gui.SendMessageTimeout.side_effect=None
        with self.assertRaisesRegex(RuntimeError,'Windows未允许'):desktop.focus_search_result()
        desktop.require_action_focus.assert_not_called()

    def test_refused_or_unresponsive_never_passes_execution_guard(self):
        for failure in (None,OSError('timeout')):
            desktop=self.desktop([20]);desktop.gui.SendMessageTimeout.side_effect=failure
            with self.assertRaises(RuntimeError):desktop.focus_search_result()
            desktop.gui.SetForegroundWindow.assert_called_once();desktop.require_action_focus.assert_not_called()
