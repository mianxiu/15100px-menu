import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from backend.photoshop_theme import THEMES, read_theme, read_font_size
from backend.photoshop_bridge import PhotoshopBridge


class ThemeTests(unittest.IsolatedAsyncioTestCase):
    def test_font_size_and_unavailable_retention(self):
        app = Mock()
        for size in ('small', 'medium', 'large'):
            app.DoJavaScript.return_value = 'FontSize.' + size.upper()
            self.assertEqual(read_font_size(app), size)
        app.DoJavaScript.return_value = 'unknown'
        self.assertEqual(read_font_size(app, 'large'), 'large')
        app.DoJavaScript.side_effect = RuntimeError('modal')
        self.assertEqual(read_font_size(app, 'large'), 'large')

    def test_four_preferences_and_unavailable_preference(self):
        app = Mock()
        for raw, expected in THEMES.items():
            app.DoJavaScript.return_value = raw
            self.assertEqual(read_theme(app), expected)
        app.DoJavaScript.return_value = 'future-unknown-value'
        self.assertEqual(read_theme(app, 'light-gray'), 'light-gray')
        app.DoJavaScript.side_effect = RuntimeError('modal dialog')
        self.assertEqual(read_theme(app, 'light-gray'), 'light-gray')

    async def test_no_document_theme_refresh_busy_and_disconnect_retention(self):
        bridge = PhotoshopBridge()
        app = SimpleNamespace(Documents=SimpleNamespace(Count=0),
                              DoJavaScript=Mock(return_value='kPanelBrightnessLightGray'))
        app.DoJavaScript.side_effect = lambda script: ('FontSize.LARGE' if 'textFontSize' in script
                                                      else app.DoJavaScript.return_value)
        bridge._application = Mock(return_value=app)
        try:
            status = await bridge.status()
            self.assertTrue(status['connected'])
            self.assertIsNone(status['document'])
            self.assertEqual(status['ui_theme'], 'light-gray')
            self.assertEqual(status['ui_font_size'], 'large')
            app.DoJavaScript.return_value = 'kPanelBrightnessMediumGray'
            bridge.busy = True
            self.assertEqual((await bridge.status())['ui_theme'], 'light-gray')
            self.assertEqual(app.DoJavaScript.call_count, 2)
            bridge.busy = False
            self.assertEqual((await bridge.status(force=True))['ui_theme'], 'dark-gray')
            app.DoJavaScript.side_effect = RuntimeError('preference temporarily unavailable')
            self.assertTrue((await bridge.status(force=True))['connected'])
            bridge._application.side_effect = RuntimeError('Photoshop closed')
            status = await bridge.status(force=True)
            self.assertFalse(status['connected'])
            self.assertEqual(status['ui_theme'], 'dark-gray')
            self.assertEqual(status['ui_font_size'], 'large')
        finally:
            await bridge.close()
