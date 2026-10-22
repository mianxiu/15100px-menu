import asyncio, json, tempfile, unittest
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
from backend.language import read_language, save_language, plugin_name, localized_manifest
from backend.main import Application
from backend.paths import ROOT
from backend.uxp_management import UxpManager

class LanguageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.builtin_version=json.loads((ROOT/'uxp/offline-probe/manifest.json').read_text('utf-8'))['version']
        self.manager=UxpManager(self.root,ROOT/'uxp/offline-probe',self.root/'roaming',
                                running=Mock(return_value=False),hosts=Mock(return_value=[]))
    def tearDown(self):self.temp.cleanup()
    def test_names_follow_manifest_version_and_do_not_duplicate_suffix(self):
        original={'name':'Photoshop 快捷菜单 v0.3.4','version':'0.3.9','entrypoints':[{'id':'probe','label':{'default':'检查连接'}}]}
        for language in ('zh-CN','en'):
            result=localized_manifest(original,language)
            self.assertEqual(result['name'],plugin_name(language,'0.3.9'))
            self.assertEqual(localized_manifest(result,language),result)
        self.assertEqual(original['name'],'Photoshop 快捷菜单 v0.3.4')
    def test_old_name_detected_and_only_manifest_updated(self):
        self.manager.install()
        data=json.loads((self.manager.plugin/'manifest.json').read_text('utf-8'))
        data['name']='Photoshop 快捷菜单'
        (self.manager.plugin/'manifest.json').write_text(json.dumps(data),'utf-8')
        from backend.uxp_management import digest
        state=self.manager.state();state['owned']['manifest.json']=digest(self.manager.plugin/'manifest.json')
        from backend.settings import atomic_json
        atomic_json(self.manager.state_path,state)
        status=self.manager.status()
        self.assertTrue(status['language_pending'])
        self.assertEqual(status['desired_name'],plugin_name('zh-CN',self.builtin_version))
        before={n:(self.manager.plugin/n).read_bytes() for n in ('main.js','labels.js','probe-config.js')}
        self.manager.apply_language()
        self.assertFalse(self.manager.status()['language_pending'])
        self.assertEqual(self.manager.status()['name'],status['desired_name'])
        self.assertEqual(before,{n:(self.manager.plugin/n).read_bytes() for n in before})
    def test_default_persistence_and_validation(self):
        self.assertEqual(read_language(self.root),'zh-CN')
        save_language(self.root,'en');self.assertEqual(read_language(self.root),'en')
        for bad in (None,'fr',42):
            with self.assertRaises(ValueError):save_language(self.root,bad)
        self.assertEqual(read_language(self.root),'en')
    def test_installation_states_and_external_damage(self):
        self.assertEqual(self.manager.status()['installation'],'missing')
        self.manager.plugin.mkdir(parents=True)
        (self.manager.plugin/'main.js').write_text('partial')
        self.assertEqual(self.manager.status()['installation'],'invalid')
        (self.manager.plugin/'main.js').unlink();self.manager.plugin.rmdir()
        self.manager.install()
        self.assertEqual(self.manager.status()['installation'],'installed')
        (self.manager.plugin/'labels.js').write_text('foreign code')
        self.assertEqual(self.manager.status()['installation'],'invalid')
    def test_name_application_keeps_credentials_code_enable_and_rolls_back(self):
        self.manager.install();before={n:(self.manager.plugin/n).read_bytes() for n in ('main.js','labels.js','probe-config.js')}
        self.manager.set_enabled(False);save_language(self.root,'en')
        self.assertTrue(self.manager.status()['language_pending'])
        self.manager.running.return_value=True
        with self.assertRaisesRegex(RuntimeError,'关闭 Photoshop'):self.manager.apply_language()
        self.assertEqual(self.manager.status()['name'],plugin_name('zh-CN',self.builtin_version))
        self.manager.running.return_value=False;self.manager.apply_language()
        status=self.manager.status();self.assertFalse(status['enabled']);self.assertFalse(status['language_pending'])
        self.assertEqual(status['name'],plugin_name('en',self.builtin_version));self.assertTrue(status['matches_builtin'])
        self.assertEqual(before,{n:(self.manager.plugin/n).read_bytes() for n in before})
        self.manager.rollback();self.assertEqual(self.manager.status()['name'],plugin_name('zh-CN',self.builtin_version))
    def test_name_failure_restores_files_and_history(self):
        self.manager.install();before=self.manager.state();manifest=(self.manager.plugin/'manifest.json').read_bytes()
        save_language(self.root,'en')
        with patch.object(self.manager,'sync_receipt',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.manager.apply_language()
        self.assertEqual(self.manager.state(),before)
        self.assertEqual((self.manager.plugin/'manifest.json').read_bytes(),manifest)
    def test_english_install_has_correct_package_metadata(self):
        save_language(self.root,'en');self.manager.install()
        self.assertEqual(self.manager.status()['name'],plugin_name('en',self.builtin_version))
        self.assertFalse(self.manager.status()['language_pending'])
        self.assertTrue(self.manager.status()['matches_builtin'])

class LanguageApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_ui_switch_does_not_apply_native_settings_or_plugin_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=Application(0,bridge=Mock(tasks=None,status=AsyncMock(return_value={'connected':False})),runtime=tmp);app.desktop=Mock(input_language=None)
            with patch.object(app,'broadcast',new_callable=unittest.mock.AsyncMock):
                await app.dispatch('language.set',{'language':'en'})
            app.desktop.apply_settings.assert_not_called()
            self.assertFalse(app.uxp.plugin.exists() and app.uxp.plugin.is_relative_to(Path(tmp)))
            self.assertEqual(read_language(tmp),'en')
            await app.photoshop_launcher.close()
