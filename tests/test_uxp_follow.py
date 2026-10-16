import json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock
from backend.uxp_auto_update import UxpAutoUpdate
from backend.uxp_management import UxpManager
from backend.paths import ROOT

class FollowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.auto=UxpAutoUpdate(self.root)
        self.manager=Mock();self.manager.status.return_value={'installed':True,'enabled':True,'error':'','version':'0.3.13','bundled_version':'0.3.14'}
        self.manager.running.return_value=False
    def tearDown(self):self.temp.cleanup()
    def test_waits_for_ps_and_unknown_result_without_install(self):
        self.manager.running.return_value=True
        self.assertEqual(self.auto.step(self.manager)['phase'],'waiting')
        self.manager.running.return_value=False
        self.assertEqual(self.auto.step(self.manager,blocked=True)['phase'],'waiting')
        self.manager.install.assert_not_called()
    def test_newer_only_and_one_failure_attempt_until_reset(self):
        self.manager.install.side_effect=RuntimeError('disk denied')
        self.assertEqual(self.auto.step(self.manager)['phase'],'error')
        self.auto.step(self.manager);self.manager.install.assert_called_once()
        self.auto.set_enabled(True);self.auto.step(self.manager);self.assertEqual(self.manager.install.call_count,2)
        self.manager.status.return_value['version']='0.3.15';self.auto.step(self.manager);self.assertEqual(self.manager.install.call_count,2)
    def test_disabled_missing_modified_preserved(self):
        for changes in ({'installed':False},{'enabled':False},{'error':'modified'}):
            self.manager.status.return_value.update(changes);self.auto.step(self.manager)
            self.manager.status.return_value.update(installed=True,enabled=True,error='')
        self.auto.set_enabled(False);self.auto.step(self.manager);self.manager.install.assert_not_called()
        self.assertFalse(UxpAutoUpdate(self.root).enabled)
    def test_real_install_preserves_credential_and_supports_rollback(self):
        old=self.root/'old';old.mkdir()
        import shutil
        for name in ('main.js','labels.js','manifest.json'):shutil.copy2(ROOT/'uxp/offline-probe'/name,old/name)
        manifest=json.loads((old/'manifest.json').read_text('utf-8'));manifest['version']='0.3.13';(old/'manifest.json').write_text(json.dumps(manifest),'utf-8')
        m=UxpManager(self.root/'runtime',old,self.root/'roaming',running=lambda:False,hosts=lambda _:None)
        m.install();credential=m.config.read_bytes();m.builtin=ROOT/'uxp/offline-probe'
        self.assertEqual(self.auto.step(m)['phase'],'updated');self.assertEqual(m.status()['version'],m.status()['bundled_version']);self.assertEqual(m.config.read_bytes(),credential)
        self.auto.set_enabled(False);m.rollback();self.auto.step(m);self.assertEqual(m.status()['version'],'0.3.13')
