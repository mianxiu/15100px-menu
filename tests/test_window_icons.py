"""Exercise real Windows icon decoding and WM_SETICON, without user windows."""
import os
import unittest

from backend.window_icons import WindowIcons


@unittest.skipUnless(os.name == 'nt', 'Windows native icon test')
class IconTests(unittest.TestCase):
    def test_ico_loads_all_sizes_and_window_icons_can_be_repaired(self):
        import win32api
        import win32gui as g
        icons = WindowIcons()
        name = 'PhotoshopMenuIconTest'
        instance = win32api.GetModuleHandle(None)
        wc = g.WNDCLASS()
        wc.hInstance, wc.lpszClassName = instance, name
        wc.lpfnWndProc = g.DefWindowProc
        g.RegisterClass(wc)
        hwnd = g.CreateWindow(name, name, 0, 0, 0, 0, 0, 0, 0, instance, None)
        try:
            for size in (16, 20, 24, 32, 40, 48, 64, 128, 256):
                self.assertTrue(icons.load(size))
            self.assertTrue(icons.apply(hwnd))
            self.assertIn(icons.message(hwnd, 0x7f, 0, 0), icons.handles.values())
            self.assertIn(icons.message(hwnd, 0x7f, 1, 0), icons.handles.values())
            icons.message(hwnd, 0x80, 0, 0)  # Simulate Edge replacing the favicon.
            self.assertTrue(icons.apply(hwnd))
            self.assertIn(icons.message(hwnd, 0x7f, 0, 0), icons.handles.values())
            icons.detach(hwnd)
            self.assertEqual(icons.message(hwnd, 0x7f, 0, 0), 0)
        finally:
            g.DestroyWindow(hwnd)
            g.UnregisterClass(name, instance)
            icons.close()
        self.assertFalse(icons.handles)
