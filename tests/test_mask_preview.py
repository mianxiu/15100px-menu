import json
import tempfile
import threading
import unittest
import asyncio
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

from backend.mask_preview import MaskPreview
from backend.mask_preview import dispatch_preview
from backend.uxp_bridge import UxpBridge


def paint(feather=0, density=100):
    return {'revision':'test:1','fill':{'kind':'solid','enabled':True,'rgb':[12,34,56]},
            'stroke':{'kind':'solid','enabled':False,'rgb':[0,0,0],'width':1},
            'mask':{'feather':feather,'density':density}}


class MaskPreviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder=Path(self.temporary.name)
        self.request={'id':'a'*32,'session':'test-session','token':'local-only'}
        self.path=self.folder/('mask-preview-'+self.request['id']+'.json')

    def test_coalesces_updates_and_binds_identity(self):
        preview=MaskPreview(8,paint());preview.bind(self.folder,self.request)
        for i in range(1,1001):preview.update(paint(i,50))
        preview.publish()
        value=json.loads(self.path.read_text('utf-8'))
        self.assertEqual(value['seq'],1001)
        self.assertEqual(value['paint']['mask'],{'feather':1000,'density':50})
        self.assertEqual({k:value[k] for k in self.request},self.request)
        self.assertEqual([p.name for p in self.folder.iterdir()],[self.path.name])

    def test_terminal_commit_cannot_be_replaced_or_cancelled(self):
        preview=MaskPreview(8,paint());preview.bind(self.folder,self.request)
        preview.update(paint(25,40),commit=True)
        self.assertFalse(preview.update(paint(90,10)))
        preview.cancel();preview.publish()
        value=json.loads(self.path.read_text('utf-8'))
        self.assertEqual(value['phase'],'commit')
        self.assertEqual(value['paint']['mask'],{'feather':25,'density':40})

    def test_cancel_never_accepts_later_release(self):
        preview=MaskPreview(8,paint());preview.bind(self.folder,self.request)
        preview.cancel()
        self.assertFalse(preview.update(paint(70,20),commit=True))
        preview.publish();self.assertEqual(json.loads(self.path.read_text())['phase'],'cancel')

    def test_old_revision_and_invalid_values_rejected(self):
        preview=MaskPreview(8,paint())
        for value in ({**paint(),'revision':'other'},paint(1001),paint(0,-1)):
            with self.assertRaises(ValueError):preview.update(value)
        plain={k:v for k,v in paint().items() if k!='mask'}
        preview=MaskPreview(8,plain)
        preview.update({**plain,'fill':{'kind':'solid','enabled':True,'rgb':[99,88,77]}})
        with self.assertRaises(ValueError):preview.update(paint())

    def test_slow_publication_does_not_block_cancel_or_overwrite_terminal(self):
        preview=MaskPreview(8,paint());entered=threading.Event();release=threading.Event()
        from backend.uxp_bridge import publish_request
        def delayed(temporary,destination):
            entered.set();self.assertTrue(release.wait(2));publish_request(temporary,destination)
        with patch('backend.uxp_bridge.publish_request',delayed):
            writer=threading.Thread(target=preview.bind,args=(self.folder,self.request));writer.start()
            try:
                self.assertTrue(entered.wait(2))
                preview.cancel()
                self.assertEqual(preview.phase,'cancel')
            finally:release.set();writer.join(2)
        preview.publish()
        self.assertEqual(json.loads(self.path.read_text())['phase'],'cancel')

    def test_progress_is_bound_bounded_monotonic_and_presentation_only(self):
        preview=MaskPreview(8,paint());preview.bind(self.folder,self.request)
        path=self.folder/('preview-progress-'+self.request['id']+'.json')
        base={**self.request,'serial':1,'stage':'write','done':3,'total':8,'frame':1}
        path.write_text(json.dumps(base),'utf-8')
        value=preview.progress();self.assertEqual(value['done'],3)
        with patch.object(Path,'read_text',side_effect=AssertionError('UI close must use cached feedback')):
            self.assertEqual(preview.progress(read=False)['done'],3)
        self.assertFalse(set(self.request)&set(value))
        for invalid in ({**base,'session':'old','serial':9},{**base,'serial':0,'done':1},
                        {**base,'serial':4,'done':9},{**base,'serial':5,'total':999},[],None,{'serial':8}):
            path.write_text(json.dumps(invalid),'utf-8')
            self.assertEqual(preview.progress()['done'],3)
        path.write_text('{"incomplete":','utf-8');self.assertEqual(preview.progress()['done'],3)
        preview.cancel();self.assertEqual(preview.progress()['stage'],'cancel-wait')
        path.write_text(json.dumps({**base,'serial':2,'stage':'restore-verify','done':2}),'utf-8')
        self.assertEqual(preview.progress()['stage'],'restore-verify')
        self.assertEqual(preview.phase,'cancel');self.assertEqual(preview.seq,2)
        preview.close();self.assertIsNone(preview.progress())


    def test_reopened_busy_menu_receives_original_request_progress(self):
        from backend.desktop import Desktop
        import io
        desktop=Desktop('http://localhost',lambda action:None);desktop.menu_epoch=9
        desktop.mask_preview=MaskPreview(8,paint());desktop.mask_preview.cancel()
        desktop.process=SimpleNamespace(poll=lambda:None,stdin=io.StringIO())
        desktop.event(desktop.mask_preview.progress())
        result=json.loads(desktop.process.stdin.getvalue())
        self.assertEqual(result['epoch'],9);self.assertEqual(result['stage'],'cancel-wait')
        self.assertEqual(desktop.mask_preview.epoch,8)



class PreviewDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self,reopen):
        focus=threading.Event();entered=threading.Event();calls=[];events=[]
        desktop=SimpleNamespace(menu_epoch=7,visible=True,color_editor_active=True,
            menu_layer_context={'session':'s','document_id':3,'layer_ids':[4],'shape_editor':{'live_preview':True}},
            _scope=lambda:True,event=events.append,require_menu_layer_target=lambda *_:None)
        def require_focus():entered.set();self.assertTrue(focus.wait(2))
        desktop.require_action_focus=require_focus
        def hide(restore=True):
            desktop.visible=False
            if getattr(desktop,'mask_preview',None):desktop.mask_preview.cancel()
        desktop.hide=hide
        bridge=object.__new__(UxpBridge);bridge.busy=False;bridge.layer_context={}
        async def execute(params,**kw):
            await kw['before_dispatch'](kw['frozen_target']);calls.append(copy_value(kw['preview'].paint))
            if reopen:desktop.menu_epoch=8;desktop.visible=True
            return {'message':'confirmed'}
        bridge.execute_shape=execute
        async def broadcast(event):events.append(event)
        app=SimpleNamespace(bridge=bridge,desktop=desktop,operation_lock=asyncio.Lock(),
                            require_uxp_enabled=lambda:None,photoshop_launcher=SimpleNamespace(active=False),broadcast=broadcast)
        await dispatch_preview(app,'mask.preview.update',{'menu_epoch':7,'params':paint(1)})
        self.assertTrue(app.operation_lock.locked())
        await dispatch_preview(app,'mask.preview.update',{'menu_epoch':7,'params':paint(10)})
        await dispatch_preview(app,'mask.preview.commit',{'menu_epoch':7,'params':paint(25,40)})
        focus.set();await app._mask_preview_task
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0]['mask'],{'feather':25,'density':40})
        self.assertFalse(app.operation_lock.locked())
        self.assertIsNone(app._mask_preview)
        self.assertEqual(desktop.visible,reopen)

    async def test_draft_only_menu_rejects_live_event_before_reserving_or_starting_task(self):
        for capability in (False,None):
            desktop=SimpleNamespace(menu_epoch=7,visible=True,color_editor_active=True,
                menu_layer_context={'session':'s','document_id':3,'layer_ids':[4],'shape_editor':{'live_preview':capability}})
            bridge=object.__new__(UxpBridge);bridge.busy=False
            app=SimpleNamespace(bridge=bridge,desktop=desktop,operation_lock=asyncio.Lock(),
                require_uxp_enabled=lambda:None,photoshop_launcher=SimpleNamespace(active=False))
            with self.assertRaisesRegex(RuntimeError,'本地草稿'):
                await dispatch_preview(app,'mask.preview.update',{'menu_epoch':7,'params':paint(1)})
            self.assertFalse(app.operation_lock.locked());self.assertIsNone(getattr(app,'_mask_preview',None))

    async def test_early_updates_and_release_share_reserved_transaction(self):
        await self.exercise(False)

    async def test_completion_does_not_hide_newly_opened_busy_menu(self):
        await self.exercise(True)


def copy_value(value):return json.loads(json.dumps(value))


if __name__=='__main__':unittest.main()
