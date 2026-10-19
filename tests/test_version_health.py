import asyncio,copy,json,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from backend.version_health import VersionHealth,assessment


def state():
 return {'version':'0.4.164','photoshop':{'connected':True,'uxp_ready':True,'status_fresh':True,'busy':False,
   'photoshop_version':'25.5.0','uxp_version':'0.3.31','document_redraw_available':True,
   'document':'private-client.psd','uxp_recovery':{'active':False}},
   'uxp':{'enabled':True,'version':'0.3.31','bundled_version':'0.3.31','token':'private-token'},
   'tasks':{'items':[]},'menu':{'visible':False},'photoshop_start':{'active':False}}

class VersionHealthTests(unittest.IsolatedAsyncioTestCase):
 async def test_legacy_execution_capability_does_not_claim_draft_or_full_acceptance(self):
  s=state();s['photoshop'].update(photoshop_version='24.0.1',document_redraw_available=False,legacy_preview_available=True)
  value=await self.check(s);codes={f['code'] for f in value['findings']}
  self.assertIn('legacy_preview_available',codes);self.assertNotIn('legacy_preview_pending',codes)
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name);self.now=100
  self.h=VersionHealth(self.path,clock=lambda:self.now,system='26200.9457')
 async def asyncTearDown(self):
  await self.h.close();self.tmp.cleanup()
 async def check(self,s):
  self.h.observe(s);self.now+=7;self.h.observe(s)
  if self.h.task:await self.h.task
  return self.h.snapshot()
 async def test_first_check_debounces_then_saves_redacted_evidence(self):
  s=state();self.h.observe(s);self.assertIsNone(self.h.task)
  self.now+=3;self.h.observe(s);self.assertIsNone(self.h.task)
  self.now+=4;self.h.observe(s);await self.h.task
  report=await self.h.export();raw=json.dumps(report)
  self.assertNotIn('private-client',raw);self.assertNotIn('private-token',raw)
  self.assertTrue(report['read_only']);self.assertFalse(report['attention'])
  self.assertEqual(report['capabilities']['redraw_document'],True)
 async def test_no_host_and_disabled_plugin_do_not_trigger_probe_or_start_ps(self):
  for s in ({'version':'0.4.164'}, {**state(),'uxp':{'enabled':False}}):
   await self.check(s);self.assertIsNone(self.h.task)
  self.assertFalse(self.h.snapshot()['ready'])
 async def test_same_version_and_restart_do_not_rewrite_or_repeat(self):
  s=state();await self.check(s);first=self.h.state['report_id']
  self.now+=30;self.h.observe(s);self.assertEqual(self.h.state['report_id'],first)
  restored=VersionHealth(self.path,clock=lambda:self.now,system='26200.9457')
  try:
   restored.observe(s);self.now+=9;restored.observe(s);self.assertIsNone(restored.task)
   self.assertEqual(restored.snapshot()['report_id'],first)
  finally:await restored.close()
 async def test_new_versions_defer_while_busy_or_menu_visible_then_report_once(self):
  s=state();await self.check(s);s['photoshop']['photoshop_version']='26.0.0';s['menu']['visible']=True
  old=self.h.task;await self.check(s);self.assertIs(self.h.task,old)
  s['menu']['visible']=False;s['photoshop']['busy']=True;await self.check(s);self.assertIs(self.h.task,old)
  s['photoshop']['busy']=False;self.h.observe(s);await self.h.task
  report=await self.h.export();self.assertEqual(report['changed'],['photoshop'])
 async def test_missing_modern_api_and_loss_are_warnings_not_compatibility_success(self):
  s=state();await self.check(s);s['photoshop']['photoshop_version']='26.1';s['photoshop']['document_redraw_available']=False
  result=await self.check(s);codes=[f['code'] for f in result['findings']]
  self.assertTrue(result['attention']);self.assertIn('redraw_api_missing',codes);self.assertIn('redraw_capability_lost',codes)
  self.assertEqual(result['last_success']['versions']['photoshop'],'25.5.0')
 async def test_documented_floor_is_eligible_but_does_not_claim_preview_support(self):
  s=state();s['photoshop'].update(photoshop_version='23.3.0',document_redraw_available=False,legacy_preview_available=False)
  result=await self.check(s);codes=[f['code'] for f in result['findings']]
  self.assertNotIn('host_version_unsupported',codes);self.assertIn('legacy_preview_pending',codes)

 async def test_old_version_is_explicit_compatibility_draft_not_full_preview_acceptance(self):
  s=state();s['photoshop'].update(photoshop_version='24.0.1',document_redraw_available=False)
  result=await self.check(s);self.assertFalse(result['attention'])
  self.assertIn('legacy_preview_pending',[f['code'] for f in result['findings']])
 async def test_unknown_versions_and_unreported_api_remain_explicit(self):
  s=state();s['photoshop']['photoshop_version']='future-host';result=await self.check(s)
  self.assertTrue(result['attention']);self.assertIn('host_version_unrecognized',[f['code'] for f in result['findings']])
  s=state();s['photoshop'].pop('document_redraw_available');result=await self.check(s)
  self.assertIn('redraw_capability_unreported',[f['code'] for f in result['findings']])
 async def test_plugin_mismatch_and_failed_start_are_captured(self):
  s=state();s['photoshop']['uxp_version']='0.3.30';result=await self.check(s)
  self.assertIn('plugin_reload_required',[f['code'] for f in result['findings']])
  s=state();s['photoshop'].update(uxp_ready=False,connected=False);s['photoshop_start']['phase']='started'
  result=await self.check(s);self.assertIn('plugin_not_ready',[f['code'] for f in result['findings']])
 async def test_unknown_busy_result_is_saved_without_touching_pending_or_running_operation(self):
  p=self.path/'uxp-pending.json';p.write_bytes(b'original unknown request')
  s=state();s['photoshop'].update(busy=True,uxp_recovery={'active':True});s['menu']['visible']=True
  result=await self.check(s);self.assertTrue(result['attention']);self.assertEqual(p.read_bytes(),b'original unknown request')
  self.assertIn('result_unconfirmed',[f['code'] for f in result['findings']])
 async def test_new_failed_task_reopens_notice_after_acknowledgement(self):
  s=state();s['tasks']['items']=[{'id':'first','state':'failed','error':'private-token'}]
  await self.check(s);await self.h.acknowledge();self.assertTrue(self.h.snapshot()['acknowledged'])
  s['tasks']['items'][0]['id']='second';result=await self.check(s)
  self.assertFalse(result['acknowledged']);self.assertNotIn('private-token',json.dumps(await self.h.export()))
 async def test_ack_survives_restart_and_reports_remain_exportable(self):
  await self.check(state());await self.h.acknowledge()
  other=VersionHealth(self.path,system='26200.9457')
  try:self.assertTrue(other.snapshot()['acknowledged']);self.assertEqual((await other.export())['id'],self.h.state['report_id'])
  finally:await other.close()
 async def test_disk_failure_does_not_throw_or_retry_every_poll(self):
  with patch.object(self.h,'_write',side_effect=OSError('disk full')) as write:
   await self.check(state());self.assertTrue(self.h.snapshot()['attention'])
   for _ in range(10):self.now+=3;self.h.observe(state())
   self.assertEqual(write.call_count,1)
 async def test_io_runs_off_event_loop_and_shutdown_finishes_accepted_write(self):
  entered=threading.Event();release=threading.Event();original=self.h._write
  def delayed(*args):entered.set();release.wait(3);original(*args)
  with patch.object(self.h,'_write',side_effect=delayed):
   self.h.observe(state());self.now+=7;self.h.observe(state())
   try:
    await asyncio.wait_for(asyncio.to_thread(entered.wait),1)
    self.assertFalse(self.h.task.done());self.assertEqual(self.h.snapshot()['phase'],'waiting')
    await asyncio.wait_for(asyncio.sleep(.01),.1)
   finally:release.set()
   await self.h.close();self.assertTrue(self.h.snapshot()['ready'])
 async def test_retention_preserves_foreign_files_and_latest_report(self):
  reports=self.path/'version-health/reports';reports.mkdir(parents=True);foreign=reports/'user-file.json';foreign.write_text('keep')
  for i in range(23):
   s=state();s['version']='0.4.'+str(200+i);await self.check(s)
  self.assertEqual(len(list(reports.glob('*.json'))),21);self.assertEqual(foreign.read_text(),'keep')
  self.assertEqual((await self.h.export())['versions']['application'],'0.4.222')
 async def test_corrupt_state_and_report_traversal_do_not_read_outside_owned_folder(self):
  root=self.path/'version-health';root.mkdir();(root/'state.json').write_text('{"schema":1,"report_file":"../secrets.json"}')
  other=VersionHealth(self.path,system='26200.9457')
  try:
   self.assertFalse(other.snapshot()['ready'])
   with self.assertRaises(RuntimeError):await other.export()
  finally:await other.close()
 async def test_error_codes_and_unknown_identity_are_redacted_without_raw_error_text(self):
  s=state();s['photoshop']['uxp_recovery']={'active':True,'request_id':'a'*32,'task_id':'b'*32,'folder':'private-folder','token':'private-token'}
  s['tasks']['items']=[{'id':'b'*32,'state':'result-unknown','error':'private-client.psd secret 0x80070020'}]
  await self.check(s);report=await self.h.export();raw=json.dumps(report)
  self.assertEqual(report['error_codes'],['0x80070020'])
  self.assertEqual(report['original_request'],{'request_id':'a'*32,'task_id':'b'*32})
  for private in ('private-client','private-folder','private-token'):self.assertNotIn(private,raw)
 async def test_acknowledge_cannot_mark_a_new_report_read_during_storage_race(self):
  s=state();await self.check(s)
  await self.h.storage_lock.acquire()
  ack=asyncio.create_task(self.h.acknowledge());await asyncio.sleep(0)
  s['photoshop']['document_redraw_available']=False;self.h.observe(s);self.now+=7;self.h.observe(s)
  self.h.storage_lock.release();await ack;await self.h.task
  self.assertFalse(self.h.snapshot()['acknowledged'])
  restored=VersionHealth(self.path,system='26200.9457')
  try:self.assertFalse(restored.snapshot()['acknowledged'])
  finally:await restored.close()
 async def test_future_malformed_status_does_not_break_status_feed(self):
  self.h.observe({'photoshop':[]});self.assertTrue(self.h.snapshot()['attention'])
  self.now+=7;self.h.observe({'photoshop':[]});await self.h.task
  self.assertIn('status_format_unknown',[f['code'] for f in (await self.h.export())['findings']])
 async def test_full_task_history_cannot_overflow_the_automatic_report(self):
  s=state();s['tasks']['items']=[{'id':str(i).zfill(32),'state':'failed','timeline':[
   {'state':'running','start_elapsed_ms':i,'duration_ms':10,'active':False} for i in range(32)]} for i in range(64)]
  await self.check(s);report=await self.h.export()
  self.assertEqual(len(report['runtime']['tasks']),12)
  self.assertTrue(all(len(row['timeline'])<=8 for row in report['runtime']['tasks']))
 async def test_status_read_failure_produces_bounded_evidence_then_recovers(self):
  result=await self.check({'version':'0.4.164','_status_unavailable':True})
  self.assertIn('status_unavailable',[f['code'] for f in result['findings']])
  result=await self.check(state());self.assertFalse(result['attention'])

if __name__=='__main__':unittest.main()
