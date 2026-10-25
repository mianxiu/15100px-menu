import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from backend.input_tool import ToolObservation
from backend.settings import atomic_json


class ToolObservationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.folder=self.root/'plugin';self.folder.mkdir()
        config=self.root/'uxp-config.json';atomic_json(config,{'token':'private-test-token'})
        self.heartbeat={'probe_version':'0.3.66','session':'owned-session'}
        self.reader=ToolObservation(SimpleNamespace(config=config,observe=lambda:(self.folder,self.heartbeat)))

    def pending(self,**changes):
        value={'schema':1,'id':'a'*32,'session':'owned-session','expires_at_ms':time.time()*1000+1000,**changes}
        atomic_json(self.reader.path,value);return value

    def reply(self,request,**changes):
        atomic_json(self.folder/'input-tool-response.json',{
            'schema':1,'id':request['id'],'session':request['session'],'token':'private-test-token',
            'phase':'completed','classID':'typeCreateOrEditTool','isModal':False,
            'completed_at_ms':time.time()*1000,**changes})

    def test_matched_idle_and_editing_tool_responses_consume_only_original_identity(self):
        for modal in (False,True):
            original=self.pending();self.reply(original,isModal=modal)
            self.assertEqual(self.reader.read(),{'classID':'typeCreateOrEditTool','isModal':modal})
            self.assertFalse(self.reader.path.exists())
            self.assertFalse((self.folder/'input-tool-request.json').exists(),'Original observation must never be republished')

    def test_new_request_is_authenticated_and_identity_is_saved_before_publication(self):
        from backend.input_tool import atomic_json as write
        from backend.input_tool import publish_request as rename
        rows=[]
        def save(path,value):rows.append(value.get('publication'));write(path,value)
        def publish(temporary,destination):
            value=json.loads(temporary.read_text('utf-8'));rows.append('request')
            pending=json.loads(self.reader.path.read_text());self.assertEqual(pending['publication'],'prepared');self.assertNotIn('token',pending)
            self.assertEqual(value['token'],'private-test-token');self.assertEqual(value['schema'],1)
            rename(temporary,destination);self.reply(value)
        with patch('backend.input_tool.atomic_json',side_effect=save),patch('backend.input_tool.publish_request',side_effect=publish):self.reader.read()
        self.assertEqual(rows,['prepared','request','published'])

    def test_failed_publication_archives_before_release_and_never_waits_for_host(self):
        error=PermissionError('sharing');error.winerror=32
        with patch('backend.input_tool.publish_request',side_effect=error):
            with self.assertRaisesRegex(RuntimeError,'未发布'):self.reader.read()
        self.assertFalse(self.reader.path.exists());self.assertFalse((self.folder/'input-tool-request.json').exists())
        archive=list(self.root.glob('input-tool-unpublished-*.json'));self.assertEqual(len(archive),1)
        record=json.loads(archive[0].read_text());self.assertFalse(record['host_request_published']);self.assertEqual(record['request']['publication'],'prepared')
        self.assertIsNotNone(self.reader.retry_after)

    def test_sharing_retry_keeps_one_identity_and_one_envelope(self):
        import os
        real=os.replace;attempts=[]
        error=PermissionError('sharing');error.winerror=32
        def replace(source,destination):
            if Path(destination).name=='input-tool-request.json':
                value=json.loads(Path(source).read_text('utf-8'));attempts.append(value)
                if len(attempts)<3:raise error
                result=real(source,destination);self.reply(value);return result
            return real(source,destination)
        with patch('backend.uxp_bridge.os.replace',side_effect=replace):self.reader.read()
        self.assertEqual(len(attempts),3);self.assertTrue(all(row==attempts[0] for row in attempts))
        self.assertFalse(self.reader.path.exists());self.assertFalse(list(self.root.glob('input-tool-unpublished-*.json')))

    def test_archive_failure_keeps_unpublished_identity_and_does_not_claim_exit(self):
        from backend.input_tool import atomic_json as write
        def save(path,value):
            if 'unpublished-' in path.name:raise OSError('archive failed')
            write(path,value)
        with patch('backend.input_tool.atomic_json',side_effect=save),patch('backend.input_tool.publish_request',side_effect=PermissionError('sharing')):
            with self.assertRaises(OSError):self.reader.read()
        self.assertEqual(json.loads(self.reader.path.read_text())['publication'],'prepared')

    def test_readonly_reconcile_consumes_only_matching_terminal_and_never_publishes(self):
        original=self.pending();self.reply(original,id='b'*32)
        with patch('backend.input_tool.publish_request') as publish:
            self.assertFalse(self.reader.reconcile());publish.assert_not_called();self.assertTrue(self.reader.path.exists())
            self.reply(original,completed_at_ms=time.time()*1000-2000)
            self.assertTrue(self.reader.reconcile());publish.assert_not_called();self.assertFalse(self.reader.path.exists())

    def test_prepared_after_publication_crash_is_not_republished(self):
        original=self.pending(schema=2,publication='prepared');self.reply(original)
        with patch('backend.input_tool.publish_request') as publish:
            self.assertEqual(self.reader.read()['classID'],'typeCreateOrEditTool');publish.assert_not_called()

    def test_unknown_wrong_id_token_and_session_are_never_republished(self):
        for changes in ({'id':'b'*32},{'token':'other'},{'session':'other'}):
            original=self.pending();self.reply(original,**changes);before=self.reader.path.read_bytes()
            with patch('backend.input_tool.time.monotonic',side_effect=[0,1]),self.assertRaisesRegex(RuntimeError,'不重发'):
                self.reader.read()
            self.assertEqual(self.reader.path.read_bytes(),before)
            self.assertFalse((self.folder/'input-tool-request.json').exists())

    def test_malformed_authenticated_response_keeps_pending_identity(self):
        for changes in ({'completed_at_ms':float('nan')},{'completed_at_ms':True},{'classID':None},{'isModal':0},{'phase':'running'}):
            original=self.pending();self.reply(original,**changes);before=self.reader.path.read_bytes()
            with self.assertRaises(RuntimeError):self.reader.read()
            self.assertEqual(self.reader.path.read_bytes(),before)

    def test_failed_or_stale_trusted_terminal_is_consumed_but_cannot_grant_eng(self):
        for changes in ({'phase':'failed'},{'completed_at_ms':time.time()*1000-2000}):
            original=self.pending();self.reply(original,**changes)
            with self.assertRaisesRegex(RuntimeError,'失败／失鲜'):self.reader.read()
            self.assertFalse(self.reader.path.exists())

    def test_old_executor_changed_session_and_damaged_pending_never_publish(self):
        self.heartbeat['probe_version']='0.3.65'
        with self.assertRaisesRegex(RuntimeError,'0.3.66'):self.reader.read()
        self.heartbeat['probe_version']='0.3.66'
        self.pending(session='previous-session')
        with self.assertRaisesRegex(RuntimeError,'会话变化'):self.reader.read()
        for value in ([],{'schema':1},{**self.pending(),'expires_at_ms':float('inf')}):
            atomic_json(self.reader.path,value)
            with self.assertRaisesRegex(RuntimeError,'身份损坏'):self.reader.read()
        self.assertFalse((self.folder/'input-tool-request.json').exists())
