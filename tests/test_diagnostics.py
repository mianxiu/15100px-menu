import asyncio,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,AsyncMock
from backend.diagnostics import Diagnostics
from backend.diagnostics import trigger_summary,runtime_report,uxp_findings

class DiagnosticTests(unittest.IsolatedAsyncioTestCase):
    def test_runtime_export_excludes_documents_credentials_and_raw_errors(self):
        report=runtime_report({'application':{'version':'146','executable':'SECRET_PATH'},
            'photoshop':{'document':'SECRET_DOCUMENT','layer_context':{'layer_ids':[1,2],'document_name':'SECRET_DOCUMENT','kind':'pixel'},
                'layer_observation':{'background':{'selection_ms':900,'error':'SECRET_ERROR'}}},
            'tasks':{'items':[{'id':'a','state':'failed','target':{'name':'SECRET_DOCUMENT'},'error':'SECRET_ERROR','timeline':[{'state':'running','duration_ms':40,'token':'SECRET_TOKEN'}]}]},
            'application_update':{'phase':'error','error':'SECRET_PROXY','release':{'body':'SECRET_BODY'}},
            'graphics':{'requested':'auto','active':'gpu','adapter':'test adapter','private':'SECRET_GPU'},'token':'SECRET_TOKEN'})
        import json
        self.assertNotIn('SECRET',json.dumps(report))
        self.assertEqual(report['layer_context']['selection_count'],2)
        self.assertEqual(report['layer_observation']['background']['selection_ms'],900)
        self.assertTrue(report['tasks'][0]['error_present'])
        self.assertEqual(report['graphics'],{'requested':'auto','active':'gpu','adapter':'test adapter'})
        self.assertEqual(runtime_report({'photoshop':{'layer_observation':None,'layer_context':None}})['layer_context']['selection_count'],0)

    def test_loader_findings_ignore_old_host_and_pre_start_logs(self):
        value={'plugin_exists':True,'backend':{'ready':False},'logs':[{'loader_lines':['system fallback plugins folder: x']}]}
        self.assertEqual(uxp_findings(value),['uxp_current_host_logs_unavailable'])
        value['logs'][0].update(matches_running_host=True,after_host_start=False)
        self.assertEqual(uxp_findings(value),['uxp_current_host_logs_unavailable'])
        value['logs'][0]['after_host_start']=True
        self.assertEqual(uxp_findings(value),['uxp_user_external_scan_not_observed'])
        value['logs'][0]['loader_lines'].append('Loading plugins from user fallback plugins folder: x')
        self.assertEqual(uxp_findings(value),['uxp_load_unconfirmed'])
        value['backend']['ready']=True;self.assertEqual(uxp_findings(value),['uxp_loaded'])

    async def test_combined_report_preserves_sections_when_one_tool_times_out(self):
        with tempfile.TemporaryDirectory() as folder:
            d=Diagnostics(folder,'panel.ps1',15153);d.runtime_provider=lambda:{'photoshop':{'busy':True}}
            async def run(kind):
                if kind=='uxp':raise TimeoutError('PRIVATE_ERROR')
                return {'schema':2,'read_only':True,'panels':[{'floating':False}]}
            with patch.object(d,'run_script',side_effect=run),patch('backend.diagnostics.asyncio.sleep',new=AsyncMock()):
                d.start('all');await d.task
            self.assertTrue(d.snapshot()['ready']);self.assertTrue(d.snapshot()['partial'])
            report=d.export();self.assertEqual(report['components']['uxp']['reason'],'timed_out')
            self.assertTrue(report['runtime']['photoshop']['busy']);self.assertEqual(len(report['panels']),1)
            self.assertEqual(report['components']['menu']['phase'],'completed')

    def test_index_findings_prefer_explicit_registration_state_to_scan_absence(self):
        for state in ('missing','disabled','invalid','outdated'):
            value={'plugin_exists':True,'backend':{'ready':False,'registration':{'state':state}}}
            self.assertEqual(uxp_findings(value),['uxp_registration_'+state])
            value['backend']['ready']=True
            self.assertEqual(uxp_findings(value),['uxp_loaded'])

    async def test_uxp_only_has_no_delay_menu_sampling_or_trigger_trace(self):
        with tempfile.TemporaryDirectory() as folder:
            d=Diagnostics(folder,'panel.ps1',15153);d.provider=lambda:self.fail('No trigger trace for UXP-only')
            with patch.object(d,'run_script',new=AsyncMock(return_value={'schema':1,'read_only':True,'backend':{'ready':True}})) as run,patch('backend.diagnostics.asyncio.sleep',new=AsyncMock()) as sleep:
                d.start('uxp');await d.task
            run.assert_awaited_once_with('uxp');sleep.assert_not_awaited()
            self.assertEqual(d.export()['findings'],['uxp_loaded'])
            self.assertNotIn('trigger_decisions',d.export())

    async def test_runtime_only_launches_no_subprocess_and_invalid_scope_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            d=Diagnostics(folder,'panel.ps1',15153);d.runtime_provider=lambda:{'photoshop':{'uxp_ready':False}}
            with self.assertRaises(ValueError):d.start('arbitrary.ps1')
            with self.assertRaises(ValueError):d.start(['all'])
            with patch('asyncio.create_subprocess_exec',new=AsyncMock()) as spawn:
                d.start('runtime');await d.task
            spawn.assert_not_awaited();self.assertTrue(d.snapshot()['ready'])
            self.assertEqual(d.export()['runtime']['photoshop']['uxp_ready'],False)

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
