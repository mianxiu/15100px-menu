import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from backend.paths import ROOT, resource_root, runtime_dir, overlay_command


class PackagingTests(unittest.TestCase):
    def test_uxp_resources_are_whitelisted_without_credentials(self):
        spec=(ROOT/'PhotoshopMenu.spec').read_text('utf-8')
        for name in ('manifest.json','main.js','labels.js'):
            self.assertIn('uxp/offline-probe/'+name,spec)
        self.assertNotIn('probe-config.js',spec)
        self.assertNotIn('uxp-config.json',spec)
    def test_installed_entry_uses_its_own_data_root(self):
        with tempfile.TemporaryDirectory() as folder:
            installed=Path(folder)/'redirected/PhotoshopMenu/app/PhotoshopMenu.exe'
            with patch.object(sys,'frozen',True,create=True),patch.object(sys,'executable',str(installed)),patch.dict('os.environ',{'LOCALAPPDATA':str(Path(folder)/'different-user-location')}):
                self.assertEqual(runtime_dir(),installed.resolve().parent.parent)
    def test_development_resources_and_data_are_in_project(self):
        with patch.object(sys, 'frozen', False, create=True):
            self.assertEqual(resource_root(), ROOT)
            self.assertEqual(runtime_dir(), ROOT / '.runtime')
            args = overlay_command('http://localhost:15151', 'secret', ROOT / '.runtime')
            self.assertEqual(args[0], str(ROOT/'native/MenuHost.exe'))
            self.assertIn('--parent',args)

    def test_frozen_resources_are_separate_from_persistent_data(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(sys, 'frozen', True, create=True), \
                 patch.object(sys, '_MEIPASS', str(Path(folder)/'extracted'), create=True), \
                 patch.dict('os.environ', {'LOCALAPPDATA': str(Path(folder)/'user')}):
                self.assertEqual(resource_root(), Path(folder)/'extracted')
                self.assertEqual(runtime_dir(), Path(folder)/'user'/'PhotoshopMenu')
                args = overlay_command('http://localhost:15151', 'secret', runtime_dir())
                self.assertEqual(args[0], str(Path(folder)/'extracted/native/MenuHost.exe'))
                self.assertNotIn('-m', args)
                self.assertEqual(args[-2:], ['--icon', str(Path(folder)/'extracted/frontend/public/icon.ico')])


if __name__ == '__main__':
    unittest.main()
