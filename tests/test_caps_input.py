import copy,json,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from backend.desktop import Desktop
from backend.settings import Settings,DEFAULTS

class CapsInputTests(unittest.TestCase):
 def test_f5_migrates_to_conversion_and_later_custom_settings_survive(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'settings.json';old=copy.deepcopy(DEFAULTS)
   del old['shortcuts']['convertSmartObject'];old['shortcuts']['color']='f5'
   path.write_text(json.dumps(old),'utf-8');settings=Settings(path);value=settings.get()
   self.assertEqual(value['shortcuts']['convertSmartObject'],'f5');self.assertEqual(value['shortcuts']['color'],'')
   value['shortcuts']['convertSmartObject']='f6';settings.save(value)
   self.assertEqual(Settings(path).get()['shortcuts']['convertSmartObject'],'f6')
 def test_stock_collisions_migrate_and_custom_chords_survive(self):
  old=copy.deepcopy(DEFAULTS);old['shortcuts']={k:old['shortcuts'][k] for k in ('toggle','hide','select','color','moveToTop','moveToBottom')};old['shortcuts'].update(color='capslock+c',moveToTop='capslock+w',moveToBottom='f8')
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'settings.json';path.write_text(json.dumps(old),'utf-8');value=Settings(path).get()['shortcuts']
  self.assertEqual(value['copyStyle'],'capslock+c');self.assertEqual(value['color'],'');self.assertEqual(value['selectAbove'],'capslock+w');self.assertEqual(value['moveToTop'],'');self.assertEqual(value['moveToBottom'],'f8')
 def test_step_shortcuts_removed_from_legacy_load_and_save(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'settings.json';old=copy.deepcopy(DEFAULTS)
   old['shortcuts'].update(moveUp='ctrl+capslock+w',moveDown='ctrl+capslock+s')
   path.write_text(json.dumps(old),'utf-8');settings=Settings(path)
   self.assertEqual(settings.get()['shortcuts']['moveUp'],'')
   self.assertEqual(settings.get()['shortcuts']['moveDown'],'')
   saved=settings.save(old)
   self.assertEqual(saved['shortcuts']['moveUp'],'');self.assertEqual(saved['shortcuts']['moveDown'],'')
   self.assertEqual(saved['shortcuts']['selectAbove'],'capslock+w')
   self.assertEqual(saved['shortcuts']['selectBelow'],'capslock+s')
 def test_shift_selection_bindings_migrate_without_restoring_move_shortcuts(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'settings.json';old=copy.deepcopy(DEFAULTS)
   del old['shortcuts']['extendAbove'];del old['shortcuts']['extendBelow']
   path.write_text(json.dumps(old),'utf-8');value=Settings(path).get()['shortcuts']
   self.assertEqual(value['extendAbove'],'shift+capslock+w');self.assertEqual(value['extendBelow'],'shift+capslock+s')
   self.assertEqual(value['moveUp'],'');self.assertEqual(value['moveDown'],'')
 def test_multi_selection_menu_allows_single_and_shift_navigation_but_not_style_single_commands(self):
  from backend.layer_context import require_menu_target
  from backend.tasks import TaskCancelled
  context={'session':'s','document_id':1,'layer_ids':[2,3],'kind':'mixed'}
  for name in ('selectAbove','selectBelow','extendAbove','extendBelow'):
   require_menu_target(context,name,dict(context))
  for name in ('copyStyle','editStyle'):
   with self.assertRaises(TaskCancelled):require_menu_target(context,name,dict(context))
  with self.assertRaises(TaskCancelled):require_menu_target(context,'extendAbove',{**context,'layer_ids':[3]})
 def ready(self,folder):
  d=Desktop('http://localhost',Mock());d.visible=True;d.hwnd=1;d.menu_epoch=7
  d.menu_context_pending={'id':'test','session':'s','folder':Path(folder),'epoch':7,'deadline':time.monotonic()+3}
  d.panel_context=SimpleNamespace(current={'kind':'layers','input_focused':False});d._scope=Mock(return_value=True);d.gui=SimpleNamespace(SendMessage=Mock(return_value=1));d._native_config=Mock()
  return d
 def result(self,folder,**changes):
  v={'schema':1,'session':'s','menu_request_id':'test','document_id':2,'layer_ids':[3],'mask':15,'quick_mask':127,'kind':'pixel','plugin_time_ms':time.time()*1000,**changes}
  (Path(folder)/'menu-context-result.json').write_text(json.dumps(v),'utf-8')
 def test_only_the_current_menu_request_can_enable_controls(self):
  with tempfile.TemporaryDirectory() as folder:
   d=self.ready(folder);self.result(folder,menu_request_id='previous');d._finish_menu_context();d.gui.SendMessage.assert_not_called()
   self.result(folder);d._finish_menu_context();self.assertEqual(d.menu_layer_context['layer_ids'],[3]);self.assertFalse(d.color_editor_active);self.assertIsNone(d.menu_context_pending)
 def test_input_and_new_menu_epoch_reject_delayed_context(self):
  with tempfile.TemporaryDirectory() as folder:
   d=self.ready(folder);self.result(folder);d.panel_context.current['input_focused']=True;d._finish_menu_context();d.gui.SendMessage.assert_not_called()
   d.menu_epoch=8;d._finish_menu_context();self.assertIsNone(d.menu_context_pending);d.gui.SendMessage.assert_not_called()
 def test_matching_shape_snapshot_enables_editor_without_reusing_old_pixel_identity(self):
  with tempfile.TemporaryDirectory() as folder:
   d=self.ready(folder);d.menu_layer_context={'layer_ids':[99],'kind':'pixel'}
   shape={'available':True,'vector':True,'revision':'s:1','fill':{'kind':'solid','enabled':True,'rgb':[1,2,3]},'stroke':{'kind':'solid','enabled':False,'rgb':[0,0,0],'width':1},'patterns':[]}
   self.result(folder,kind='shape-fill',shape_editor=shape);d._finish_menu_context();self.assertTrue(d.color_editor_active);self.assertEqual(d.menu_layer_context['layer_ids'],[3])
 def large_shape(self):
  return {'available':True,'vector':True,'revision':'s:1','fill':{'kind':'solid','enabled':True,'rgb':[1,2,3]},
   'stroke':{'kind':'solid','enabled':False,'rgb':[0,0,0],'width':1},'patterns':['图案'*64]*128}
 def packet(self,d):
  import ctypes
  class CopyData(ctypes.Structure):
   _fields_=[('tag',ctypes.c_size_t),('size',ctypes.c_ulong),('data',ctypes.c_void_p)]
  packet=ctypes.cast(d.gui.SendMessage.call_args.args[3],ctypes.POINTER(CopyData)).contents
  return packet.size,json.loads(ctypes.string_at(packet.data,packet.size-1))
 def test_maximum_catalog_remains_complete_inside_native_packet_budget(self):
  with tempfile.TemporaryDirectory() as folder:
   d=self.ready(folder);received=[]
   def receive(*args):
    received.append(self.packet(d));return 1
   d.gui.SendMessage.side_effect=receive
   self.result(folder,kind='shape-fill',shape_editor=self.large_shape());d._finish_menu_context()
   size,value=received[0]
   self.assertGreater(size,65536);self.assertLessEqual(size,256*1024)
   self.assertEqual(value['shape']['patterns'],self.large_shape()['patterns'])
   self.assertTrue(d.menu_context_delivery['accepted']);self.assertFalse(d.menu_context_delivery['editor_omitted'])
   self.assertIsNone(d.menu_context_pending);self.assertTrue(d.color_editor_active)
 def test_optional_editor_over_budget_keeps_fresh_basic_actions_usable(self):
  with tempfile.TemporaryDirectory() as folder:
   d=self.ready(folder);received=[]
   def receive(*args):received.append(self.packet(d));return 1
   d.gui.SendMessage.side_effect=receive
   self.result(folder,kind='shape-fill',shape_editor=self.large_shape())
   with patch('backend.desktop.MAX_CONTEXT_PACKET_BYTES',65536):d._finish_menu_context()
   size,value=received[0]
   self.assertLess(size,65536);self.assertEqual(value['shape'],{'available':False})
   self.assertEqual((value['flags']>>8)&15,15);self.assertEqual((value['flags']>>32)&127,127)
   self.assertFalse(d.color_editor_active);self.assertEqual(d.menu_layer_context['layer_ids'],[3])
   self.assertTrue(d.menu_context_delivery['editor_omitted']);self.assertIsNone(d.menu_context_pending)
 def test_native_rejection_does_not_mark_context_applied_or_replace_target(self):
  with tempfile.TemporaryDirectory() as folder:
   d=self.ready(folder);d.menu_layer_context={'layer_ids':[99]};d.gui.SendMessage.return_value=0
   self.result(folder);d._finish_menu_context()
   self.assertEqual(d.menu_layer_context,{'layer_ids':[99]});self.assertIsNotNone(d.menu_context_pending)
   self.assertEqual(d.menu_context_delivery['phase'],'native-rejected');self.assertFalse(d.menu_context_delivery['accepted'])
 def test_basic_capabilities_apply_once_then_matching_paint_can_finish(self):
  with tempfile.TemporaryDirectory() as folder:
   d=self.ready(folder);d.menu_context_pending['deadline']=time.monotonic()+10
   self.result(folder,kind='shape-fill',menu_phase='basic');d._finish_menu_context()
   self.assertEqual(d.menu_layer_context['mask'],15);self.assertFalse(d.color_editor_active)
   d._finish_menu_context();self.assertEqual(d.gui.SendMessage.call_count,1)
   self.result(folder,kind='shape-fill',menu_phase='completed');d._finish_menu_context()
   self.assertIsNone(d.menu_context_pending);self.assertEqual(d.gui.SendMessage.call_count,2)
 def test_accepted_basic_has_bounded_completion_window_without_extending_unaccepted_reads(self):
  with tempfile.TemporaryDirectory() as folder:
   d=self.ready(folder);d.menu_context_pending.update(deadline=110,completion_deadline=130)
   with patch('backend.desktop.time.monotonic',return_value=105):
    self.result(folder,menu_phase='basic');d._finish_menu_context()
   self.assertEqual(d.menu_context_pending['deadline'],130)
   with patch('backend.desktop.time.monotonic',return_value=115):
    self.result(folder,menu_phase='completed');d._finish_menu_context()
   self.assertIsNone(d.menu_context_pending);self.assertEqual(d.gui.SendMessage.call_count,2)
   d=self.ready(folder);d.menu_context_pending.update(deadline=110,completion_deadline=130)
   with patch('backend.desktop.time.monotonic',return_value=115):
    self.result(folder,menu_phase='basic');d._finish_menu_context()
   self.assertIsNone(d.menu_context_pending);d.gui.SendMessage.assert_not_called()
 def test_enrichment_cannot_switch_the_already_frozen_identity(self):
  with tempfile.TemporaryDirectory() as folder:
   d=self.ready(folder);self.result(folder,menu_phase='basic');d._finish_menu_context()
   self.result(folder,menu_phase='completed',layer_ids=[4]);d._finish_menu_context()
   self.assertEqual(d.menu_layer_context['layer_ids'],[3]);self.assertIsNone(d.menu_context_pending)
   self.assertEqual(d.gui.SendMessage.call_count,1)
 def test_slow_current_request_finishes_after_the_old_three_second_limit(self):
  with tempfile.TemporaryDirectory() as folder:
   d=self.ready(folder);d.menu_context_pending['deadline']=time.monotonic()+6
   self.result(folder);d._finish_menu_context();self.assertEqual(d.menu_layer_context['layer_ids'],[3])
 def test_long_lived_shape_draft_is_validated_by_identity_not_menu_age(self):
  from backend.layer_context import require_menu_target
  context={'session':'s','document_id':2,'layer_ids':[3],'kind':'shape-fill','shape_editor':{'available':True},'plugin_time_ms':(time.time()-120)*1000}
  require_menu_target(context,'shape.paint',dict(context))
  with self.assertRaisesRegex(RuntimeError,'已改变'):require_menu_target(context,'shape.paint',{**context,'layer_ids':[4]})
 def test_all_completed_scopes_close_without_selection_reads(self):
  with tempfile.TemporaryDirectory() as folder:
   for scope in ('layers','canvas','generic','home','text'):
    d=self.ready(folder);d.panel_context.current['kind']=scope;d.menu_context_pending=None
    d.hide=Mock();d.menu_context_requester=Mock();d.gui.SendMessage.return_value=1
    d._close_completed_menu();d.hide.assert_called_once_with(restore=True)
    d.menu_context_requester.assert_not_called();self.assertIsNone(d.menu_context_pending)
 def test_completion_close_waits_for_native_result_and_preview_guard(self):
  with tempfile.TemporaryDirectory() as folder:
   d=self.ready(folder);d.hide=Mock();d.gui.SendMessage.return_value=0
   d._close_completed_menu();d.hide.assert_not_called()
   d.gui.SendMessage.return_value=1;d.preview_input_guard={'release':True}
   d._close_completed_menu();d.hide.assert_not_called()
   d.preview_input_guard=None;d.mask_preview=SimpleNamespace(closed=False)
   d._close_completed_menu();d.hide.assert_not_called()
   d.mask_preview.closed=True;d._close_completed_menu();d.hide.assert_called_once_with(restore=True)
 def test_hidden_or_foreign_feedback_never_reopens_or_activates(self):
  with tempfile.TemporaryDirectory() as folder:
   d=self.ready(folder);d.hide=Mock();d.visible=False
   d._close_completed_menu();d.hide.assert_not_called();d.gui.SendMessage.assert_not_called()
   d.visible=True;d._scope.return_value=False;d._close_completed_menu();d.hide.assert_called_once_with(restore=False)
 def test_retired_resume_snapshot_is_dropped_without_epoch_or_host_read(self):
  with tempfile.TemporaryDirectory() as folder:
   d=self.ready(folder);d.menu_context_pending['resume']=True;self.result(folder)
   d._finish_menu_context();self.assertIsNone(d.menu_context_pending);self.assertEqual(d.menu_epoch,7)
   d.gui.SendMessage.assert_not_called()
   d.menu_context_pending={'epoch':7,'unpublished':True,'resume':True};d.menu_context_requester=Mock()
   d._publish_menu_context();d.menu_context_requester.assert_not_called();self.assertIsNone(d.menu_context_pending)

class NativeDialogWaitTests(unittest.IsolatedAsyncioTestCase):
 async def test_style_wait_has_no_generic_write_timeout_and_never_replays(self):
  import asyncio,threading
  from backend.photoshop_bridge import PhotoshopBridge
  with tempfile.TemporaryDirectory() as folder:
   bridge=PhotoshopBridge(task_history=Path(folder)/'tasks.json');bridge.operation_timeout=.1
   bridge._capture_target=lambda:{'document_id':1,'active_layer_id':2,'layer_ids':[2]}
   release=threading.Event();calls=[]
   def write(action):calls.append(action);release.wait(3);return '{"verified":true,"cancelled":true}'
   bridge._execute=write
   task=asyncio.create_task(bridge.execute('editStyle'))
   try:
    await asyncio.sleep(.2);self.assertFalse(task.done());self.assertTrue(bridge.busy)
    with self.assertRaises(RuntimeError):await bridge.execute('pasteStyle')
    release.set();result=await task;self.assertIn('已取消',result['message']);self.assertEqual(calls,['editStyle']);self.assertFalse(bridge.busy)
   finally:release.set();await bridge.close()
 async def test_dialog_api_acknowledges_without_waiting_and_refuses_duplicates(self):
  import asyncio
  from unittest.mock import AsyncMock
  from backend.main import Application
  from backend.uxp_bridge import UxpBridge
  release=asyncio.Event()
  async def dialog(action,args):await release.wait();return {'message':'cancelled'}
  bridge=Mock(spec=UxpBridge);bridge.busy=False
  app=SimpleNamespace(bridge=bridge,operation_lock=asyncio.Lock(),_dialog_tasks=set(),dispatch=AsyncMock(side_effect=dialog))
  reply=await Application.dispatch(app,'action.execute',{'name':'editStyle'})
  self.assertIn('正在打开',reply['message']);self.assertEqual(len(app._dialog_tasks),1)
  with self.assertRaises(RuntimeError):await Application.dispatch(app,'action.execute',{'name':'editStyle'})
  workers=list(app._dialog_tasks);release.set();await asyncio.gather(*workers);await asyncio.sleep(0)
  self.assertFalse(app._dialog_tasks);app.dispatch.assert_awaited_once()
