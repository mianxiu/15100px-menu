import copy
import json
import tempfile
import unittest
from pathlib import Path

from backend.settings import DEFAULTS, Settings, validate


class RemoteCompatibilityTests(unittest.TestCase):
    def test_legacy_settings_remain_opted_out(self):
        legacy = copy.deepcopy(DEFAULTS)
        legacy.pop('remote_compatibility')
        self.assertFalse(validate(legacy)['remote_compatibility'])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'settings.json'
            path.write_text(json.dumps(legacy), encoding='utf-8')
            self.assertEqual(Settings(path).get(), DEFAULTS)

    def test_explicit_opt_in_persists_and_rejects_non_boolean(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'settings.json'
            settings = Settings(path)
            value = settings.get()
            value['remote_compatibility'] = True
            settings.save(value)
            self.assertEqual(Settings(path).get(), value)
        for value in (1, 'true', None, []):
            data = copy.deepcopy(DEFAULTS)
            data['remote_compatibility'] = value
            with self.assertRaises(ValueError):
                validate(data)
