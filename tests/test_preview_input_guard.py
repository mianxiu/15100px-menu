import copy
import os
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from backend.desktop import Desktop
from backend.panel_context import PanelContext
from backend.settings import DEFAULTS


class PreviewInputGuardTests(unittest.TestCase):
    def desktop(self):
        d=Desktop('http://localhost',lambda _:None)
        p=SimpleNamespace(epoch=9,closed=False,phase='commit')
        d.mask_preview=p;d.target=41;d._is_photoshop=lambda h:h==41
        d.panel_context=SimpleNamespace(current={'hwnd':12},layer_list_window=Mock(return_value=13))
        d.preview_pending_feedback=Mock()
        d._native_config=Mock(return_value=7);d.native_applied_sequence=7
        return d,p

    def test_guard_requires_verified_list_and_applied_native_configuration(self):
        d,p=self.desktop();d.prepare_preview_input_guard(p)
        self.assertEqual((d.preview_input_guard['owner'],d.preview_input_guard['panel']),(41,13))
        d.panel_context.layer_list_window.assert_called_once_with(12,41)
        for changed in ('list','owner','preview'):
            d,p=self.desktop()
            if changed=='list':d.panel_context.layer_list_window.return_value=0
            elif changed=='owner':d.target=99
            else:d.mask_preview=object()
            with self.assertRaises(RuntimeError):d.prepare_preview_input_guard(p)
            d._native_config.assert_not_called()

    def test_unacknowledged_arm_fails_before_host_work(self):
        d,p=self.desktop();d.native_applied_sequence=0
        with patch.object(d.native_applied,'wait_for',return_value=False):
            with self.assertRaisesRegex(RuntimeError,'未就绪'):d.prepare_preview_input_guard(p)
        self.assertIsNotNone(d.preview_input_guard)
        d.native_applied_sequence=7
        d.finish_preview_input_guard(p)
        self.assertIsNone(d.preview_input_guard)

    def test_known_terminal_waits_for_native_release_before_clearing_feedback(self):
        d,p=self.desktop();d.prepare_preview_input_guard(p);d.native_applied_sequence=0
        with patch.object(d.native_applied,'wait_for',return_value=False):d.finish_preview_input_guard(p)
        self.assertTrue(d.preview_input_guard['release'])
        d.maintain_preview_input_guard();self.assertIsNotNone(d.preview_input_guard)
        d.native_applied_sequence=7;d.maintain_preview_input_guard()
        self.assertIsNone(d.preview_input_guard)

    def test_unknown_original_keeps_guard_until_original_terminal_is_proven(self):
        d,p=self.desktop();d.prepare_preview_input_guard(p);known=[False]
        d.finish_preview_input_guard(p,False,lambda:known[0]);p.closed=True;d.mask_preview=None
        for _ in range(4):d.maintain_preview_input_guard()
        self.assertTrue(d.preview_input_guard['unknown'])
        d.finish_preview_input_guard(object());self.assertIsNotNone(d.preview_input_guard)
        known[0]=True;d.maintain_preview_input_guard();self.assertIsNone(d.preview_input_guard)

    def test_closed_unknown_and_release_have_honest_feedback_without_ps_or_file_reads(self):
        for stage in ('unknown','release'):
            d=Desktop('http://localhost',lambda _:None);d.target=41;d.preview_hint_anchor=[500,300]
            d.mask_preview=None;d._send_menu_event=Mock()
            d.preview_input_guard={'owner':41,'panel':13,'epoch':9,'preview':object(),stage:True}
            with patch('pathlib.Path.read_text',side_effect=AssertionError('No receipt or PS query in feedback')):
                d.preview_pending_feedback()
            v=d._send_menu_event.call_args.args[0]
            self.assertTrue(v['active']);self.assertEqual(v['stage'],stage)
            self.assertEqual((v['epoch'],v['owner']),(9,41))

    @unittest.skipUnless(os.name=='nt','Native applied configuration acknowledgement')
    def test_real_native_config_acknowledges_arm_and_release_without_input(self):
        settings=copy.deepcopy(DEFAULTS);settings['enabled']=False
        d=Desktop('http://localhost',lambda _:None,settings);d.ready=threading.Event()
        d._spawn_native();d.thread=threading.Thread(target=d._native_events,daemon=True);d.thread.start()
        try:
            self.assertTrue(d.ready.wait(5))
            previous=0
            for guard in ({'owner':41,'panel':13,'epoch':9,'preview':object()},None):
                d.preview_input_guard=guard;seq=d._native_config()
                with d.native_applied:self.assertTrue(d.native_applied.wait_for(lambda:d.native_applied_sequence>=seq,2))
                self.assertGreater(seq,previous);previous=seq
        finally:d.close()


class LayerListIdentityTests(unittest.TestCase):
    def detector(self):
        parents={12:11,13:11,14:13,15:16,16:11};classes={12:'Static',11:'OWL.Palette',13:'PSViewC',14:'Static',15:'PSViewC',16:'OWL.Palette'}
        g=SimpleNamespace(GetClassName=lambda h:classes[h],GetParent=lambda h:parents.get(h,41),
            GetDlgCtrlID=lambda h:0,IsWindowVisible=lambda h:True,
            EnumChildWindows=lambda h,fn,_:[fn(x,None) for x in (12,13,14,15)])
        p=PanelContext(g);p.describe=Mock(return_value='layers');return p,g

    def test_only_unique_list_in_frozen_palette_not_nested_other_palette(self):
        p,g=self.detector();self.assertEqual(p.layer_list_window(12,41),13)
        g.GetParent=lambda h:{12:11,13:11,14:13,15:11}.get(h,41)
        self.assertEqual(p.layer_list_window(12,41),0,'Ambiguous lists must fail before dispatch')

    def test_canvas_input_or_hidden_list_cannot_be_a_click_guard(self):
        p,g=self.detector();p.describe.return_value='canvas';self.assertEqual(p.layer_list_window(12,41),0)
        p.describe.return_value='text';self.assertEqual(p.layer_list_window(12,41),0)
        p.describe.return_value='layers';g.IsWindowVisible=lambda h:h!=13
        self.assertEqual(p.layer_list_window(12,41),0)


class GuardDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_guard_never_starts_host_or_replays_a_request(self):
        import asyncio
        from unittest.mock import AsyncMock
        from backend.mask_preview import dispatch_preview
        from backend.uxp_bridge import UxpBridge
        from tests.test_mask_preview import paint
        d=SimpleNamespace(menu_epoch=7,visible=True,color_editor_active=True,
            menu_layer_context={'session':'s','document_id':3,'layer_ids':[4],'shape_editor':{'live_preview':True}},
            require_action_focus=Mock(),prepare_preview_input_guard=Mock(side_effect=RuntimeError('guard unavailable')),
            finish_preview_input_guard=Mock(),event=Mock(),_scope=lambda:True)
        def hide(*_,**__):d.visible=False
        d.hide=hide
        b=object.__new__(UxpBridge);b.busy=False;b.execute_shape=AsyncMock()
        a=SimpleNamespace(desktop=d,bridge=b,operation_lock=asyncio.Lock(),photoshop_launcher=SimpleNamespace(active=False),require_uxp_enabled=lambda:None,broadcast=AsyncMock())
        await dispatch_preview(a,'mask.preview.update',{'menu_epoch':7,'params':paint(1)})
        await a._mask_preview_task
        b.execute_shape.assert_not_called();self.assertFalse(a.operation_lock.locked())
        self.assertIsNone(a._mask_preview);d.finish_preview_input_guard.assert_called_once()
