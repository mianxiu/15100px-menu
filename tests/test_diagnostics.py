import asyncio,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,AsyncMock
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
            with patch('asyncio.create_subprocess_exec',side_effect=OSError('not installed')), patch('backend.diagnostics.asyncio.sleep',new=AsyncMock()):
                d.start();await d.task
            self.assertEqual(d.snapshot()['phase'],'failed');self.assertFalse(d.snapshot()['ready'])
            with self.assertRaises(RuntimeError):d.export()

    async def test_prepare_clock_is_monotonic_and_never_marks_report_ready(self):
        with tempfile.TemporaryDirectory() as folder:
            d=Diagnostics(folder,'probe.ps1',15153)
            with patch('backend.diagnostics.time.monotonic',return_value=100):
                d.start();self.assertEqual(d.snapshot()['remaining_ms'],5000)
            with patch('backend.diagnostics.time.monotonic',return_value=103.25):
                self.assertEqual(d.snapshot()['remaining_ms'],1750)
            with patch('backend.diagnostics.time.monotonic',return_value=110):
                self.assertEqual(d.snapshot()['remaining_ms'],0);self.assertFalse(d.snapshot()['ready'])
            await d.close()

    async def test_progress_stream_tracks_real_samples_and_ignores_untrusted_fields(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as folder:
            d=Diagnostics(folder,'probe.ps1',15153);d.state={'phase':'collecting'}
            stream=asyncio.StreamReader()
            for line in [b'Other stdout',b'PSMENU_PROGRESS {}',b'PSMENU_PROGRESS {"stage":"completed"}',b'PSMENU_PROGRESS {"stage":"sampling","remaining_ms":9000,"samples_done":1}']:
                stream.feed_data(line+b'\n')
            stream.feed_eof()
            await d.read_progress(SimpleNamespace(stdout=stream))
            self.assertEqual(d.snapshot()['stage'],'sampling');self.assertEqual(d.snapshot()['samples_done'],1)
            self.assertGreater(d.snapshot()['remaining_ms'],8000);self.assertFalse(d.snapshot()['ready'])

    async def test_completed_report_requires_process_success_and_has_full_evidence(self):
        import json
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as folder:
            d=Diagnostics(folder,'probe.ps1',15153);phases=[];d.listener=lambda value:phases.append(value['stage'])
            d.provider=lambda:{'events':[{'message':256,'matched_action':'hold_begin'}]}
            async def spawn(*args,**kwargs):
                self.assertIn('-ProgressStream',args);self.assertEqual(args[args.index('-DelaySeconds')+1],'0')
                path=Path(args[args.index('-OutputPath')+1]);path.write_text(json.dumps({'schema':2,'read_only':True}),'utf-8')
                stream=asyncio.StreamReader();stream.feed_data(b'PSMENU_PROGRESS {"stage":"processing","samples_done":10}\n');stream.feed_eof()
                return SimpleNamespace(stdout=stream,returncode=0,wait=AsyncMock(return_value=0))
            with patch('asyncio.create_subprocess_exec',side_effect=spawn),patch('backend.diagnostics.asyncio.sleep',new=AsyncMock()):
                d.start();await d.task
            self.assertEqual(phases,['prepare','starting','processing','completed'])
            self.assertTrue(d.snapshot()['ready']);self.assertEqual(d.export()['trigger_summary'],'native_open_action_emitted')
