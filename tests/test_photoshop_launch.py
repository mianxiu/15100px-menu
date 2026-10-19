import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from backend.photoshop_launch import PhotoshopLauncher, execute_worker, worker_command, registered_executable
from backend.main import Application, run
from backend.settings import atomic_json
from backend.version import APP_VERSION


class LaunchTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.running = Mock(return_value=False)
        self.ready = AsyncMock(return_value=True)
        self.registered = Mock(return_value=Path('Photoshop.exe'))
        self.launch = Mock(return_value=123)
        self.manager = PhotoshopLauncher(self.root, self.ready, running=self.running,
                                         registered=self.registered, launch=self.launch, timeout=.1)
    async def asyncTearDown(self):
        await self.manager.close()
        self.temp.cleanup()
    async def test_existing_process_does_not_activate_or_spawn(self):
        self.running.return_value=True
        reply=await self.manager.start()
        self.assertIn('未重复',reply['message'])
        self.assertFalse(self.manager.active)
        self.registered.assert_not_called(); self.launch.assert_not_called()
    async def test_accept_then_ready_and_repeated_request_rejected(self):
        def launch(request):
            data=json.loads(request.read_text())
            atomic_json(request.with_suffix('.result.json'), {'id':data['id'],'version':APP_VERSION,'state':'succeeded'})
            return 123
        self.launch.side_effect=launch
        accepted=await self.manager.start()
        self.assertEqual(accepted['photoshop_start']['phase'],'starting')
        with self.assertRaisesRegex(RuntimeError,'未重复'):await self.manager.start()
        await self.manager.task
        self.assertEqual(self.manager.snapshot()['phase'],'ready')
        self.assertEqual(self.launch.call_count,1)
        self.ready.assert_awaited_once()
    async def test_worker_error_and_timeout_do_not_retry(self):
        def launch(request):
            data=json.loads(request.read_text())
            atomic_json(request.with_suffix('.result.json'), {'id':data['id'],'version':APP_VERSION,'state':'failed','error':'CCD'})
        self.launch.side_effect=launch
        await self.manager.start(); await self.manager.task
        self.assertEqual(self.manager.state['phase'],'failed')
        self.launch.side_effect=None
        await self.manager.start(); await self.manager.task
        self.assertEqual(self.manager.state['phase'],'unknown')
        with self.assertRaisesRegex(RuntimeError,'未重复'):await self.manager.start()
        self.assertEqual(self.launch.call_count,2)
    async def test_mismatched_worker_and_shutdown_resume_never_resend(self):
        def launch(request):
            atomic_json(request.with_suffix('.result.json'), {'id':'foreign','version':APP_VERSION,'state':'succeeded'})
        self.launch.side_effect=launch
        await self.manager.start(); await self.manager.task
        self.assertEqual(self.manager.state['phase'],'unknown')
        resumed=PhotoshopLauncher(self.root,self.ready,launch=self.launch,timeout=.01)
        await resumed.resume(); await resumed.task
        self.assertEqual(self.launch.call_count,1)
        await resumed.close()
    async def test_open_backend_with_installed_plugin_ignores_legacy_auto_start(self):
        preferences=self.root/'photoshop-start/preferences.json'
        atomic_json(preferences,{'auto_start':True})
        saved=preferences.read_bytes()
        bridge=Mock();bridge.busy=False;bridge._queue=[];bridge.tasks=None;bridge.close=AsyncMock()
        app=Application(0,bridge=bridge,runtime=self.root)
        app.photoshop_launcher=self.manager
        app.uxp=Mock();app.uxp.status.return_value={'installed':True,'enabled':True,'error':None}
        app.preferences.data['open_control_on_start']=False
        app.sync_uxp_auto=AsyncMock()
        app.application_updates=Mock(periodic=AsyncMock(),close=AsyncMock())
        app.control=Mock();app.listen=Mock();app.stop_event.set()
        with patch('backend.main.Application',return_value=app), \
             patch('backend.main.Desktop'),patch('backend.main.Tray') as tray, \
             patch('backend.main.signal.signal'):
            tray.return_value.error=None
            await run(port=0,runtime=self.root)
        self.launch.assert_not_called();self.registered.assert_not_called()
        self.assertEqual(self.manager.snapshot()['phase'],'idle')
        self.assertEqual(preferences.read_bytes(),saved)
        with self.assertRaisesRegex(ValueError,'未知动作'):
            app.closing=False
            await app.dispatch('photoshop.autostart',{'enabled':True})
    async def test_busy_backend_rejects_start_and_management_during_start(self):
        bridge=Mock();bridge.busy=True;bridge._queue=[];bridge.tasks=None
        app=Application(15158,bridge=bridge,runtime=self.root)
        app.photoshop_launcher=self.manager
        with self.assertRaisesRegex(RuntimeError,'未排队'):await app.dispatch('photoshop.start',{})
        self.launch.assert_not_called()
        bridge.busy=False
        self.manager.state={'phase':'starting','started_at_ms':0}
        with self.assertRaises(RuntimeError):await app.dispatch('uxp.uninstall',{})

    async def test_explicit_start_action_still_launches_once(self):
        bridge=Mock();bridge.busy=False;bridge._queue=[];bridge.tasks=None
        app=Application(0,bridge=bridge,runtime=self.root)
        app.photoshop_launcher=self.manager
        app.sync_uxp_auto=AsyncMock()
        app.uxp=Mock();app.uxp.status.return_value={'installed':True,'enabled':True,'error':None}
        reply=await app.dispatch('photoshop.start',{})
        self.assertEqual(reply['photoshop_start']['phase'],'starting')
        await self.manager.task
        self.launch.assert_called_once()


class WorkerTests(unittest.TestCase):
    def test_registered_unquoted_exe_with_spaces_and_version_floor(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'Adobe Photoshop 2023'/'Photoshop.exe'
            path.parent.mkdir();path.write_bytes(b'test')
            key=MagicMock()
            with patch('winreg.QueryValue',return_value='{test}'),patch('winreg.OpenKey',return_value=key), \
                 patch('winreg.QueryValueEx',side_effect=[FileNotFoundError(),(str(path)+' /Automation',1)]), \
                 patch('backend.photoshop_launch.exe_version',return_value='24.0.1'):
                self.assertEqual(registered_executable(),path.resolve())
            with patch('winreg.QueryValue',return_value='{test}'),patch('winreg.OpenKey',return_value=key), \
                 patch('winreg.QueryValueEx',return_value=(str(path),1)), \
                 patch('backend.photoshop_launch.exe_version',return_value='23.2.9'):
                with self.assertRaisesRegex(RuntimeError,'23.3.0'):registered_executable()
    def test_frozen_worker_uses_the_same_exe_without_service_args(self):
        with patch.object(sys,'frozen',True,create=True),patch.object(sys,'executable','C:/app/PhotoshopMenu.exe'):
            command=worker_command(Path('C:/data/request.json'))
            self.assertEqual(command[1:3],['--ps-launch-worker','C:\\data\\request.json'])
            self.assertNotIn('--headless',command)
    def test_worker_existing_instance_attaches_only_and_consumes_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            request=Path(tmp)/'request.json'
            import time
            atomic_json(request,{'id':'a'*32,'version':APP_VERSION,'state':'requested',
                                 'started_at_ms':int(time.time()*1000),'executable':str(Path('Photoshop.exe'))})
            app=Mock();app.Version='24.0.1'
            with patch('backend.photoshop_launch.registered_executable',return_value=Path('Photoshop.exe')), \
                 patch('backend.photoshop_launch.photoshop_running',return_value=True), \
                 patch('win32com.client.GetActiveObject',return_value=app), \
                 patch('win32com.client.Dispatch') as activate:
                execute_worker(request)
                activate.assert_not_called()
                result=json.loads(request.with_suffix('.result.json').read_text())
                self.assertEqual(result['state'],'succeeded')
                self.assertTrue(result['existing_instance'])
                with self.assertRaisesRegex(ValueError,'消费'):execute_worker(request)


if __name__=='__main__':unittest.main()
