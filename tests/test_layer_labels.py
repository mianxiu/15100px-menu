import unittest
from unittest.mock import Mock

from backend.layer_labels import LABEL_COLORS, LABEL_ACTIONS, label_script
from backend.photoshop_bridge import PhotoshopBridge


class LabelTests(unittest.IsolatedAsyncioTestCase):
    async def test_clear_reports_parent_color_instead_of_generic_success(self):
        bridge = PhotoshopBridge()
        bridge._execute = lambda action: '{"verified":true,"count":2,"inherited":1}'
        try:
            result = await bridge.execute('label.none')
            self.assertIn('清除 2 个图层', result['message'])
            self.assertIn('父组仍有颜色', result['message'])
        finally:
            await bridge.close()

    async def test_each_label_executes_on_serial_bridge_and_survives_script_package_switch(self):
        bridge = PhotoshopBridge()
        app = Mock()
        app.Documents.Count = 2
        app.DoJavaScript.return_value = '{"verified":true,"count":2,"inherited":0}'
        bridge._application = lambda: app
        bridge.replace_scripts({'color': 'custom orange script'})
        try:
            for color in LABEL_COLORS:
                name = 'label.' + color['id']
                result = await bridge.execute(name)
                self.assertIn('无颜色' if color['id']=='none' else color['label'], result['message'])
                app.DoJavaScript.assert_called_with(label_script(name))
            self.assertEqual(app.DoJavaScript.call_count, 8)
        finally:
            await bridge.close()

    async def test_label_respects_focus_no_document_and_busy_guards(self):
        bridge = PhotoshopBridge()
        app = Mock()
        app.Documents.Count = 0
        bridge._application = lambda: app
        try:
            with self.assertRaisesRegex(ValueError, '打开文档'):
                await bridge.execute('label.red')
            app.Documents.Count = 1
            bridge.focus_guard = Mock(side_effect=RuntimeError('input focused'))
            with self.assertRaisesRegex(RuntimeError, 'input focused'):
                await bridge.execute('label.red')
            bridge.busy = True
            with self.assertRaisesRegex(RuntimeError, '尚未完成'):
                await bridge.execute('label.red')
            app.DoJavaScript.assert_not_called()
        finally:
            bridge.busy = False
            await bridge.close()

    def test_only_known_enum_values_can_be_inserted_into_jsx(self):
        self.assertEqual(len(LABEL_ACTIONS), 8)
        for invalid in ('label', 'label.green', 'label.red);alert(1)', None):
            with self.assertRaises(ValueError):
                label_script(invalid)
