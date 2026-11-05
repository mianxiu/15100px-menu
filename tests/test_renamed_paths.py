import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from backend.paths import application_data_root, runtime_dir

class RenamedApplicationPathsTests(unittest.TestCase):
    def test_fresh_install_and_existing_state(self):
        with tempfile.TemporaryDirectory() as directory:
            local=Path(directory)
            self.assertEqual(application_data_root(local),local/'151500px-menu')
            legacy=local/'PhotoshopMenu';legacy.mkdir()
            (legacy/'uxp-pending.json').write_text('unknown','utf-8')
            (local/'151500px-menu').mkdir()
            self.assertEqual(application_data_root(local),legacy)
            self.assertEqual((legacy/'uxp-pending.json').read_text('utf-8'),'unknown')

    def test_installed_executable_keeps_its_own_data(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ('PhotoshopMenu','151500px-menu'):
                root=Path(directory)/name
                with patch('sys.frozen',True,create=True), patch('sys.executable',str(root/'app/151500px-menu.exe')):
                    self.assertEqual(runtime_dir(),root.resolve())
