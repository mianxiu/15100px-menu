import asyncio
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import Mock, patch, AsyncMock
from tornado.testing import AsyncHTTPTestCase, gen_test
from tornado.websocket import websocket_connect
from tornado.httpclient import HTTPRequest
from backend.paths import ROOT
from backend.uxp_management import UxpManager, FILES
from backend.uxp_bridge import UxpBridge, compatible
from backend.main import Application

class UxpManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        self.manager=UxpManager(self.base/'data', ROOT/'uxp/offline-probe', self.base/'roaming',
                                running=Mock(return_value=False),hosts=Mock(return_value=[{'version':'24.0.1'}]))
    def tearDown(self):self.temp.cleanup()
    def test_install_disable_persist_export_and_uninstall_rollback(self):
        self.manager.install()
        token=self.manager.config.read_bytes()
        self.manager.set_enabled(False)
        again=UxpManager(self.manager.runtime,self.manager.builtin,self.base/'roaming')
        self.assertFalse(again.enabled)
        self.assertTrue(self.manager.status()['installed'])
        self.manager.set_enabled(True)
        with zipfile.ZipFile(io.BytesIO(self.manager.export())) as z:
            self.assertEqual(set(z.namelist()),{*FILES,'package.json'})
            self.assertNotIn(json.loads(token)['token'].encode(),b''.join(z.read(n) for n in z.namelist()))
        prepared=self.manager.prepare(self.manager.export())
        self.manager.install(prepared['token'])
        self.assertEqual(self.manager.config.read_bytes(),token)
        self.manager.uninstall()
        self.assertFalse(self.manager.status()['installed']);self.assertFalse(self.manager.enabled)
        self.assertEqual(self.manager.config.read_bytes(),token)
        self.manager.rollback()
        self.assertTrue(self.manager.status()['installed']);self.assertTrue(self.manager.enabled)
    def test_running_ps_blocks_file_changes_but_disable_is_immediate(self):
        self.manager.install();before=(self.manager.plugin/'main.js').read_bytes()
        self.manager.running.return_value=True
        for fn in (self.manager.install,self.manager.uninstall,self.manager.rollback):
            with self.assertRaisesRegex(RuntimeError,'关闭 Photoshop'):fn()
        self.manager.set_enabled(False)
        self.assertEqual((self.manager.plugin/'main.js').read_bytes(),before)
    def test_host_version_failure_precedes_writes(self):
        self.manager.hosts.side_effect=RuntimeError('old Photoshop')
        with self.assertRaises(RuntimeError):self.manager.install()
        self.assertFalse(self.manager.plugin.exists());self.assertFalse(self.manager.config.exists())
    def test_existing_compact_config_preserves_bytes_and_extra_fields(self):
        self.manager.runtime.mkdir(parents=True)
        original=json.dumps({'token':'a'*64,'protocol_version':1,'user_metadata':'keep'}).encode()
        self.manager.config.write_bytes(original)
        self.manager.install()
        self.assertEqual(self.manager.config.read_bytes(),original)
    def test_missing_plugin_cannot_enable(self):
        with self.assertRaises(RuntimeError):self.manager.set_enabled(True)
    def test_external_changes_and_foreign_extra_files_preserved(self):
        self.manager.install();path=self.manager.plugin/'main.js';path.write_text('user edit')
        for fn in (self.manager.install,self.manager.uninstall,self.manager.rollback):
            with self.assertRaisesRegex(RuntimeError,'外部修改'):fn()
        self.assertEqual(path.read_text(),'user edit')
    def test_credentials_mismatch_refuses_enable(self):
        self.manager.install();(self.manager.plugin/'probe-config.js').write_text('other')
        with self.assertRaises(RuntimeError):self.manager.set_enabled(True)
    def test_partial_update_failure_rolls_back_files_and_state(self):
        self.manager.install();before=self.manager.state();config=self.manager.config.read_bytes()
        with patch.object(self.manager,'sync_receipt',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.manager.install()
        self.assertEqual(self.manager.state(),before)
        self.assertEqual(self.manager.config.read_bytes(),config)
        self.assertTrue(self.manager.status()['matches_builtin'])
    def test_bad_zip_and_corrupt_preview_cannot_install(self):
        with zipfile.ZipFile(io.BytesIO(self.manager.export())) as z:files={n:z.read(n) for n in z.namelist()}
        def package(files):
            b=io.BytesIO()
            with zipfile.ZipFile(b,'w') as z:
                for n,c in files.items():z.writestr(n,c)
            return b.getvalue()
        with self.assertRaises(ValueError):self.manager.prepare(package({**files,'../escape':b'x'}))
        with self.assertRaises(ValueError):self.manager.prepare(package({**files,'main.js':b'changed'}))
        prepared=self.manager.prepare(package(files))
        (self.manager.source(prepared['token'])/'labels.js').write_text('changed')
        with self.assertRaises(ValueError):self.manager.install(prepared['token'])
    def test_legacy_install_adoption_checks_receipt_and_updates_ownership(self):
        self.manager.install();receipt=self.manager.runtime/'offline-install.json'
        receipt.write_text(json.dumps({'owned':{str(self.manager.plugin/n):'wrong' for n in (*FILES,'probe-config.js')}}))
        self.manager.state_path.unlink()
        with self.assertRaisesRegex(RuntimeError,'外部修改'):self.manager.install()
    def test_transport_patch_versions_compatible_but_major_changes_rejected(self):
        self.assertTrue(compatible('0.3.1'));self.assertFalse(compatible('0.4.0'));self.assertFalse(compatible(None))
    def test_plugin_rollback_preserves_current_application_receipt(self):
        self.manager.runtime.mkdir(parents=True)
        receipt=self.manager.runtime/'offline-install.json'
        receipt.write_text(json.dumps({'version':'old-app','owned':{'current-app.exe':'old-hash'}}))
        self.manager.install()
        current=json.loads(receipt.read_text());current.update(version='new-app')
        current['owned']['current-app.exe']='new-hash';receipt.write_text(json.dumps(current))
        self.manager.rollback()
        restored=json.loads(receipt.read_text())
        self.assertEqual(restored['version'],'new-app')
        self.assertEqual(restored['owned']['current-app.exe'],'new-hash')
        self.assertFalse(self.manager.status()['installed'])

class UxpExecutionGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_disable_precedes_capture_and_task_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            bridge=UxpBridge(task_history=Path(tmp)/'tasks.json');bridge.transport=Mock()
            def disabled():raise RuntimeError('disabled')
            bridge.execution_guard=disabled
            try:
                with self.assertRaisesRegex(RuntimeError,'disabled'):await bridge.execute('label.red')
                bridge.transport.call.assert_not_called();self.assertFalse(bridge.tasks.snapshot()['items'])
            finally:await bridge.close()
    async def test_management_busy_rejects_and_does_not_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            bridge=Mock();bridge.busy=True;bridge._queue=[];bridge.tasks=None
            app=Application(15159,bridge=bridge,runtime=Path(tmp));app.uxp=Mock()
            with self.assertRaisesRegex(RuntimeError,'未排队'):await app.dispatch('uxp.disable',{})
            with self.assertRaisesRegex(RuntimeError,'未排队'):await app.dispatch('uxp.repair-registration',{})
            app.uxp.repair_registration.assert_not_called()
            app.uxp.set_enabled.assert_not_called()
            bridge.busy=False
            app.uxp.set_enabled.return_value={'message':'disabled'}
            app.broadcast=Mock(side_effect=lambda x:asyncio.sleep(0))
            # Status refresh is independent of the mock bridge.
            original=app.dispatch
            async def dispatch(action,args):return {} if action=='status' else await original(action,args)
            app.dispatch=dispatch
            self.assertEqual(await app.dispatch('uxp.disable',{}),{'message':'disabled'})
            app.uxp.set_enabled.assert_called_once_with(False)

class UxpManagementApiTests(AsyncHTTPTestCase):
    def test_follow_and_diagnostic_states_are_in_public_status(self):
        state=json.loads(self.fetch('/api/status').body)
        self.assertTrue(state['uxp_auto_update']['enabled'])
        self.assertEqual(state['diagnostics']['phase'],'idle')
        self.assertFalse(state['diagnostics']['ready'])

    def get_app(self):
        self.temp=tempfile.TemporaryDirectory();base=Path(self.temp.name)
        self.bridge=UxpBridge(task_history=base/'data/tasks.json')
        self.bridge.status=AsyncMock(return_value={'connected':False,'execution_backend':'uxp-local-files'})
        app=Application(self.get_http_port(),bridge=self.bridge,runtime=base/'data')
        app.uxp=UxpManager(base/'data',ROOT/'uxp/offline-probe',base/'roaming',running=lambda:False,hosts=lambda p:[])
        # Old enabled preferences must not start PS after install/update either.
        preferences=base/'data/photoshop-start/preferences.json'
        preferences.parent.mkdir(parents=True)
        preferences.write_text('{"auto_start":true}',encoding='utf-8')
        self.start_photoshop=AsyncMock()
        app.photoshop_launcher.start=self.start_photoshop
        return app
    def tearDown(self):
        self.io_loop.run_sync(self.bridge.close)
        super().tearDown();self.temp.cleanup()
    def test_uxp_export_preview_and_origin_protection(self):
        result=self.fetch('/api/uxp/export');self.assertEqual(result.code,200)
        boundary='uxp-package-test'
        body=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="uxp.zip"\r\nContent-Type: application/zip\r\n\r\n'.encode()+result.body+f'\r\n--{boundary}--\r\n'.encode())
        preview=self.fetch('/api/uxp/preview',method='POST',body=body,headers={'Content-Type':f'multipart/form-data; boundary={boundary}'})
        self.assertTrue(json.loads(preview.body)['ok'])
        self.assertEqual(self.fetch('/api/uxp/export',headers={'Origin':'https://example.com'}).code,403)
    @gen_test
    async def test_production_follow_repairs_same_version_index_and_respects_startup_protection(self):
        app=self._app;app.uxp.install();index=app.uxp.registration.path
        index.parent.mkdir(parents=True);index.write_text('{"plugins":[{"pluginId":"foreign"}]}','utf-8')
        app.photoshop_launcher.state={'phase':'unknown'}
        await app.sync_uxp_auto(force=True)
        self.assertEqual(app.uxp.status()['registration']['state'],'missing')
        app.photoshop_launcher.state={'phase':'idle'}
        await app.sync_uxp_auto(force=True)
        self.assertEqual(app.uxp.status()['registration']['state'],'registered')
        self.assertEqual(json.loads(index.read_text('utf-8'))['plugins'][0],{'pluginId':'foreign'})

    @gen_test
    async def test_websocket_install_disable_enable_update_rollback_uninstall(self):
        ws=await websocket_connect(HTTPRequest(self.get_url('/websocket').replace('http:','ws:'),headers={'Origin':self.get_url('/').rstrip('/')}))
        await ws.read_message()
        async def request(action,args=None):
            await ws.write_message(json.dumps({'id':action,'action':action,'args':args or {}}))
            while True:
                result=json.loads(await ws.read_message())
                if result.get('id')==action:return result
        try:
            self.assertTrue((await request('uxp.install'))['ok'])
            self.start_photoshop.assert_not_awaited()
            self.assertTrue((await request('uxp.disable'))['ok'])
            blocked=await request('action.execute',{'name':'label.red'})
            self.assertFalse(blocked['ok']);self.assertIn('禁用',blocked['error'])
            self.assertFalse(self.bridge.tasks.snapshot()['items'])
            self.assertTrue((await request('uxp.enable'))['ok'])
            self.assertTrue((await request('uxp.repair-registration'))['ok'])
            preview=self._app.uxp.prepare(self._app.uxp.export())
            self.assertTrue((await request('uxp.install',{'token':preview['token']}))['ok'])
            self.start_photoshop.assert_not_awaited()
            self.assertTrue((await request('uxp.rollback'))['ok'])
            self.assertTrue((await request('uxp.uninstall'))['ok'])
            self.assertFalse((await request('uxp.enable'))['ok'])
            self.start_photoshop.assert_not_awaited()
        finally:ws.close()


class MinimumDeclarationMigrationTests(unittest.TestCase):
    setUp=UxpManagementTests.setUp
    tearDown=UxpManagementTests.tearDown

    def previous_install(self):
        from backend.uxp_management import digest
        from backend.settings import atomic_json
        self.manager.install()
        path=self.manager.plugin/'manifest.json';v=json.loads(path.read_text('utf-8'))
        v['host']['minVersion']='24.0.1';atomic_json(path,v)
        state=self.manager.state();state['owned']['manifest.json']=digest(path);atomic_json(self.manager.state_path,state)
        self.manager.running.return_value=True
        return path

    def test_only_owned_floor_hot_migrates_and_preserves_runtime_code(self):
        from backend.uxp_auto_update import UxpAutoUpdate
        path=self.previous_install();names=('main.js','labels.js','probe-config.js')
        before={n:((self.manager.plugin/n).read_bytes(),(self.manager.plugin/n).stat().st_mtime_ns) for n in names}
        token=self.manager.config.read_bytes()
        auto=UxpAutoUpdate(self.manager.runtime)
        self.assertTrue(self.manager.status()['minimum_declaration_pending'])
        auto.step(self.manager,blocked=True);self.assertEqual(json.loads(path.read_text('utf-8'))['host']['minVersion'],'24.0.1')
        result=auto.step(self.manager);self.assertEqual(result['phase'],'current')
        self.assertEqual(json.loads(path.read_text('utf-8'))['host']['minVersion'],'23.3.0')
        self.assertTrue(self.manager.status()['matches_builtin']);self.assertFalse(self.manager.status()['error'])
        for n,(content,mtime) in before.items():
            self.assertEqual((self.manager.plugin/n).read_bytes(),content);self.assertEqual((self.manager.plugin/n).stat().st_mtime_ns,mtime)
        self.assertEqual(self.manager.config.read_bytes(),token)

    def test_foreign_script_is_not_overwritten_or_adopted(self):
        path=self.previous_install();code=self.manager.plugin/'main.js';code.write_bytes(b'foreign code')
        with self.assertRaises(RuntimeError):self.manager.sync_minimum_declaration()
        self.assertEqual(code.read_bytes(),b'foreign code');self.assertEqual(json.loads(path.read_text('utf-8'))['host']['minVersion'],'24.0.1')

    def test_package_validation_stays_strict_and_migration_does_not_enable_disabled_plugin(self):
        from backend.uxp_management import validate
        from backend.settings import atomic_json
        path=self.previous_install()
        with self.assertRaises(ValueError):validate(self.manager.plugin)
        self.assertEqual(validate(self.manager.plugin,allow_previous_floor=True)['host']['minVersion'],'24.0.1')
        state=self.manager.state();state['enabled']=False;atomic_json(self.manager.state_path,state)
        self.manager.sync_minimum_declaration();self.assertFalse(self.manager.enabled)

    def test_metadata_failure_restores_floor_and_keeps_js_and_credentials_untouched(self):
        path=self.previous_install();code=self.manager.plugin/'main.js';mtime=code.stat().st_mtime_ns
        token=self.manager.config.read_bytes();before=self.manager.state()
        with patch.object(self.manager,'sync_receipt',side_effect=OSError('receipt write failed')):
            with self.assertRaises(OSError):self.manager.sync_minimum_declaration()
        self.assertEqual(json.loads(path.read_text('utf-8'))['host']['minVersion'],'24.0.1')
        self.assertEqual(code.stat().st_mtime_ns,mtime);self.assertEqual(self.manager.config.read_bytes(),token);self.assertEqual(self.manager.state(),before)

    def test_older_plugin_keeps_normal_closed_ps_upgrade_path(self):
        from backend.uxp_auto_update import UxpAutoUpdate
        from backend.uxp_management import digest
        from backend.settings import atomic_json
        path=self.previous_install();v=json.loads(path.read_text('utf-8'));v['version']='0.3.42';atomic_json(path,v)
        state=self.manager.state();state['owned']['manifest.json']=digest(path);atomic_json(self.manager.state_path,state)
        auto=UxpAutoUpdate(self.manager.runtime)
        with patch.object(self.manager,'sync_minimum_declaration') as hot,patch.object(self.manager,'install') as install:
            self.assertEqual(auto.step(self.manager)['phase'],'waiting');hot.assert_not_called();install.assert_not_called()
            self.manager.running.return_value=False
            self.assertEqual(auto.step(self.manager)['phase'],'updated');install.assert_called_once();hot.assert_not_called()
