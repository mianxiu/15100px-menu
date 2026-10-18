"""Hover return confirms one preview; withdrawn followups never execute."""
import asyncio,json,unittest
from types import SimpleNamespace
from unittest.mock import Mock
from backend.mask_preview import MaskPreview,dispatch_preview
from backend.uxp_bridge import UxpBridge
from tests.test_mask_preview import paint

class PreviewReturnTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self,mode='ok'):
        events=[];gate=asyncio.Event();guards=[];calls=[]
        pending=SimpleNamespace(value=None,error=None,execution_has_exited=lambda:False)
        d=SimpleNamespace(menu_epoch=7,visible=True,color_editor_active=True,preview_input_guard=None,
            menu_layer_context={'session':'s','document_id':3,'layer_ids':[4],'shape_editor':{'live_preview':True}},
            _scope=lambda:True,event=events.append,require_menu_layer_target=Mock(),require_action_focus=Mock())
        def arm(p):d.preview_input_guard={'preview':p};guards.append('arm')
        def finish(p,known,check):
            guards.append(('finish',known));d.preview_input_guard=None if known else d.preview_input_guard
        d.prepare_preview_input_guard=arm;d.finish_preview_input_guard=finish;d.finish_preview_focus=Mock()
        def hide(restore=True):d.visible=False;d.mask_preview.cancel()
        d.hide=hide
        b=object.__new__(UxpBridge);b.busy=False;b.layer_context={};b.transport=SimpleNamespace(pending=pending)
        async def shape(params,**kw):
            await kw['before_dispatch'](kw['frozen_target']);await gate.wait();p=kw['preview'];calls.append(dict(p.paint))
            if mode=='unknown':b.busy=True;raise RuntimeError('unknown original request')
            if mode=='closed':d.visible=False
            if mode=='reopen':d.menu_epoch+=1
            if mode=='failure':raise RuntimeError('target changed')
            p.execution_exited=True
            return {'message':'confirmed','result':json.dumps({'verified':mode!='unverified','cancelled':mode=='cancelled'})}
        b.execute_shape=shape;b.execute=Mock(side_effect=AssertionError('No followup allowed'))
        async def broadcast(e):events.append(e)
        app=SimpleNamespace(bridge=b,desktop=d,operation_lock=asyncio.Lock(),require_uxp_enabled=lambda:None,
            photoshop_launcher=SimpleNamespace(active=False),broadcast=broadcast)
        await dispatch_preview(app,'mask.preview.update',{'menu_epoch':7,'params':paint(1)})
        await dispatch_preview(app,'mask.preview.commit',{'menu_epoch':7,'params':paint(9,50),'return_to_menu':True})
        self.assertTrue(d.visible)
        with self.assertRaises(RuntimeError):
            await dispatch_preview(app,'mask.preview.commit',{'menu_epoch':7,'params':paint(99),'return_to_menu':True})
        gate.set();await app._mask_preview_task
        return calls,events,guards,b,app

    async def test_returns_only_after_verified_original_result_and_guard_release(self):
        calls,events,guards,b,app=await self.exercise()
        self.assertEqual(len(calls),1);self.assertEqual(calls[0]['mask'],{'feather':9,'density':50})
        self.assertTrue(app.desktop.visible);self.assertIsNone(app.desktop.preview_input_guard)
        self.assertEqual(guards,['arm',('finish',True)])
        self.assertEqual(sum(e.get('type')=='preview.menu.confirmed' for e in events),1)
        self.assertFalse(app.operation_lock.locked());self.assertIsNone(app._mask_preview);b.execute.assert_not_called()

    async def test_failure_unknown_cancel_and_unverified_receipts_never_resume(self):
        for mode in ('failure','unknown','cancelled','unverified'):
            with self.subTest(mode=mode):
                calls,events,guards,b,app=await self.exercise(mode)
                self.assertFalse(any(e.get('type')=='preview.menu.confirmed' for e in events));b.execute.assert_not_called()
                self.assertFalse(app.desktop.visible)
                if mode=='unknown':self.assertTrue(b.busy);self.assertIsNotNone(app.desktop.preview_input_guard)

    async def test_closed_or_reopened_menu_cannot_be_resurrected(self):
        for mode in ('closed','reopen'):
            calls,events,guards,b,app=await self.exercise(mode)
            self.assertFalse(any(e.get('type')=='preview.menu.confirmed' for e in events));b.execute.assert_not_called()

    async def test_withdrawn_after_action_is_rejected_without_claiming_or_hiding(self):
        app=SimpleNamespace(bridge=object.__new__(UxpBridge),desktop=SimpleNamespace(menu_epoch=7),_mask_preview=MaskPreview(7,paint()))
        before=app._mask_preview.seq
        for action in ('moveUp','moveDown','moveToTop','moveToBottom','copyStyle'):
            with self.assertRaises(ValueError):await dispatch_preview(app,'mask.preview.commit',{'menu_epoch':7,'params':paint(9),'after_action':action})
        self.assertEqual(app._mask_preview.seq,before);self.assertEqual(app._mask_preview.phase,'preview')

    async def test_return_requires_a_bool_and_commit(self):
        p=MaskPreview(7,paint())
        for value in (1,[],None,'true'):
            with self.assertRaises(ValueError):p.update(paint(2),commit=True,return_to_menu=value)
        with self.assertRaises(ValueError):p.update(paint(2),return_to_menu=True)
        self.assertEqual(p.seq,1);self.assertFalse(p.return_to_menu)

class PreviewReturnWireTests(unittest.TestCase):
    def test_native_event_retains_return_intent_and_latest_draft(self):
        from backend.desktop import Desktop
        d=object.__new__(Desktop);d.process=None;d.menu_epoch=7;d.notify=Mock()
        draft=paint(9,50);event={'type':'action','action':'mask.preview.commit','session':7,'params':draft,'return_to_menu':True}
        d._menu_events(SimpleNamespace(stdout=[json.dumps(event)]))
        d.notify.assert_called_once_with({'action':'mask.preview.commit','menu_epoch':7,'params':draft,'return_to_menu':True})

    def test_heartbeat_cannot_end_return_feedback_before_guard_release(self):
        from backend.desktop import Desktop
        d=object.__new__(Desktop);d.menu_epoch=7;d._send_menu_event=Mock()
        p=MaskPreview(7,paint());p.update(paint(9),commit=True,return_to_menu=True);d.mask_preview=p
        d.event({'type':'operation','busy':False});self.assertTrue(d._send_menu_event.call_args.args[0]['busy'])
        original={'type':'status','data':{'photoshop':{'busy':False}}};d.event(original)
        self.assertTrue(d._send_menu_event.call_args.args[0]['data']['photoshop']['busy']);self.assertFalse(original['data']['photoshop']['busy'])
        p.close();d.event({'type':'operation','busy':False});self.assertFalse(d._send_menu_event.call_args.args[0]['busy'])
