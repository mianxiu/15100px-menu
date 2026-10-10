import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


class NativeWinProcessTests(unittest.TestCase):
    host = Path(__file__).resolve().parents[1] / 'native/HotkeyHost.exe'

    def test_foreign_process_cannot_match_by_photoshop_window_class(self):
        result = subprocess.run([str(self.host), '--self-test-process-scope', 'false'],
            capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_photoshop_process_accepts_unknown_popup_without_class_whitelist(self):
        # Isolated helper windows only: no input or real PS document changes.
        with tempfile.TemporaryDirectory() as folder:
            helper = Path(folder) / 'Photoshop.exe'
            shutil.copy2(self.host, helper)
            result = subprocess.run([str(helper), '--self-test-process-scope', 'true'],
                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
