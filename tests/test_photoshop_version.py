import unittest
from unittest.mock import patch
from backend.photoshop_version import require_version,check_install_hosts

class PhotoshopVersionTests(unittest.TestCase):
    def test_boundary_and_newer_versions(self):
        for version in ('24.0.1','24.0.1.112','24.1.0','25.0.0','30.0.0'):
            self.assertEqual(require_version(version),version)
    def test_older_build_number_cannot_bypass_floor(self):
        for version in ('23.5.0','24.0.0','24.0.0.999'):
            with self.assertRaisesRegex(RuntimeError,'24.0.1'):require_version(version)
    def test_unknown_versions_fail_closed(self):
        for value in (None,'unavailable','24.x','24.0.1 bad'):
            with self.assertRaises(ValueError):require_version(value)
    def test_no_installation_or_only_old_installation_rejected(self):
        with self.assertRaises(RuntimeError):check_install_hosts([])
        with patch('backend.photoshop_version.exe_version',return_value='24.0.0'):
            with self.assertRaisesRegex(RuntimeError,'24.0.1'):check_install_hosts(['old.exe'])
    def test_coexisting_versions_only_returns_supported_hosts(self):
        with patch('backend.photoshop_version.exe_version',side_effect=['23.5.0','24.0.1','26.0.0']):
            self.assertEqual([v['version'] for v in check_install_hosts(['old','current','new'])],['24.0.1','26.0.0'])
