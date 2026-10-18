import unittest
from tools.quiet_ps_session import select

class QuietWindowSelectionTests(unittest.TestCase):
    def test_notification_does_not_count_as_another_main_window_but_two_main_windows_are_ambiguous(self):
        ps={'role':'photoshop','cls':'Photoshop','monitor':2,'hwnd':10}
        main={'role':'codex','cls':'Chrome_WidgetWin_1','monitor':2,'hwnd':20}
        toast={'role':'codex','cls':'ATL:notification','monitor':2,'hwnd':30}
        monitor={'handle':2,'Flags':0}
        state={'windows':[toast,main,ps],'monitors':[monitor]}
        self.assertEqual(select(state),(ps,monitor))
        state['windows'].append({**main,'hwnd':21})
        with self.assertRaises(RuntimeError):select(state)
