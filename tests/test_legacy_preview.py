import json,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from backend.uxp_bridge import UxpTransport,UxpResultUnknown
from backend.legacy_preview import invoke


class LegacyTransportTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
  self.transport=UxpTransport(self.root/'config.json');self.transport.storage=self.root/'PHSP'
  self.transport.pending.storage=self.transport.storage;self.transport.task_id='a'*32
  self.folder=self.transport.storage/'24/External/com.15100px.menu.offline-probe/PluginData';self.folder.mkdir(parents=True)
  self.transport.config.write_text(json.dumps({'token':'t'*64}),'utf-8')
  self.heartbeat={'session':'session','probe_version':'0.3.43','photoshop_version':'24.0.1','legacy_preview_available':True,'document_redraw_available':False,'plugin_time_ms':time.time()*1000}
  self.save_heartbeat();self.preview=SimpleNamespace(bind=Mock(),trace=False)
 def tearDown(self):self.temp.cleanup()
 def save_heartbeat(self):(self.folder/'probe-last.json').write_text(json.dumps(self.heartbeat),'utf-8')
 def publish(self,source,dest):
  self.request=json.loads(source.read_text('utf-8'));source.replace(dest)
  self.ready={k:self.request[k] for k in ('id','session','operation','token')}
  self.ready.update(schema=1,phase='prepared',prepared={'before':{}})
  (self.folder/('legacy-prepared-'+self.request['id']+'.json')).write_text(json.dumps(self.ready),'utf-8')
 def finish(self,request):
  result={k:request[k] for k in ('id','session','operation')};result.update(schema=1,phase='completed',result={'verified':True})
  (self.folder/('result-'+request['id']+'.json')).write_text(json.dumps(result),'utf-8')
 def call(self,native):return self.transport.call('set_label',preview=self.preview,native_preview=native,command='shape.legacy.preview',target={'session':'session'})
 def test_bound_native_runs_once_after_prepare_and_retains_pending_until_history_saved(self):
  native=Mock(side_effect=lambda folder,request,ready:self.finish(request))
  with patch('backend.uxp_bridge.publish_request',side_effect=self.publish) as publish,patch('backend.uxp_management.photoshop_running',return_value=True):result=self.call(native)
  self.assertEqual(native.call_count,1);self.assertEqual(publish.call_count,1);self.assertTrue(result['result']['verified'])
  self.assertEqual(self.transport.pending.value['id'],result['id']);self.preview.bind.assert_called_once()
 def test_2400_executor44_prepares_once_then_runs_bound_native(self):
  self.heartbeat.update(photoshop_version='24.0.0',probe_version='0.3.44');self.save_heartbeat()
  native=Mock(side_effect=lambda folder,request,ready:self.finish(request))
  with patch('backend.uxp_bridge.publish_request',side_effect=self.publish) as publish:
   result=self.call(native)
  self.assertTrue(result['result']['verified']);publish.assert_called_once();native.assert_called_once()
  self.assertEqual(self.request['command'],'shape.legacy.preview')
  self.assertEqual(self.request['target'],{'session':'session'})
  self.assertEqual(self.transport.pending.value['id'],result['id'])
 def test_2400_missing_capabilities_never_publishes_or_invokes_native(self):
  self.heartbeat.update(photoshop_version='24.0.0',probe_version='0.3.44')
  for changes in ({'legacy_preview_available':False},{'legacy_preview_available':None},
                  {'document_redraw_available':True},{'document_redraw_available':None},
                  {'probe_version':'0.3.43'}):
   before=dict(self.heartbeat);self.heartbeat.update(changes);self.save_heartbeat();native=Mock()
   with patch('backend.uxp_bridge.publish_request') as publish:
    with self.assertRaisesRegex(RuntimeError,'未就绪'):self.call(native)
   publish.assert_not_called();native.assert_not_called()
   self.assertIsNone(self.transport.pending.value);self.heartbeat=before
 def test_final_receipt_precedes_native_invocation_and_host_check(self):
  def publish(source,dest):self.publish(source,dest);self.finish(self.request)
  native=Mock()
  with patch('backend.uxp_bridge.publish_request',side_effect=publish),patch('backend.uxp_management.photoshop_running',return_value=False) as presence:self.call(native)
  native.assert_not_called();presence.assert_not_called()
 def test_mismatched_prepare_never_invokes_native_and_keeps_original_pending(self):
  def publish(source,dest):
   self.publish(source,dest);self.ready['session']='other';(self.folder/('legacy-prepared-'+self.request['id']+'.json')).write_text(json.dumps(self.ready),'utf-8')
  native=Mock()
  with patch('backend.uxp_bridge.publish_request',side_effect=publish),patch('backend.uxp_management.photoshop_running',return_value=False):
   with self.assertRaises(UxpResultUnknown):self.call(native)
  native.assert_not_called();self.assertIsNotNone(self.transport.pending.value)
 def test_native_com_error_does_not_override_already_persisted_original_terminal(self):
  def native(folder,request,ready):self.finish(request);raise OSError('COM return channel failed')
  callback=Mock(side_effect=native)
  with patch('backend.uxp_bridge.publish_request',side_effect=self.publish),patch('backend.uxp_management.photoshop_running',return_value=False):result=self.call(callback)
  self.assertTrue(result['result']['verified']);self.assertEqual(callback.call_count,1)
 def test_native_error_without_terminal_is_unknown_and_never_retried(self):
  callback=Mock(side_effect=OSError('COM disconnected'));tick=[0]
  def clock():tick[0]+=1;return tick[0]
  with patch('backend.uxp_bridge.publish_request',side_effect=self.publish),patch('backend.uxp_management.photoshop_running',return_value=True),patch('backend.uxp_bridge.time.monotonic',side_effect=clock),patch('backend.uxp_bridge.time.sleep'):
   with self.assertRaises(UxpResultUnknown):self.call(callback)
  self.assertEqual(callback.call_count,1);self.assertIsNotNone(self.transport.pending.value)
 def test_old_plugin_modern_host_and_missing_capability_reject_before_publication(self):
  for changes in ({'probe_version':'0.3.31'},{'probe_version':'0.3.42'},{'photoshop_version':'24.2.0'},{'photoshop_version':'23.3.0'},{'photoshop_version':'24.0.0'},{'document_redraw_available':True},{'legacy_preview_available':False}):
   before=dict(self.heartbeat);self.heartbeat.update(changes);self.save_heartbeat()
   with self.assertRaisesRegex(RuntimeError,'未就绪|0.3.43'):self.call(Mock())
   self.assertIsNone(self.transport.pending.value);self.assertFalse((self.folder/'probe-request.json').exists());self.heartbeat=before
 def test_prepare_identity_rejected_before_com_and_unicode_is_data(self):
  request={'id':'a'*32,'session':'s','operation':'set_label','token':'t','paint':{'name':'quote"\\\u2028'}}
  ready={**request,'phase':'prepared','prepared':{}};app=Mock()
  invoke(app,self.folder,request,ready)
  script=app.DoJavaScript.call_args.args[0];self.assertIn('\\u2028',script);self.assertNotIn('__PS_MENU_LEGACY_REQUEST__',script)
  ready['session']='changed'
  with self.assertRaises(ValueError):invoke(app,self.folder,request,ready)
  self.assertEqual(app.DoJavaScript.call_count,1)
 def test_unknown_rollback_with_normal_native_return_proves_exit_without_clearing_pending(self):
  def native(folder,request,ready):
   result={k:request[k] for k in ('id','session','operation')};result.update(schema=1,phase='failed',error='rollback uncertain',result_unknown=True)
   (folder/('result-'+request['id']+'.json')).write_text(json.dumps(result),'utf-8')
   return json.dumps({**result,'token':request['token']})
  with patch('backend.uxp_bridge.publish_request',side_effect=self.publish):
   with self.assertRaises(UxpResultUnknown):self.call(native)
  original=self.transport.pending.path.read_bytes();self.assertTrue(self.preview.execution_check())
  self.assertIsNone(self.transport.pending.read_result());self.assertEqual(original,self.transport.pending.path.read_bytes())
  self.transport.pending.value={**self.transport.pending.value,'id':'c'*32}
  self.assertFalse(self.preview.execution_check(),'An old callback cannot attest a later request')
 def test_native_com_exception_with_original_unknown_receipt_does_not_claim_exit(self):
  def native(folder,request,ready):
   result={k:request[k] for k in ('id','session','operation')};result.update(schema=1,phase='failed',error='rollback uncertain',result_unknown=True)
   (folder/('result-'+request['id']+'.json')).write_text(json.dumps(result),'utf-8')
   raise OSError('COM channel failed')
  with patch('backend.uxp_bridge.publish_request',side_effect=self.publish):
   with self.assertRaises(UxpResultUnknown):self.call(native)
  self.assertFalse(self.preview.execution_check());self.assertIsNotNone(self.transport.pending.value)
