import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from backend.paths import ROOT
from backend.uxp_management import UxpManager, PLUGIN_ID, OWNED
from backend.uxp_auto_update import UxpAutoUpdate


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.manager=UxpManager(self.root/'runtime',ROOT/'uxp/offline-probe',self.root/'roaming',running=lambda:False,hosts=lambda _:None)
        self.index=self.manager.registration.path
        self.foreign={'pluginId':'151500PX','path':'$localPlugins/External/another','status':'enabled','foreign_setting':{'keep':True}}
    def tearDown(self):self.tmp.cleanup()
    def write(self,plugins=None):
        self.index.parent.mkdir(parents=True,exist_ok=True)
        self.index.write_text(json.dumps({'plugins':plugins if plugins is not None else [self.foreign],'metadata':{'keep':[1,2]}}),'utf-8')
    def read(self):return json.loads(self.index.read_text('utf-8'))
    def own(self):return next(p for p in self.read()['plugins'] if p['pluginId']==PLUGIN_ID)
    def test_absent_index_preserves_directory_fallback(self):
        self.manager.install();self.manager.repair_registration()
        self.assertFalse(self.index.exists());self.assertEqual(self.manager.status()['registration']['state'],'directory')
    def test_install_registers_existing_index_and_preserves_foreign_metadata(self):
        self.write();self.manager.install()
        self.assertEqual(self.read()['plugins'][0],self.foreign)
        self.assertEqual(self.read()['metadata'],{'keep':[1,2]})
        self.assertEqual(self.own()['status'],'enabled')
        self.assertEqual(self.own()['path'],'$localPlugins\\External\\'+self.manager.plugin.name)
        self.assertEqual(self.manager.status()['registration']['state'],'registered')
        backup=self.manager.root/'backups'/self.manager.state()['history'][-1]
        self.assertEqual(json.loads((backup/'PS-index-recovery.json').read_text())['plugins'],[self.foreign])
    def test_uninstall_rollback_merges_new_foreign_entries(self):
        self.write();self.manager.install();entry=self.own();self.manager.uninstall()
        self.assertEqual(self.read()['plugins'],[self.foreign])
        other={'pluginId':'new-after-uninstall','extra':'preserve'}
        self.write([self.foreign,other]);self.manager.rollback()
        self.assertEqual(self.read()['plugins'],[self.foreign,other,entry])
        self.assertTrue(self.manager.status()['installed'])
    def test_install_rollback_removes_only_own_registration(self):
        self.write();self.manager.install();self.manager.rollback()
        self.assertEqual(self.read()['plugins'],[self.foreign]);self.assertFalse(self.manager.status()['installed'])
    def test_invalid_structures_duplicate_keys_and_foreign_paths_block_before_writes(self):
        bad=['broken','[]','{"plugins":{}}','{"plugins":[1]}','{"plugins":[],"plugins":[]}',json.dumps({'plugins':[{'pluginId':PLUGIN_ID,'path':'$localPlugins/External/foreign'}]})]
        self.index.parent.mkdir(parents=True)
        for raw in bad:
            with self.subTest(raw=raw):
                self.index.write_text(raw,'utf-8')
                with self.assertRaises(ValueError):self.manager.install()
                self.assertEqual(self.index.read_text('utf-8'),raw)
                self.assertFalse(self.manager.plugin.exists());self.assertFalse(self.manager.config.exists())
    def test_disabled_preserved_until_explicit_repair(self):
        self.write();self.manager.install();entry=self.own();entry.update(status='disabled',custom='keep')
        self.write([self.foreign,entry]);self.manager.install()
        self.assertEqual(self.own()['status'],'disabled')
        auto=UxpAutoUpdate(self.manager.runtime)
        self.assertEqual(auto.step(self.manager)['phase'],'blocked')
        self.manager.repair_registration();self.assertEqual(self.own()['status'],'enabled');self.assertEqual(self.own()['custom'],'keep')
        self.manager.rollback();self.assertEqual(self.own()['status'],'disabled')
    def test_same_version_auto_repair_waits_for_ps_and_unknown_and_is_reversible(self):
        self.manager.install();self.write();auto=UxpAutoUpdate(self.manager.runtime)
        before={n:(self.manager.plugin/n).read_bytes() for n in OWNED}
        self.assertEqual(auto.step(self.manager,blocked=True)['phase'],'waiting')
        self.manager.running=lambda:True
        self.assertEqual(auto.step(self.manager)['phase'],'waiting')
        self.assertEqual(self.read()['plugins'],[self.foreign])
        self.manager.running=lambda:False
        self.assertEqual(auto.step(self.manager)['phase'],'updated')
        self.assertEqual(auto.step(self.manager)['phase'],'current')
        self.assertEqual(before,{n:(self.manager.plugin/n).read_bytes() for n in OWNED})
        self.manager.rollback();self.assertEqual(self.read()['plugins'],[self.foreign])
    def test_concurrent_index_change_is_preserved_and_plugin_files_rolled_back(self):
        self.write();original=self.manager.registration.commit
        external={'pluginId':'concurrent-editor'}
        def race(plan):
            self.write([self.foreign,external]);return original(plan)
        with patch.object(self.manager.registration,'commit',side_effect=race):
            with self.assertRaisesRegex(RuntimeError,'其他程序修改'):self.manager.install()
        self.assertEqual(self.read()['plugins'],[self.foreign,external])
        self.assertFalse(self.manager.plugin.exists());self.assertFalse(self.manager.config.exists())
    def test_partial_failure_keeps_index_bytes_and_original_files(self):
        self.write();self.manager.install();before=self.index.read_bytes();state=self.manager.state()
        with patch.object(self.manager,'sync_receipt',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.manager.install()
        self.assertEqual(self.index.read_bytes(),before);self.assertEqual(self.manager.state(),state)
    def test_rollback_concurrent_index_change_preserves_external_edit_and_current_files(self):
        self.write();self.manager.install();state=self.manager.state();original=self.manager.registration.commit
        changed={**self.own(),'status':'disabled','external':'keep'}
        def race(plan):
            self.write([self.foreign,changed]);return original(plan)
        with patch.object(self.manager.registration,'commit',side_effect=race):
            with self.assertRaisesRegex(RuntimeError,'其他程序修改'):self.manager.rollback()
        self.assertEqual(self.own(),changed);self.assertEqual(self.manager.state(),state)
        self.assertTrue(self.manager.status()['matches_builtin'])
    def test_duplicate_own_entries_refused_and_oversize_refused(self):
        self.write();self.manager.install();entry=self.own();self.write([entry,entry])
        with self.assertRaises(ValueError):self.manager.repair_registration()
        self.index.write_bytes(b' '*(2*1024*1024+1))
        self.assertEqual(self.manager.status()['registration']['state'],'invalid')
    def test_name_update_synchronizes_index_preserving_unknown_fields(self):
        self.write();self.manager.install();entry=self.own();entry['custom']='keep';self.write([self.foreign,entry])
        (self.manager.runtime/'ui-language.json').write_text('{"language":"en"}')
        self.manager.apply_language()
        self.assertEqual(self.own()['name'],self.manager.status()['name']);self.assertEqual(self.own()['custom'],'keep')
    def test_legacy_snapshot_rollback_synchronizes_current_restored_manifest(self):
        self.write();self.manager.install();self.manager.install()
        snapshot=self.manager.root/'backups'/self.manager.state()['history'][-1]/'snapshot.json'
        data=json.loads(snapshot.read_text('utf-8'));data.pop('registration');snapshot.write_text(json.dumps(data),'utf-8')
        self.manager.rollback();self.assertEqual(self.manager.status()['registration']['state'],'registered')
        snapshot=self.manager.root/'backups'/self.manager.state()['history'][-1]/'snapshot.json'
        data=json.loads(snapshot.read_text('utf-8'));data.pop('registration');snapshot.write_text(json.dumps(data),'utf-8')
        self.manager.rollback();self.assertEqual(self.read()['plugins'],[self.foreign])
