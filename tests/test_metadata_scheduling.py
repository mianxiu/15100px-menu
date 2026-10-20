import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('node'), 'Node is required for production UXP worker simulation')
class MetadataSchedulingTests(unittest.TestCase):
    def test_interactive_priority_and_independent_freshness(self):
        for script in ('test-metadata-scheduling.cjs', 'test-uxp-preferences.cjs'):
            with self.subTest(script=script):
                result = subprocess.run(['node', str(ROOT / 'tools' / script)], cwd=ROOT,
                                        capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
