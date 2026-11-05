import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import input_service


def clsid_literal(guid):
    value = guid.strip('{}').lower().replace('-', '')
    parts = [value[0:8], value[8:12], value[12:16], value[16:20], value[20:32]]
    return ('{0x' + parts[0] + ', 0x' + parts[1] + ', 0x' + parts[2] + ', {'
            + ', '.join('0x' + parts[3][i:i + 2] for i in range(0, 4, 2)) + ', '
            + ', '.join('0x' + parts[4][i:i + 2] for i in range(0, 12, 2)) + '}}')


class ContractTests(unittest.TestCase):
    def test_registration_identity_matches_the_native_service(self):
        source = (Path(__file__).resolve().parents[1] / 'native/InputService.cpp').read_text('utf-8')
        self.assertIn(clsid_literal(input_service.CLSID), source)

    def test_machine_keys_are_distinct_and_scoped(self):
        self.assertTrue(input_service.TIP_KEY.startswith(r'SOFTWARE\Microsoft\CTF\TIP'))
        self.assertIn(input_service.CLSID, input_service.TIP_KEY)
        self.assertTrue(input_service.CLASS_KEY.startswith(r'SOFTWARE\Classes\CLSID'))
        self.assertIn(input_service.CLSID, input_service.CLASS_KEY)
        self.assertEqual(input_service.LANGIDS, (0x0804, 0x0409))

    def test_service_files_are_the_two_native_dlls(self):
        self.assertEqual(input_service.FILES, ('InputService.dll', 'InputContext.dll'))


class StatusTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix='psmenu-input-service-'))
        self.source = self.folder / 'source'
        self.install = self.folder / 'installed'
        self.source.mkdir()
        self.install.mkdir()
        for name in input_service.FILES:
            (self.source / name).write_bytes(b'payload-' + name.encode())
            (self.install / name).write_bytes(b'payload-' + name.encode())
        self.patches = [patch.object(input_service, 'PROGRAM_DATA', self.install),
                        patch.object(input_service, '_source', side_effect=lambda name: self.source / name),
                        patch.object(input_service, '_register_cache', {'at': 0.0, 'value': None})]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()

    def test_unregistered_reports_the_injection_channel(self):
        with patch.object(input_service, '_read_hklm', return_value=None):
            value = input_service.status()
        self.assertFalse(value['registered'])
        self.assertEqual(value['channel'], 'injection')
        self.assertTrue(all(item['match'] for item in value['files'].values()))

    def test_registered_profile_reports_the_tsf_channel(self):
        def read(path, name=''):
            if path == input_service.CLASS_KEY + r'\InprocServer32':
                return str(self.install / 'InputService.dll')
            if 'LanguageProfile' in path:
                return 1 if name == 'Enable' else 'Photoshop Menu 输入法服务'
            return None
        with patch.object(input_service, '_read_hklm', side_effect=read):
            value = input_service.status()
        self.assertTrue(value['registered'])
        self.assertEqual(value['channel'], 'tsf')
        self.assertEqual(value['languages'], [0x0804, 0x0409])

    def test_mismatched_installed_files_are_reported(self):
        (self.install / 'InputService.dll').write_bytes(b'older')
        with patch.object(input_service, '_read_hklm', return_value=None):
            value = input_service.status()
        self.assertFalse(value['files']['InputService.dll']['match'])


class ElevationTests(unittest.TestCase):
    def test_cancelled_elevation_changes_nothing(self):
        with patch.object(input_service.ctypes.windll.shell32, 'ShellExecuteW', return_value=5):
            with self.assertRaisesRegex(RuntimeError, '管理员'):
                input_service.request('install', Path(tempfile.gettempdir()) / 'psmenu-input-service')

    def test_failed_receipt_is_reported(self):
        runtime = Path(tempfile.mkdtemp(prefix='psmenu-input-service-'))
        receipt = runtime / 'input-service-install.json'

        def shell(*_):
            receipt.write_text(json.dumps({'ok': False, 'error': '拒绝写入'}), 'utf-8')
            return 42
        with patch.object(input_service.ctypes.windll.shell32, 'ShellExecuteW', side_effect=shell):
            with self.assertRaisesRegex(RuntimeError, '拒绝写入'):
                input_service.request('install', runtime, timeout=5)

    def test_successful_receipt_is_consumed(self):
        runtime = Path(tempfile.mkdtemp(prefix='psmenu-input-service-'))
        receipt = runtime / 'input-service-remove.json'

        def shell(*_):
            receipt.write_text(json.dumps({'ok': True, 'files': []}), 'utf-8')
            return 42
        with patch.object(input_service.ctypes.windll.shell32, 'ShellExecuteW', side_effect=shell):
            value = input_service.request('remove', runtime, timeout=5)
        self.assertTrue(value['ok'])
        self.assertFalse(receipt.exists())

    def test_unknown_operation_is_rejected_before_elevation(self):
        with patch.object(input_service.ctypes.windll.shell32, 'ShellExecuteW') as shell:
            with self.assertRaises(ValueError):
                input_service.request('enable', Path(tempfile.gettempdir()))
        shell.assert_not_called()


class PrivilegedTests(unittest.TestCase):
    def test_missing_native_files_write_a_failed_receipt(self):
        runtime = Path(tempfile.mkdtemp(prefix='psmenu-input-service-'))
        receipt = runtime / 'receipt.json'
        with patch.object(input_service, '_source', return_value=runtime / 'missing.dll'):
            value = input_service.apply_privileged('install', receipt)
        self.assertFalse(value['ok'])
        self.assertIn('缺少原生组件', value['error'])
        self.assertFalse(json.loads(receipt.read_text('utf-8'))['ok'])


if __name__ == '__main__':
    unittest.main()
