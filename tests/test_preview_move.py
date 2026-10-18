"""A single explicit commit-and-move gesture keeps both task boundaries."""
import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from backend.mask_preview import MaskPreview,dispatch_preview
from backend.uxp_bridge import UxpBridge
from tests.test_mask_preview import paint

class PreviewMoveTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self,mode='ok',name='moveUp'):
        calls=[];events=[];gate=asyncio.Event();guards=[]
        pending=SimpleNamespace(value=None,error=None,execution_has_exited=lambda:False)
        d=SimpleNamespace(menu_epoch=7,visible=True,color_editor_active=True,preview_input_guard=None,
            menu_layer_context={'session':'s','document_id':3,'layer_ids':[4],'shape_editor':{'live_preview':True}},
            _scope=lambda:True,event=events.append,require_menu_layer_target=Mock(),require_move_context=Mock())
        focus=[0]
        def require_focus():
            focus[0]+=1
            if mode=='foreign' and focus[0]>1:raise RuntimeError('foreign foreground')
        d.require_action_focus=require_focus;d.finish_preview_focus=Mock()
        def arm(p):guards.append(('arm',p.execution_exited));d.preview_input_guard={'preview':p}
        def finish(p,known,check):guards.append(('finish',known));d.preview_input_guard=None if known else d.preview_input_guard
        d.prepare_preview_input_guard=arm;d.finish_preview_input_guard=finish
        def hide(restore=True):d.visible=False;d.mask_preview.cancel()
        d.hide=hide
        b=object.__new__(UxpBridge);b.busy=False;b.layer_context={};b.transport=SimpleNamespace(pending=pending)
        async def shape(params,**kw):
            await kw['before_dispatch'](kw['frozen_target']);await gate.wait();p=kw['preview']
            if mode=='shape-unknown':b.busy=True;raise RuntimeError('unknown first request')
            if mode=='reopen':d.menu_epoch+=1
            p.execution_exited=True;p.execution_check=lambda:True
            calls.append(('paint',dict(p.paint)))
            return {'message':'confirmed','result':json.dumps({'verified':True,'cancelled':mode=='cancelled'})}
        async def move(action,**kw):
            self.assertTrue(app.operation_lock.locked());self.assertFalse(d.mask_preview.execution_exited)
            self.assertFalse(d.mask_preview.execution_finished(),'Must not reuse the first exit marker')
            await kw['before_dispatch'](kw['frozen_target']);calls.append((action,kw['frozen_target']))
            if mode=='move-unknown':
                b.busy=True;pending.value={'id':'new-move','session':'s','task_id':'new-task'};raise RuntimeError('unknown move')
            return {'message':'moved','result':'{}'}
        b.execute_shape=shape;b.execute=move
        async def broadcast(e):events.append(e)
        app=SimpleNamespace(bridge=b,desktop=d,operation_lock=asyncio.Lock(),require_uxp_enabled=lambda:None,
            photoshop_launcher=SimpleNamespace(active=False),broadcast=broadcast)
        await dispatch_preview(app,'mask.preview.update',{'menu_epoch':7,'params':paint(1)})
        await dispatch_preview(app,'mask.preview.commit',{'menu_epoch':7,'params':paint(9,50),'after_action':name})
        with self.assertRaises(RuntimeError):
            await dispatch_preview(app,'mask.preview.commit',{'menu_epoch':7,'params':paint(99),'after_action':'moveDown'})
        gate.set();await app._mask_preview_task
        return calls,events,guards,b,app

    async def test_four_moves_commit_latest_values_once_before_frozen_target_move(self):
        for name in ('moveToTop','moveToBottom','moveUp','moveDown'):
            with self.subTest(name=name):
                calls,events,guards,b,app=await self.exercise(name=name)
                self.assertEqual([x[0] for x in calls],['paint',name]);self.assertEqual(calls[0][1]['mask'],{'feather':9,'density':50})
                self.assertEqual(calls[1][1],{'session':'s','document_id':3,'layer_ids':[4],'active_layer_id':4})
                self.assertEqual([x[0] for x in guards],['arm','arm','finish']);self.assertTrue(guards[-1][1])
                self.assertFalse(app.operation_lock.locked());self.assertIsNone(app._mask_preview)
                self.assertTrue(any(e.get('stage')=='move' for e in events))

    async def test_cancel_unknown_foreign_and_reopened_session_never_move(self):
        for mode in ('cancelled','shape-unknown','foreign','reopen'):
            with self.subTest(mode=mode):
                calls,events,guards,b,app=await self.exercise(mode)
                self.assertFalse(any(x[0] in ('moveUp','moveDown') for x in calls))
                self.assertTrue(any(e.get('type')=='notice' and not e.get('ok',True) for e in events))

    async def test_second_unknown_retains_new_guard_and_request_identity(self):
        calls,events,guards,b,app=await self.exercise('move-unknown')
        self.assertEqual([x[0] for x in calls],['paint','moveUp']);self.assertEqual(guards[-1],('finish',False))
        self.assertTrue(b.busy);self.assertEqual(b.transport.pending.value['id'],'new-move')
        self.assertIsNotNone(app.desktop.preview_input_guard)

    async def test_update_cannot_claim_a_followup_and_invalid_action_does_not_mutate(self):
        p=MaskPreview(7,paint());before=p.seq
        for action in ('copyStyle','shape.paint','',[],1):
            with self.assertRaises(ValueError):p.update(paint(3),commit=True,after_action=action)
        with self.assertRaises(ValueError):p.update(paint(3),after_action='moveUp')
        self.assertEqual(p.seq,before);self.assertEqual(p.phase,'preview');self.assertIsNone(p.after_action)

class PreviewMoveWireTests(unittest.TestCase):
    def test_native_event_preserves_the_one_explicit_followup_and_draft(self):
        from backend.desktop import Desktop
        d=object.__new__(Desktop);d.process=None;d.menu_epoch=7;d.notify=Mock()
        draft=paint(9,50);event={'type':'action','action':'mask.preview.commit','session':7,'params':draft,'after_action':'moveUp'}
        d._menu_events(SimpleNamespace(stdout=[json.dumps(event)]))
        d.notify.assert_called_once_with({'action':'mask.preview.commit','menu_epoch':7,'params':draft,'after_action':'moveUp'})

    def test_first_task_completion_cannot_clear_the_compound_busy_indicator(self):
        from backend.desktop import Desktop
        d=object.__new__(Desktop);d.menu_epoch=7;d._send_menu_event=Mock()
        p=MaskPreview(7,paint());p.update(paint(9),commit=True,after_action='moveUp');d.mask_preview=p
        d.event({'type':'operation','busy':False});self.assertTrue(d._send_menu_event.call_args.args[0]['busy'])
        original={'type':'status','data':{'photoshop':{'busy':False}}};d.event(original)
        self.assertTrue(d._send_menu_event.call_args.args[0]['data']['photoshop']['busy']);self.assertFalse(original['data']['photoshop']['busy'])
        p.close();d.event({'type':'operation','busy':False});self.assertFalse(d._send_menu_event.call_args.args[0]['busy'])
