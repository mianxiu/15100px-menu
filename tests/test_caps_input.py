import copy,json,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from backend.desktop import Desktop
from backend.settings import Settings,DEFAULTS

class CapsInputTests(unittest.TestCase):
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
