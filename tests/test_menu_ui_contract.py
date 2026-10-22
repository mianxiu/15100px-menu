"""Prevent new native tool views from silently reverting to default widgets."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


class MenuUiContractTests(unittest.TestCase):
    def test_tool_views_use_caps_controls_without_local_palette_or_widget_styles(self):
        for path in (ROOT/'native').glob('*Panel.h'):
            source=path.read_text('utf-8')
            with self.subTest(panel=path.name):
                self.assertNotRegex(source,r'ImGui::(?:Button|Selectable|InputText\w*)\s*\(')
                self.assertNotRegex(source,r'ImGui::PushStyleVar|IM_COL32\(|ImVec4\(')
                self.assertIn('MenuControls::PanelStyle',source)
        source=(ROOT/'native/MenuToolsPanel.h').read_text('utf-8')
        for shared in ('PanelStyle','button','input','segments'):
            self.assertIn('MenuControls::'+shared,source)
        caps=(ROOT/'native/MenuHost.cpp').read_text('utf-8')
        for shared in ('surface','outline','segment'):
            self.assertIn('MenuControls::'+shared,caps)

    def test_shared_controls_keep_ps_tokens_and_keyboard_navigation(self):
        source=(ROOT/'native/MenuControls.h').read_text('utf-8')
        self.assertNotRegex(source,r'IM_COL32\(|ImVec4\(')
        for token in ('FrameRounding','menuControlHeight','menuControlTextInset','menuControlBorder','menuPanelGap'):
            self.assertIn(token,source)
        self.assertIn('ImGuiButtonFlags_EnableNav',source)
        self.assertIn('RenderNavCursor',source)
        self.assertIn('requireText(value)',source)
        build=(ROOT/'tools/build-menu-host.ps1').read_text('utf-8')
        self.assertIn('-DIMGUI_ENABLE_WIN32_DEFAULT_IME_FUNCTIONS',build)
