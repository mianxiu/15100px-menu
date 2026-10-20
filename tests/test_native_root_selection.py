import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('node'), 'Node is required for UXP scalar selection simulation')
class NativeRootSelectionTests(unittest.TestCase):
    def test_scalar_capabilities_bounds_and_safe_fallback(self):
        for script in ('test-native-root-selection.cjs', 'test-native-selection.cjs', 'test-stability-fixture.cjs'):
            with self.subTest(script=script):
                result = subprocess.run(['node', str(ROOT / 'tools' / script)], cwd=ROOT,
                                        capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
