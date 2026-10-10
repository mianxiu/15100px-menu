import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from backend.document_caption import document_name
from backend.desktop import Desktop


class DocumentCaptionTests(unittest.TestCase):
    def test_names_unicode_zoom_and_embedded_separator(self):
        for title, expected in [
            ('Untitled-1 @ 100% (Background, RGB/8#) *','Untitled-1'),
            ('图层稿.psd @ 66.7% (RGB/8) *','图层稿.psd'),
            ('draft @ home.psd @ 12,5% (RGB/8)','draft @ home.psd'),
        ]:
            self.assertEqual(document_name(title), expected)

    def test_non_document_titles_do_not_replace_com_fallback(self):
        for title in ('Adobe Photoshop', '', 'Save As', 'draft @ home.psd'):
            self.assertIsNone(document_name(title))

    def test_active_floating_document_updates_only_on_change_without_com(self):
        desktop = Desktop('http://localhost', lambda action:None)
        desktop.target = 2
        title = ['first.psd @ 100% (RGB/8)']
        desktop.gui = SimpleNamespace(GetClassName=lambda h:'OWL.DocumentWindow',
                                      GetWindowText=lambda h:title[0])
        desktop.event = Mock()
        with patch('backend.photoshop_windows.workspace_root',return_value=1):
            desktop._refresh_document_name()
            desktop._refresh_document_name()
            title[0] = 'second.psd @ 50% (RGB/8)'
            desktop._refresh_document_name()
        self.assertEqual(desktop.event.call_count, 2)
        self.assertEqual(desktop.event.call_args.args[0], {'type':'document','name':'second.psd'})
