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
        rows=[]
        def publish(path,value):
            rows.append(Path(path).name);write(path,value)
            if path.name=='input-tool-request.json':
                self.assertTrue(self.reader.path.exists());self.assertNotIn('token',json.loads(self.reader.path.read_text()))
                self.assertEqual(value['token'],'private-test-token');self.reply(value)
        with patch('backend.input_tool.atomic_json',side_effect=publish):self.reader.read()
        self.assertEqual(rows,['input-tool-pending.json','input-tool-request.json'])

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
