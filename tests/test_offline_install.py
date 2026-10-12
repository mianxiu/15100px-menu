import importlib.util,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('offline_install',ROOT/'tools/offline_install.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class OfflineInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        self.payload=self.base/'payload';(self.payload/'plugin').mkdir(parents=True)
        (self.payload/'PhotoshopMenu.exe').write_bytes(b'app')
        self.setup=self.base/'setup.exe';self.setup.write_bytes(b'setup')
        for name in ('manifest.json','main.js','labels.js'):
            (self.payload/'plugin'/name).write_bytes((ROOT/'uxp/offline-probe'/name).read_bytes())
        files=['PhotoshopMenu.exe','plugin/manifest.json','plugin/main.js','plugin/labels.js']
        (self.payload/'SHA256.json').write_text(json.dumps({p:module.digest(self.payload/p) for p in files}))
        self.installer=module.OfflineInstall(self.base/'Local',self.base/'Roaming')
    def tearDown(self):self.temp.cleanup()
    def test_fresh_credentials_and_no_user_config_in_package(self):
        self.installer.install(self.payload,self.setup)
        token=json.loads((self.installer.root/'uxp-config.json').read_text())['token']
        self.assertIn(token,(self.installer.plugin/'probe-config.js').read_text())
        another=module.OfflineInstall(self.base/'Another',self.base/'AnotherRoaming')
        another.install(self.payload,self.setup)
        self.assertNotEqual(token,json.loads((another.root/'uxp-config.json').read_text())['token'])
    def test_update_rollback_and_uninstall_preserve_user_data(self):
        self.installer.install(self.payload,self.setup)
        settings=self.installer.root/'settings.json';settings.write_text('user settings')
        config=(self.installer.root/'uxp-config.json').read_bytes()
        previous=(self.installer.plugin/'main.js').read_bytes()
        self.installer.install(self.payload,self.setup)
        self.installer.rollback()
        self.assertEqual((self.installer.plugin/'main.js').read_bytes(),previous)
        self.installer.uninstall()
        self.assertEqual(settings.read_text(),'user settings')
        self.assertEqual((self.installer.root/'uxp-config.json').read_bytes(),config)
        self.assertFalse((self.installer.plugin/'main.js').exists())
    def test_corrupt_payload_is_rejected_before_any_change(self):
        (self.payload/'PhotoshopMenu.exe').write_bytes(b'corrupt')
        with self.assertRaises(RuntimeError):self.installer.install(self.payload,self.setup)
        self.assertFalse(self.installer.root.exists())
    def test_partial_failure_restores_previous_files(self):
        self.installer.install(self.payload,self.setup)
        old=(self.installer.plugin/'main.js').read_bytes()
        def fail():raise OSError('shortcut failure')
        with self.assertRaises(OSError):self.installer.install(self.payload,self.setup,fail)
        self.assertEqual((self.installer.plugin/'main.js').read_bytes(),old)
        self.assertTrue(self.installer.receipt.exists())
    def test_uninstall_refuses_modified_or_foreign_owned_files(self):
        self.installer.install(self.payload,self.setup)
        script=self.installer.plugin/'main.js';script.write_bytes(b'user change')
        with self.assertRaises(RuntimeError):self.installer.uninstall()
        self.assertEqual(script.read_bytes(),b'user change')
        self.assertTrue((self.installer.root/'app/PhotoshopMenu.exe').exists())
    def test_restore_refuses_foreign_path(self):
        with self.assertRaises(RuntimeError):self.installer.restore(self.base/'not-a-backup')
    def test_install_refuses_foreign_plugin_directory(self):
        self.installer.plugin.mkdir(parents=True)
        (self.installer.plugin/'manifest.json').write_text('{"id":"other-plugin"}')
        with self.assertRaises(RuntimeError):self.installer.install(self.payload,self.setup)
        self.assertEqual((self.installer.plugin/'manifest.json').read_text(),'{"id":"other-plugin"}')
    def test_hot_update_only_accepts_identical_plugin_and_keeps_mtimes(self):
        self.installer.install(self.payload,self.setup)
        script=self.installer.plugin/'main.js';before=script.stat().st_mtime_ns
        self.assertTrue(self.installer.plugin_is_current(self.payload))
        self.installer.install(self.payload,self.setup,preserve_plugin=True)
        self.assertEqual(script.stat().st_mtime_ns,before)
        script.write_bytes(b'different plugin')
        with self.assertRaises(RuntimeError):self.installer.install(self.payload,self.setup,preserve_plugin=True)
    def test_minimum_declaration_update_preserves_running_code_and_credentials(self):
        self.installer.install(self.payload,self.setup)
        path=self.installer.plugin/'manifest.json'
        manifest=json.loads(path.read_text('utf-8'));manifest['host']['minVersion']='23.5.0'
        path.write_text(json.dumps(manifest),'utf-8')
        code=self.installer.plugin/'main.js';mtime=code.stat().st_mtime_ns
        credential=(self.installer.root/'uxp-config.json').read_bytes()
        self.assertFalse(self.installer.plugin_is_current(self.payload))
        self.assertTrue(self.installer.plugin_is_current(self.payload,True))
        self.installer.install(self.payload,self.setup,preserve_plugin=True)
        self.assertEqual(json.loads(path.read_text('utf-8'))['host']['minVersion'],'24.0.1')
        self.assertEqual(code.stat().st_mtime_ns,mtime)
        self.assertEqual((self.installer.root/'uxp-config.json').read_bytes(),credential)
