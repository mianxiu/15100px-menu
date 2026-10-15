import asyncio,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from backend.diagnostics import Diagnostics
from backend.diagnostics import trigger_summary

class DiagnosticTests(unittest.IsolatedAsyncioTestCase):
    def test_summary_does_not_infer_a_keypress_from_sampling(self):
        self.assertEqual(trigger_summary({'enabled':False}),'menu_disabled')
        self.assertEqual(trigger_summary({'events':[]}),'no_trigger_keydown_observed')
        self.assertEqual(trigger_summary({'events':[{'message':257}]}),'no_trigger_keydown_observed')

    def test_summary_distinguishes_native_gates_from_backend_opening(self):
        event={'message':256,'process_scope':False}
        def result():return trigger_summary({'events':[event]})
        self.assertEqual(result(),'outside_recognized_ps_process')
        event['process_scope']=True;self.assertEqual(result(),'activation_not_qualified')
        event['activation_allowed']=True;self.assertEqual(result(),'workspace_scope_rejected')
        event['command_scope']=True;self.assertEqual(result(),'key_received_without_open_match')
        event['matched_action']='hold_begin';self.assertEqual(result(),'native_open_action_emitted')

    async def test_start_is_single_job_and_export_is_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            d=Diagnostics(folder,'probe.ps1',15153);gate=asyncio.Event()
            async def collect():await gate.wait()
            with patch.object(d,'collect',collect):
                self.assertEqual(d.start()['phase'],'collecting')
                with self.assertRaises(RuntimeError):d.start()
                with self.assertRaises(RuntimeError):d.export()
                await d.close();self.assertTrue(d.task.cancelled())
    async def test_subprocess_failure_is_not_a_ready_report(self):
        with tempfile.TemporaryDirectory() as folder:
            d=Diagnostics(folder,'probe.ps1',15153)
            with patch('asyncio.create_subprocess_exec',side_effect=OSError('not installed')):
                d.start();await d.task
            self.assertEqual(d.snapshot()['phase'],'failed');self.assertFalse(d.snapshot()['ready'])
            with self.assertRaises(RuntimeError):d.export()
