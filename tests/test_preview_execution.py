import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from backend.uxp_recovery import PendingUxp
from backend.legacy_preview import returned_result
from backend.mask_preview import MaskPreview
from tests.test_mask_preview import paint


class PreviewExitEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.storage=self.root/'storage';self.folder=self.storage/'24/External/com.15100px.menu.offline-probe/PluginData';self.folder.mkdir(parents=True)
        self.pending=PendingUxp(self.root/'uxp-pending.json',self.storage)
        self.request={'id':'a'*32,'session':'original','operation':'set_label','command':'shape.preview','token':'private'}
        self.pending.begin(self.request,self.folder,'b'*32)
        self.original=self.pending.path.read_bytes();self.path=self.folder/('result-'+self.request['id']+'.json')
        self.result={k:self.request[k] for k in ('id','session','operation')}
        self.result.update(schema=1,phase='failed',error='rollback uncertain',result_unknown=True,probe_version='0.3.43',
                           execution_exit={'schema':1,'engine':'uxp-modal','exited':True})
    def tearDown(self):self.temp.cleanup()
    def write(self,value=None):self.path.write_text(json.dumps(self.result if value is None else value),'utf-8')
    def assert_preserved(self):
        self.assertEqual(self.pending.path.read_bytes(),self.original)
        self.assertIsNone(self.pending.read_result());self.assertTrue(self.pending.snapshot()['active'])
    def test_modern_exit_releases_input_evidence_but_never_confirms_content(self):
        self.write();raw=self.path.read_bytes();self.assertTrue(self.pending.execution_has_exited())
        self.assert_preserved();self.assertEqual(raw,self.path.read_bytes())
        self.assertTrue(self.pending.snapshot()['execution_exited'])
        self.assertIn('PS可正常使用',self.pending.snapshot()['message'])
        restored=PendingUxp(self.pending.path,self.storage);self.assertTrue(restored.execution_has_exited())
        self.assertIsNotNone(restored.value)
    def test_missing_accepted_malformed_old_and_other_original_records_do_not_release(self):
        values=[{},dict(self.result,phase='accepted'),dict(self.result,probe_version='0.3.42')]
        values += [dict(self.result,**{k:'other'}) for k in ('id','session','operation')]
        values += [dict(self.result,execution_exit=m) for m in (None,{},True,
                    {'schema':True,'engine':'uxp-modal','exited':True},
                    {'schema':1,'engine':'uxp-modal','exited':1},
                    {'schema':1,'engine':'standalone-extendscript','exited':True},
                    {'schema':1,'engine':'uxp-modal','exited':False})]
        # A boolean exited flag must not accept integer lookalikes.
        for value in values:
            self.write(value);self.assertFalse(self.pending.execution_has_exited(),value)
        self.assertEqual(self.pending.path.read_bytes(),self.original)
    def test_legacy_normal_com_return_preserves_uncertain_original_result(self):
        self.pending.value['preview_command']='shape.legacy.preview';self.result.pop('execution_exit');self.write()
        self.assertFalse(self.pending.execution_has_exited())
        self.assertFalse(self.pending.execution_has_exited(1))
        self.assertTrue(self.pending.execution_has_exited(True))
        self.assertIsNotNone(self.pending.value);self.assertIsNone(self.pending.read_result())
    def test_receipt_written_inside_jsx_before_com_return_is_insufficient(self):
        self.pending.value['preview_command']='shape.legacy.preview'
        (self.folder/('legacy-result-'+self.request['id']+'.json')).write_text(json.dumps(self.result),'utf-8')
        self.assertFalse(self.pending.execution_has_exited());self.assertFalse(self.pending.execution_has_exited())
    def test_legacy_normal_return_does_not_wait_for_metadata_receipt(self):
        self.pending.value['preview_command']='shape.legacy.preview'
        self.assertFalse(self.path.exists());self.assertTrue(self.pending.execution_has_exited(True))
        self.assertIsNotNone(self.pending.value);self.assertEqual(self.pending.path.read_bytes(),self.original)
    def test_no_execution_evidence_for_unrelated_operation_or_corrupt_proof(self):
        self.write();self.pending.value.pop('preview_command');self.assertFalse(self.pending.execution_has_exited(True))
        self.pending.value['preview_command']='shape.preview'
        file=self.root/('uxp-execution-exit-'+self.request['id']+'.json');file.write_text('{')
        self.path.unlink();self.assertFalse(self.pending.execution_has_exited())
    def test_failed_proof_storage_does_not_release_or_clear_unknown(self):
        self.write()
        with patch('backend.settings.atomic_json',side_effect=OSError('disk unavailable')):
            self.assertFalse(self.pending.execution_has_exited())
        self.assertEqual(self.pending.path.read_bytes(),self.original)
    def test_concurrent_status_and_execution_observers_publish_one_bound_proof(self):
        from concurrent.futures import ThreadPoolExecutor
        from backend.settings import atomic_json
        self.write()
        with patch('backend.settings.atomic_json',wraps=atomic_json) as publication:
            with ThreadPoolExecutor(max_workers=8) as pool:
                self.assertTrue(all(pool.map(lambda _:self.pending.execution_has_exited(),range(32))))
        self.assertEqual(publication.call_count,1);self.assert_preserved()
    def test_normally_returned_native_json_is_bound_to_exact_original_and_token(self):
        native={**self.request,'schema':1,'phase':'failed','result_unknown':True}
        self.assertTrue(returned_result(json.dumps(native),self.request))
        for key in ('id','session','operation','token'):
            self.assertFalse(returned_result(json.dumps({**native,key:'other'}),self.request))
        for raw in (None,'bad','[]',json.dumps({**native,'phase':'accepted'})):
            self.assertFalse(returned_result(raw,self.request))
    def test_exit_check_survives_closing_preview_without_ps_or_new_requests(self):
        p=MaskPreview(7,paint());p.execution_check=lambda:self.pending.execution_has_exited()
        p.cancel();p.close();self.assertFalse(p.execution_finished());self.write()
        self.assertTrue(p.execution_finished());self.assert_preserved()


class PreviewExitGuardTests(unittest.TestCase):
    def test_host_exit_releases_guard_even_while_metadata_worker_is_waiting(self):
        from tests.test_preview_input_guard import PreviewInputGuardTests
        d,_=PreviewInputGuardTests().desktop();p=MaskPreview(9,paint());d.mask_preview=p
        exited=[False];p.execution_check=lambda:exited[0];d.prepare_preview_input_guard(p)
        d.maintain_preview_input_guard();self.assertIsNotNone(d.preview_input_guard)
        exited[0]=True;d.maintain_preview_input_guard();self.assertIsNone(d.preview_input_guard)
        self.assertTrue(p.execution_exited);self.assertFalse(p.update(paint(42)))
    def test_exited_unknown_releases_native_guard_and_indicator_only_after_ack(self):
        from tests.test_preview_input_guard import PreviewInputGuardTests
        d,p=PreviewInputGuardTests().desktop();d.prepare_preview_input_guard(p);exited=[False]
        d.finish_preview_input_guard(p,False,lambda:exited[0]);d.maintain_preview_input_guard()
        self.assertTrue(d.preview_input_guard['unknown'])
        exited[0]=True;d.native_applied_sequence=0
        with patch.object(d.native_applied,'wait_for',return_value=False):d.maintain_preview_input_guard()
        self.assertTrue(d.preview_input_guard['release']);self.assertNotIn('unknown',d.preview_input_guard)
        d.native_applied_sequence=7;d.maintain_preview_input_guard();self.assertIsNone(d.preview_input_guard)
    def test_no_running_indicator_after_exit_even_if_plugin_outcome_is_pending(self):
        from tests.test_mask_preview import PreviewPendingFeedbackTests
        d=PreviewPendingFeedbackTests().desktop();d.mask_preview.cancel();d.preview_pending_feedback()
        self.assertTrue(d._send_menu_event.call_args.args[0]['active'])
        d.mask_preview.execution_exited=True;d.preview_pending_feedback()
        self.assertFalse(d._send_menu_event.call_args.args[0]['active'])
