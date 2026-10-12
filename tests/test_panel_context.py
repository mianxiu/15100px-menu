import unittest
from unittest.mock import Mock
from backend.panel_context import PanelContext, classify_chain, panel_flags


class PanelContextTests(unittest.TestCase):
    def test_visible_menu_freezes_hover_even_if_photoshop_keeps_foreground(self):
        from backend.desktop import Desktop
        from types import SimpleNamespace
        for visible in (True, False):
            desktop = Desktop('http://localhost', lambda action:None)
            desktop.visible = visible
            desktop.target = 10
            desktop.stop = Mock(wait=Mock(side_effect=[False, True]))
            desktop._scope = Mock(return_value=True)
            desktop._is_photoshop = Mock(return_value=True)
            desktop._native_config = Mock()
            desktop.gui = SimpleNamespace(GetForegroundWindow=lambda:10)
            desktop.panel_context = Mock()
            desktop._monitor()
            if visible:
                desktop.panel_context.snapshot.assert_not_called()
            else:
                desktop.panel_context.snapshot.assert_called_once_with(10)

    def test_panel_signatures_and_unknown_palette(self):
        self.assertEqual(classify_chain([('PSViewC',''),('OWL.WelcomeScreenView','')]), 'home')
        self.assertEqual(classify_chain([('Edit',''),('OWL.WelcomeScreenView','')]), 'text')
        self.assertEqual(classify_chain([('PSViewC',''),('OWL.Document','')]), 'canvas')
        self.assertEqual(classify_chain([('PSViewC',''),('OWL.Palette','')],
                                       ['Fill:', 'Lock:', 'Opacity:']), 'layers')
        self.assertEqual(classify_chain([('PSViewC',''),('OWL.Palette','')],
                                       ['填充：', '锁定：', '不透明度：']), 'layers')
        self.assertEqual(classify_chain([('PSViewC',''),('OWL.Palette','')], ['Opacity:']), 'generic')
        self.assertEqual(classify_chain([('Edit',''),('OWL.Palette','')],
                                       ['Fill:', 'Lock:', 'Opacity:']), 'text')

    def detector(self):
        detector = PanelContext(Mock(IsWindow=lambda hwnd: hwnd != 99))
        detector.describe = lambda hwnd, root: {1:'canvas',2:'layers',3:'text'}.get(hwnd,'generic')
        detector.focus_window = Mock(return_value=1)
        detector.hover_window = Mock(return_value=0)
        detector.home_visible = Mock(return_value=False)
        return detector

    def test_home_overrides_retained_canvas_and_palette_but_preserves_input(self):
        detector = self.detector()
        detector.record_click(2, 10)
        detector.hover_window.return_value = 2
        detector.home_visible.return_value = True
        self.assertEqual(detector.snapshot(10)['kind'], 'home')
        detector.focus_window.return_value = 3
        self.assertTrue(detector.snapshot(10)['input_focused'])
        detector.hover_window.return_value = 3
        self.assertEqual(detector.snapshot(10)['kind'], 'text')
        detector.home_visible.return_value = False
        detector.focus_window.return_value = 1
        detector.hover_window.return_value = 1
        self.assertEqual(detector.snapshot(10)['kind'], 'canvas')

    def test_home_protocol_does_not_alias_input_or_layout(self):
        for kind, bits in [('generic',0),('canvas',1),('layers',2),('text',3),('home',32)]:
            self.assertEqual(panel_flags({'kind':kind}), bits)
            self.assertEqual(panel_flags({'kind':kind,'input_focused':True},True,True),bits|4|8|16)

    def test_only_visible_nonempty_welcome_view_marks_home(self):
        gui = Mock()
        gui.EnumChildWindows.side_effect = lambda root, collect, unused: [collect(h,None) for h in (1,2)]
        gui.GetClassName.side_effect = lambda h:'OWL.WelcomeScreenView' if h==2 else 'OWL.Document'
        gui.GetWindowRect.return_value = (0,0,800,600)
        gui.IsWindowVisible.return_value = False
        detector = PanelContext(gui)
        self.assertFalse(detector.home_visible(10))
        gui.IsWindowVisible.return_value = True
        self.assertTrue(detector.home_visible(10))
        gui.GetWindowRect.return_value = (0,0,0,0)
        self.assertFalse(detector.home_visible(10))

    def test_clicked_layers_override_retained_canvas_focus(self):
        detector = self.detector()
        detector.record_click(2, 10)
        self.assertEqual(detector.snapshot(10)['kind'], 'layers')
        self.assertEqual(detector.snapshot(10)['source'], 'last-click')
        detector.record_click(1, 10)
        self.assertEqual(detector.snapshot(10)['kind'], 'canvas')

    def test_real_keyboard_focus_change_and_input_take_priority(self):
        detector = self.detector()
        detector.record_click(2, 10)
        detector.snapshot(10)
        detector.focus_window.return_value = 3
        self.assertEqual(detector.snapshot(10)['kind'], 'text')
        detector.focus_window.return_value = 1
        self.assertEqual(detector.snapshot(10)['kind'], 'canvas')

    def test_foreign_destroyed_and_unknown_click_fall_back(self):
        detector = self.detector()
        detector.record_click(2, 11)
        self.assertEqual(detector.snapshot(10)['kind'], 'canvas')
        detector.record_click(99, 10)
        self.assertEqual(detector.snapshot(10)['kind'], 'canvas')
        detector.record_click(4, 10)
        self.assertEqual(detector.snapshot(10)['source'], 'fallback')

    def test_text_context_blocks_direct_script_dispatch(self):
        from backend.desktop import Desktop
        desktop = Desktop('http://localhost', lambda action:None)
        desktop._scope = lambda:True
        desktop.visible = True
        desktop.panel_context = self.detector()
        desktop.panel_context.current = {'kind':'text'}
        with self.assertRaisesRegex(RuntimeError, '输入'):
            desktop.require_action_focus()

    def test_home_blocks_layer_shortcuts_even_with_open_documents(self):
        from backend.desktop import Desktop
        desktop = Desktop('http://localhost', lambda action:None)
        desktop._scope = lambda:True
        desktop.visible = True
        desktop.panel_context = self.detector()
        desktop.panel_context.current = {'kind':'home','input_focused':False}
        with self.assertRaisesRegex(RuntimeError,'首页'):
            desktop.require_action_focus()
        desktop.require_action_focus(allow_home=True)
        desktop.panel_context.current['input_focused'] = True
        with self.assertRaisesRegex(RuntimeError,'输入'):
            desktop.require_action_focus(allow_home=True)

    def test_control_recreation_failure_uses_generic_menu(self):
        detector = self.detector()
        detector.focus_window.side_effect = RuntimeError('window destroyed')
        self.assertEqual(detector.snapshot(10)['source'], 'fallback')
        self.assertEqual(detector.current['kind'], 'generic')

    def test_hover_routes_without_click_and_overrides_last_click(self):
        detector = self.detector()
        detector.record_click(1, 10)
        detector.hover_window.return_value = 2
        self.assertEqual(detector.snapshot(10)['kind'], 'layers')
        self.assertEqual(detector.current['source'], 'hover')
        detector.hover_window.return_value = 1
        self.assertEqual(detector.snapshot(10)['kind'], 'canvas')
        detector.hover_window.return_value = 0
        self.assertEqual(detector.snapshot(10)['source'], 'last-click')

    def test_hover_keeps_input_guard_and_unknown_panel_fallback(self):
        detector = self.detector()
        detector.focus_window.return_value = 3
        detector.hover_window.return_value = 1
        context = detector.snapshot(10)
        self.assertEqual(context['kind'], 'canvas')
        self.assertTrue(context['input_focused'])
        detector.hover_window.return_value = 4
        self.assertEqual(detector.snapshot(10)['source'], 'fallback')

