import unittest
from unittest.mock import Mock
from backend.layer_context import require_menu_target
from backend.tasks import TaskCancelled
from backend.uxp_bridge import UxpBridge
from backend.commands import validate_command

class PaintClipboardTests(unittest.IsolatedAsyncioTestCase):
    def context(self,ids=(2,),vector=True):
        return {'session':'s','document_id':1,'layer_ids':list(ids),'kind':'shape-fill','locked':False,'background':False,
                'shape_editor':{'available':True,'vector':vector,**({'mask_batch':True,'layer_ids':list(ids),'active_layer_id':ids[0]} if len(ids)>1 else {})}}

    def test_single_copy_requires_available_shape(self):
        context=self.context();require_menu_target(context,'shape.copyPaint',context)
        for value in (self.context(vector=False),self.context((2,3)),{**context,'locked':True}):
            with self.assertRaises(TaskCancelled):require_menu_target(value,'shape.copyPaint',value)

    def test_batch_paste_accepts_frozen_mask_selection(self):
        context=self.context((2,3));require_menu_target(context,'shape.pastePaint',context)
        with self.assertRaises(TaskCancelled):require_menu_target(context,'shape.pastePaint',{**context,'layer_ids':[2]})

    def test_ordinary_fill_cannot_receive_shape_paint(self):
        context=self.context(vector=False)
        with self.assertRaises(TaskCancelled):require_menu_target(context,'shape.pastePaint',context)

    def test_no_arbitrary_clipboard_payload(self):
        for name in ('shape.copyPaint','shape.pastePaint'):
            self.assertEqual(validate_command(name).channel,'uxp-local-files')
            with self.assertRaises(ValueError):validate_command(name,{'script':'anything'})

    async def test_batch_target_not_collapsed_to_single(self):
        bridge=object.__new__(UxpBridge);bridge.execution_guard=None;bridge.focus_guard=Mock()
        async def task(action,before_dispatch,capture):return capture()
        bridge._execute_task=task
        original={'session':'s','document_id':1,'active_layer_id':3,'layer_ids':[2,3]}
        result=await bridge.execute('shape.pastePaint',frozen_target=original)
        self.assertEqual(result['layer_ids'],[2,3]);self.assertEqual(result['active_layer_id'],3)
        self.assertEqual(original['layer_ids'],[2,3]);bridge.focus_guard.assert_called_once()

    async def test_single_copy_still_uses_single_binding(self):
        bridge=object.__new__(UxpBridge);bridge.execution_guard=None;bridge.focus_guard=Mock()
        async def task(action,before_dispatch,capture):return capture()
        bridge._execute_task=task
        result=await bridge.execute('shape.copyPaint',frozen_target={'session':'s','document_id':1,'active_layer_id':2,'layer_ids':[2]})
        self.assertEqual(result['layer_ids'],[2]);self.assertEqual(result['session'],'s')
