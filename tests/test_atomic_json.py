import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from backend.settings import atomic_json


class AtomicJsonTests(unittest.TestCase):
    def denied(self,code):
        error=PermissionError('file temporarily held');error.winerror=code;return error

    def test_only_failed_windows_publication_retries_and_success_returns_once(self):
        for code in (5,32):
            with tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'journal.json';path.write_text('{"old":true}','utf-8')
                replace=os.replace;calls=[]
                def publish(source,target):
                    calls.append((source,target))
                    if len(calls)==1:raise self.denied(code)
                    replace(source,target)
                with patch('backend.settings.os.replace',side_effect=publish),patch('backend.settings.time.sleep') as sleep:
                    atomic_json(path,{'pending':'original'})
                self.assertEqual(len(calls),2);sleep.assert_called_once_with(.004)
                self.assertEqual(json.loads(path.read_text()),{'pending':'original'})
                self.assertFalse(path.with_suffix('.json.tmp').exists())

    def test_expired_retry_retains_original_journal_and_unpublished_temporary(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'journal.json';original=b'{"pending":"unknown"}';path.write_bytes(original)
            with patch('backend.settings.os.replace',side_effect=self.denied(5)) as replace,patch('backend.settings.time.monotonic',side_effect=[0,1]),patch('backend.settings.time.sleep') as sleep:
                with self.assertRaises(PermissionError):atomic_json(path,{'new':True})
            replace.assert_called_once();sleep.assert_not_called()
            self.assertEqual(path.read_bytes(),original)
            self.assertEqual(json.loads(path.with_suffix('.json.tmp').read_text()),{'new':True})

    def test_other_permission_errors_are_not_retried(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'journal.json'
            with patch('backend.settings.os.replace',side_effect=self.denied(13)) as replace,patch('backend.settings.time.sleep') as sleep:
                with self.assertRaises(PermissionError):atomic_json(path,{'new':True})
            replace.assert_called_once();sleep.assert_not_called()
