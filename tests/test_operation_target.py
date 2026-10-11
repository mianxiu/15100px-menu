import asyncio
import json
import threading
import unittest
from unittest.mock import Mock

from backend.operation_target import CAPTURE_SCRIPT, validate_target, guarded_script
from backend.photoshop_bridge import PhotoshopBridge


class TargetTests(unittest.IsolatedAsyncioTestCase):
    def test_rejects_incomplete_or_unselected_active_target(self):
        for target in (None, {}, {'document_id':1,'active_layer_id':3,'layer_ids':[2]},
                       {'document_id':1,'active_layer_id':2,'layer_ids':[2,2]},
                       {'document_id':True,'active_layer_id':2,'layer_ids':[2]}):
            with self.assertRaises(ValueError):validate_target(target)

    async def test_capture_precedes_handoff_and_reuses_original_com_reference(self):
        bridge=PhotoshopBridge()
        app=Mock();app.Documents.Count=1
        target={'document_id':10,'active_layer_id':22,'layer_ids':[23,22]}
        app.DoJavaScript.side_effect=lambda script: json.dumps(target) if script==CAPTURE_SCRIPT else 'done'
        bridge._application=Mock(return_value=app)
        async def handoff(captured):
            self.assertEqual(captured['layer_ids'],[22,23])
            self.assertTrue(bridge.busy)
            self.assertEqual(app.DoJavaScript.call_count,1)
            bridge._application=Mock(side_effect=AssertionError('Must not reconnect to another instance'))
        try:
            result=await bridge.execute('color',before_dispatch=handoff)
            self.assertEqual(result['target']['document_id'],10)
            app.DoJavaScript.assert_called_with(guarded_script(bridge.scripts['color'],target))
        finally:await bridge.close()

    async def test_failed_handoff_never_dispatches_modification_and_releases_busy(self):
        bridge=PhotoshopBridge()
        bridge._capture_target=Mock(return_value={'document_id':1,'active_layer_id':2,'layer_ids':[2]})
        bridge._execute=Mock(side_effect=AssertionError('No write permitted'))
        async def handoff(target):raise RuntimeError('菜单已重新打开')
        try:
            with self.assertRaisesRegex(RuntimeError,'重新打开'):
                await bridge.execute('color',before_dispatch=handoff)
            bridge._execute.assert_not_called()
            self.assertFalse(bridge.busy)
        finally:await bridge.close()

    async def test_invalid_snapshot_never_hides_menu_or_writes(self):
        bridge=PhotoshopBridge()
        app=Mock();app.Documents.Count=1;app.DoJavaScript.return_value='{}'
        bridge._application=Mock(return_value=app)
        handoff=Mock()
        try:
            with self.assertRaises(ValueError):await bridge.execute('color',before_dispatch=handoff)
            handoff.assert_not_called()
            self.assertEqual(app.DoJavaScript.call_count,1)
            self.assertFalse(bridge.busy)
        finally:await bridge.close()

    async def test_cancelled_capture_keeps_busy_until_read_finishes_without_write(self):
        bridge=PhotoshopBridge();started=threading.Event();release=threading.Event()
        def capture():
            started.set();release.wait(3)
            return {'document_id':1,'active_layer_id':2,'layer_ids':[2]}
        bridge._capture_target=capture;bridge._execute=Mock()
        task=asyncio.create_task(bridge.execute('color'))
        try:
            self.assertTrue(await asyncio.to_thread(started.wait,2))
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
            self.assertTrue(bridge.busy)
            release.set()
            for _ in range(100):
                if not bridge.busy:break
                await asyncio.sleep(.01)
            self.assertFalse(bridge.busy)
            bridge._execute.assert_not_called()
        finally:
            release.set();await bridge.close()
