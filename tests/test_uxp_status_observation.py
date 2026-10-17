import json,time,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
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

    async def test_missing_plugin_uses_process_presence_without_com(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);bridge=UxpBridge(root/'tasks.json',root/'uxp-config.json')
            bridge.transport=SimpleNamespace(folder=root)
            bridge._application=Mock(side_effect=AssertionError('Lost UXP must not fall back to COM'))
            try:
                with patch('backend.uxp_management.photoshop_running',return_value=True):
                    for _ in range(10):
                        value=bridge._status()
                        self.assertIsNone(value['document']);self.assertTrue(value['connected'])
                with patch('backend.uxp_management.photoshop_running',return_value=False):
                    self.assertFalse(bridge._status()['connected'])
                bridge._application.assert_not_called()
            finally:await bridge.close()
