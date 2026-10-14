import json,time,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from backend.uxp_bridge import UxpBridge

class UxpStatusObservationTests(unittest.IsolatedAsyncioTestCase):
    async def test_heartbeat_observes_preferences_and_document_without_com(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);bridge=UxpBridge(root/'tasks.json',root/'uxp-config.json')
            bridge.transport=SimpleNamespace(folder=root)
            bridge._application=Mock(side_effect=AssertionError('COM must not be used with a ready heartbeat'))
            (root/'probe-last.json').write_text(json.dumps({'document_name':'shape.psd','ui_theme':'light-gray',
                'ui_font_size':'large','plugin_time_ms':time.time()*1000}),'utf-8')
            try:
                for _ in range(10):
                    value=bridge._status()
                    self.assertTrue(value['connected']);self.assertEqual(value['document'],'shape.psd')
                    self.assertEqual(value['ui_theme'],'light-gray');self.assertEqual(value['ui_font_size'],'large')
                bridge._application.assert_not_called()
            finally:await bridge.close()

    async def test_missing_plugin_fallback_does_not_execute_jsx(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);bridge=UxpBridge(root/'tasks.json',root/'uxp-config.json')
            bridge.transport=SimpleNamespace(folder=root)
            app=SimpleNamespace(Documents=SimpleNamespace(Count=1),ActiveDocument=SimpleNamespace(Name='fallback.psd'),
                DoJavaScript=Mock(side_effect=AssertionError('Status must not execute JSX')))
            bridge._application=Mock(return_value=app)
            try:
                for _ in range(10):self.assertEqual(bridge._status()['document'],'fallback.psd')
                app.DoJavaScript.assert_not_called()
                bridge._application.side_effect=RuntimeError('Photoshop closed')
                self.assertFalse(bridge._status()['connected'])
            finally:await bridge.close()
