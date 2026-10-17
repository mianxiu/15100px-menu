import asyncio,json,tempfile,unittest,time
from pathlib import Path
from unittest.mock import Mock,patch
from backend.uxp_bridge import UxpBridge,UxpResultUnknown,UxpTransport,publish_request,read_heartbeat

class UxpPublicationTests(unittest.TestCase):
    def test_partial_heartbeat_recovers_before_single_menu_publication(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as base:
            root=Path(base);bridge=UxpBridge(root/'tasks.json',root/'config.json')
            bridge.transport=SimpleNamespace(folder=root,config=root/'config.json')
            bridge.transport.config.write_text(json.dumps({'token':'a'*64}),'utf-8')
            heartbeat=root/'probe-last.json';heartbeat.write_text('','utf-8')
            def finish_overwrite(_):heartbeat.write_text('{"session":"new-session","probe_version":"0.3.21"}','utf-8')
            try:
                with patch('backend.uxp_bridge.time.sleep',side_effect=finish_overwrite) as pause,patch('backend.uxp_bridge.publish_request',wraps=publish_request) as publish:
                    result=bridge.request_menu_context(9)
                request=json.loads((root/'menu-context-request.json').read_text('utf-8'))
                self.assertEqual(request['session'],'new-session');self.assertEqual(result['session'],'new-session')
                self.assertEqual(result['id'],request['id']);self.assertEqual(publish.call_count,1)
                self.assertEqual(pause.call_count,1);self.assertFalse((root/'uxp-pending.json').exists())
            finally:bridge.executor.shutdown(wait=True)

    def test_persistent_partial_heartbeat_is_bounded_and_does_not_publish(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as base:
            root=Path(base);bridge=UxpBridge(root/'tasks.json',root/'config.json')
            bridge.transport=SimpleNamespace(folder=root,config=root/'config.json')
            (root/'probe-last.json').write_text('{','utf-8')
            request=root/'menu-context-request.json';request.write_text('previous','utf-8')
            try:
                with patch('backend.uxp_bridge.time.sleep') as pause,patch('backend.uxp_bridge.publish_request') as publish:
                    with self.assertRaises(json.JSONDecodeError):bridge.request_menu_context(9)
                self.assertEqual(pause.call_count,7);publish.assert_not_called()
                self.assertEqual(request.read_text('utf-8'),'previous');self.assertFalse((root/'uxp-pending.json').exists())
            finally:bridge.executor.shutdown(wait=True)

    def test_heartbeat_valid_has_no_delay_and_only_sharing_errors_retry(self):
        with tempfile.TemporaryDirectory() as base:
            root=Path(base);(root/'probe-last.json').write_text('{"session":"s"}','utf-8')
            with patch('backend.uxp_bridge.time.sleep') as pause:
                self.assertEqual(read_heartbeat(root),{'session':'s'});pause.assert_not_called()
            error=PermissionError('sharing');error.winerror=32
            with patch.object(Path,'read_text',side_effect=[error,'{"session":"current"}']),patch('backend.uxp_bridge.time.sleep') as pause:
                self.assertEqual(read_heartbeat(root),{'session':'current'});pause.assert_called_once_with(.004)
            with patch.object(Path,'read_text',side_effect=PermissionError('denied')),patch('backend.uxp_bridge.time.sleep') as pause:
                with self.assertRaises(PermissionError):read_heartbeat(root)
                pause.assert_not_called()

    def test_menu_request_sharing_retry_keeps_identity_expiry_and_deadline(self):
        from types import SimpleNamespace
        import os
        with tempfile.TemporaryDirectory() as base:
            root=Path(base);bridge=UxpBridge(root/'tasks.json',root/'config.json')
            bridge.transport=SimpleNamespace(folder=root,config=root/'config.json')
            bridge.transport.config.write_text(json.dumps({'token':'a'*64}),'utf-8')
            (root/'probe-last.json').write_text('{"session":"s","probe_version":"0.3.18"}','utf-8')
            original=os.replace;attempts=[];error=PermissionError('read handle');error.winerror=32
            def replace(a,b):
                attempts.append(Path(a).read_bytes())
                if len(attempts)<3:raise error
                return original(a,b)
            try:
                with patch('backend.uxp_bridge.os.replace',side_effect=replace),patch('backend.uxp_bridge.time.monotonic',return_value=10),patch('backend.uxp_bridge.time.time',return_value=100):
                    result=bridge.request_menu_context(7)
                request=json.loads((root/'menu-context-request.json').read_text('utf-8'))
                self.assertEqual(result['id'],request['id']);self.assertEqual(result['deadline'],20)
                self.assertEqual(request['expires_at_ms'],110000)
                self.assertEqual(len(set(attempts)),1);self.assertEqual(result['epoch'],7)
                self.assertFalse(list(root.glob('*.tmp')))
            finally:bridge.executor.shutdown(wait=True)

    def test_failed_menu_request_preserves_previous_and_removes_temp(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as base:
            root=Path(base);bridge=UxpBridge(root/'tasks.json',root/'config.json')
            bridge.transport=SimpleNamespace(folder=root,config=root/'config.json')
            bridge.transport.config.write_text(json.dumps({'token':'a'*64}),'utf-8')
            (root/'probe-last.json').write_text('{"session":"s","probe_version":"0.3.18"}','utf-8')
            request=root/'menu-context-request.json';request.write_bytes(b'previous request')
            try:
                with patch('backend.uxp_bridge.os.replace',side_effect=PermissionError('denied')):
                    with self.assertRaises(PermissionError):bridge.request_menu_context(1)
                self.assertEqual(request.read_bytes(),b'previous request');self.assertFalse(list(root.glob('*.tmp')))
            finally:bridge.executor.shutdown(wait=True)

    def test_read_lock_retry_keeps_same_request_bytes(self):
        with tempfile.TemporaryDirectory() as base:
            source=Path(base)/'one-id.tmp';destination=Path(base)/'probe-request.json'
            source.write_bytes(b'same request id and token')
            error=PermissionError('read handle');error.winerror=5
            import os
            original=os.replace
            def replace(a,b):
                self.assertEqual(a,source)
                self.assertEqual(source.read_bytes(),b'same request id and token')
                if replace.calls<2:replace.calls+=1;raise error
                return original(a,b)
            replace.calls=0
            with patch('backend.uxp_bridge.os.replace',side_effect=replace):publish_request(source,destination)
            self.assertEqual(destination.read_bytes(),b'same request id and token')
            self.assertFalse(source.exists())
    def test_permanent_failure_preserves_old_request_and_removes_temp(self):
        with tempfile.TemporaryDirectory() as base:
            source=Path(base)/'one-id.tmp';destination=Path(base)/'probe-request.json'
            source.write_bytes(b'new');destination.write_bytes(b'old')
            with patch('backend.uxp_bridge.os.replace',side_effect=PermissionError('denied')):
                with self.assertRaises(PermissionError):publish_request(source,destination)
            self.assertEqual(destination.read_bytes(),b'old');self.assertFalse(source.exists())

class UxpDiscoveryTests(unittest.TestCase):
    def test_mask_edit_rejects_old_plugin_before_publication(self):
        folder=self.heartbeat(24)
        heartbeat=json.loads((folder/'probe-last.json').read_text('utf-8'));heartbeat.update(probe_version='0.3.19',session='s')
        (folder/'probe-last.json').write_text(json.dumps(heartbeat),'utf-8')
        self.transport.config.write_text(json.dumps({'token':'a'*64}),'utf-8')
        with self.assertRaisesRegex(RuntimeError,'0.3.20'):
            self.transport.call('set_label',command='shape.paint',paint={'mask':{'feather':0,'density':100}},target={'session':'s'})
        self.assertFalse((folder/'probe-request.json').exists());self.assertIsNone(self.transport.pending.value)
        heartbeat['probe_version']='0.3.26'
        (folder/'probe-last.json').write_text(json.dumps(heartbeat),'utf-8')
        with self.assertRaisesRegex(RuntimeError,'0.3.27'):
            self.transport.call('set_label',preview=object(),command='shape.preview',target={'session':'s'})
        self.assertFalse((folder/'probe-request.json').exists());self.assertIsNone(self.transport.pending.value)
    def test_smart_conversion_rejects_old_plugin_before_publication(self):
        folder=self.heartbeat(24)
        heartbeat=json.loads((folder/'probe-last.json').read_text('utf-8'));heartbeat.update(probe_version='0.3.17',session='s')
        (folder/'probe-last.json').write_text(json.dumps(heartbeat),'utf-8')
        self.transport.config.write_text(json.dumps({'token':'a'*64}),'utf-8')
        with self.assertRaisesRegex(RuntimeError,'0.3.18'):
            self.transport.call('set_label',command='convertSmartObject',target={'session':'s'})
        self.assertFalse((folder/'probe-request.json').exists());self.assertIsNone(self.transport.pending.value)
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.transport=UxpTransport(Path(self.temp.name)/'config.json')
        self.transport.storage=Path(self.temp.name)/'PHSP'
    def tearDown(self):self.temp.cleanup()
    def heartbeat(self,major,age=0):
        folder=self.transport.storage/str(major)/'External/com.15100px.menu.offline-probe/PluginData'
        folder.mkdir(parents=True)
        (folder/'probe-last.json').write_text(json.dumps({'probe_version':'0.3.0','photoshop_version':str(major)+'.0.1','plugin_time_ms':time.time()*1000-age}))
        return folder
    def test_discovers_new_host_and_ignores_stale_old_host(self):
        self.heartbeat(24,60000)
        expected=self.heartbeat(26)
        self.assertEqual(self.transport.folder,expected)
    def test_multiple_hosts_reject_instead_of_choose_wrong_document(self):
        self.heartbeat(24);self.heartbeat(26)
        with self.assertRaises(RuntimeError):_ = self.transport.folder
    def test_missing_or_future_heartbeat_not_ready(self):
        with self.assertRaises(RuntimeError):_ = self.transport.folder
        self.heartbeat(24,-60000)
        with self.assertRaises(RuntimeError):_ = self.transport.folder

    def test_older_running_host_is_rejected(self):
        self.heartbeat(23)
        with self.assertRaisesRegex(RuntimeError,'24.0.1'):_ = self.transport.folder

class UxpBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.bridge=UxpBridge(task_history=Path(self.temp.name)/'tasks.json')
        self.target={'session':'test','document_id':1,'active_layer_id':2,'layer_ids':[2]}
        self.bridge.transport=Mock()
        self.bridge.transport.call.side_effect=lambda op,**kw: {'target':self.target} if op=='capture' else {'result':{'count':1,'verified':True}}
        self.bridge._application=Mock(side_effect=AssertionError('COM writes forbidden'))
    async def asyncTearDown(self):
        await self.bridge.close();self.temp.cleanup()
    async def test_all_menu_actions_use_uxp(self):
        for action in ('label.red','label.none','color','select','moveToTop','moveToBottom'):
            result=await self.bridge.execute(action)
            self.assertEqual(result['target']['session'],'test')
            self.assertEqual(self.bridge.tasks.get(result['task_id'])['channel'],'uxp-local-files')
        self.bridge._application.assert_not_called()
    async def test_busy_rejects_even_when_enqueue_requested(self):
        self.bridge.busy=True
        with self.assertRaises(RuntimeError):await self.bridge.execute('label.red',enqueue=True)
        self.bridge.transport.call.assert_not_called()
    async def test_frozen_single_menu_uses_one_mutation_and_same_target(self):
        result=await self.bridge.execute('layer.new',frozen_target=self.target)
        self.assertEqual(result['target']['active_layer_id'],2)
        self.assertEqual(self.bridge.transport.call.call_count,1)
        self.assertEqual(self.bridge.transport.call.call_args.args,('set_label',))
        self.assertEqual(self.bridge.transport.call.call_args.kwargs['target'],self.target)
    async def test_frozen_target_invalid_or_busy_never_publishes(self):
        with self.assertRaises(ValueError):await self.bridge.execute('layer.new',frozen_target={**self.target,'layer_ids':[2,3]})
        self.bridge.busy=True
        with self.assertRaises(RuntimeError):await self.bridge.execute('layer.new',frozen_target=self.target)
        self.bridge.transport.call.assert_not_called()
    async def test_confirmed_creation_publishes_new_selection_before_next_task(self):
        def call(op,**kw):
            anchor=kw['target']['active_layer_id']
            new=anchor+1
            return {'result':{'count':1,'verified':True,'layer_id':new},
                'layer_context':{'schema':1,'session':'test','document_id':1,
                    'layer_ids':[new],'kind':'pixel','mask':11,'quick_mask':127,
                    'plugin_time_ms':time.time()*1000}}
        self.bridge.transport.call.side_effect=call
        target=self.target
        for expected in (3,4):
            await self.bridge.execute('layer.new',frozen_target=target)
            self.assertFalse(self.bridge.busy)
            self.assertEqual(self.bridge.layer_context['layer_ids'],[expected])
            target={**self.target,'layer_ids':[expected],'active_layer_id':expected}
        self.assertEqual(self.bridge.transport.call.call_count,2)
    async def test_mismatched_receipt_context_cannot_retain_old_selection(self):
        self.bridge.layer_context={'kind':'pixel','layer_ids':[2],'mask':15}
        self.bridge.transport.call.return_value={'result':{'count':1,'verified':True}}
        self.bridge.transport.call.side_effect=None
        await self.bridge.execute('layer.new',frozen_target=self.target)
        self.assertEqual(self.bridge.layer_context['kind'],'unknown')
        self.assertEqual(self.bridge.layer_context['mask'],0)
    async def test_unknown_keeps_service_busy_no_fallback(self):
        def call(op,**kw):
            if op=='capture':return {'target':self.target}
            raise UxpResultUnknown('unknown')
        self.bridge.transport.call.side_effect=call
        with self.assertRaises(RuntimeError):await self.bridge.execute('label.red')
        await asyncio.sleep(0)
        self.assertTrue(self.bridge.busy)
        self.assertEqual(self.bridge.tasks.snapshot()['items'][0]['state'],'result-unknown')
        with self.assertRaises(RuntimeError):await self.bridge.execute('label.blue')
