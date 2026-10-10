import asyncio
import json
import threading
import unittest
import tempfile

from tornado.testing import AsyncHTTPTestCase, gen_test
from tornado.websocket import websocket_connect
from tornado.httpclient import HTTPRequest
from backend.main import Application, allowed_origin
from backend.desktop import KeyState
from backend.photoshop_bridge import PhotoshopBridge


class HotkeyTests(unittest.TestCase):
    def tab_state(self):
        from backend.settings import DEFAULTS
        return KeyState({**DEFAULTS['shortcuts'], 'toggle': 'tab', 'moveToTop':'tab+w'})

    def test_rapid_tab_press_release_sequences_are_fully_consumed(self):
        state = self.tab_state()
        for _ in range(1000):
            self.assertEqual(state.event(9, True, True), (True, 'hold_begin'))
            self.assertEqual(state.event(9, True, True), (True, None))
            self.assertEqual(state.event(9, False, True), (True, 'hold_release'))
        self.assertFalse(state.held)
        self.assertFalse(state.consumed)

    def test_tab_combo_does_not_toggle_and_ignores_repeat(self):
        state = self.tab_state()
        self.assertEqual(state.event(9, True, True), (True, 'hold_begin'))
        self.assertEqual(state.event(87, True, True), (True, 'moveToTop'))
        self.assertEqual(state.event(87, True, True), (True, None))
        self.assertEqual(state.event(87, False, True), (True, None))
        self.assertEqual(state.event(9, False, True), (True, 'hold_cancel'))
        state.event(9, True, True)
        self.assertEqual(state.event(9, False, True), (True, 'hold_release'))

    def test_unrelated_apps_and_modified_tab_are_preserved(self):
        state = self.tab_state()
        self.assertEqual(state.event(9, True, False), (False, None))
        self.assertEqual(state.event(9, False, False), (False, None))
        state.event(162, True, True)
        self.assertEqual(state.event(9, True, True), (False, None))
        self.assertEqual(state.event(9, False, True), (False, None))

    def test_focus_change_does_not_leak_consumed_key_release(self):
        state = self.tab_state()
        state.event(9, True, True)
        self.assertEqual(state.event(9, True, False), (True, None))
        self.assertEqual(state.event(9, False, False), (True, 'hold_cancel'))


class FakeBridge:
    busy = False
    async def status(self):
        return {'connected': False, 'document': None, 'busy': False, 'message': '请先启动 Photoshop'}
    async def execute(self, action):
        raise ValueError('请先在 Photoshop 中打开文档')
    def replace_scripts(self, scripts):
        self.scripts = scripts


class ApiTests(AsyncHTTPTestCase):
    def get_app(self):
        self.runtime = tempfile.TemporaryDirectory()
        self.addCleanup(self.runtime.cleanup)
        return Application(self.get_http_port(), bridge=FakeBridge(), runtime=self.runtime.name)

    def test_health_status_and_static_ui(self):
        self.assertEqual(json.loads(self.fetch('/api/health').body)['app'], 'photoshop-menu')
        self.assertFalse(json.loads(self.fetch('/api/status').body)['photoshop']['connected'])
        self.assertEqual(self.fetch('/').code, 200)

    def test_foreign_origin_and_host_rejected(self):
        self.assertEqual(self.fetch('/api/health', headers={'Origin': 'https://example.com'}).code, 403)
        self.assertEqual(self.fetch('/api/health', headers={'Host': 'example.com'}).code, 403)
        self.assertFalse(allowed_origin('http://localhost:invalid', self.get_http_port()))

    def test_plugin_upload_preview_and_export(self):
        from test_management import package
        boundary = 'photoshop-menu-test-boundary'
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="actions.zip"\r\nContent-Type: application/zip\r\n\r\n'.encode()
                + package() + f'\r\n--{boundary}--\r\n'.encode())
        response = self.fetch('/api/plugins/preview', method='POST', body=body,
                              headers={'Content-Type':f'multipart/form-data; boundary={boundary}'})
        data = json.loads(response.body)
        self.assertTrue(data['ok'])
        self.assertEqual(data['data']['manifest']['version'],'1.1.0')
        self.assertEqual(self._app.plugins.status()['active']['version'],'1.0.0')
        self.assertEqual(self.fetch('/api/plugins/export').code,200)

    @gen_test
    async def test_websocket_failure_does_not_break_next_request(self):
        url = self.get_url('/websocket').replace('http:', 'ws:')
        ws = await websocket_connect(HTTPRequest(url, headers={'Origin': self.get_url('/').rstrip('/')}))
        await ws.read_message()
        await ws.write_message(json.dumps({'id': '1', 'action': 'unknown'}))
        self.assertFalse(json.loads(await ws.read_message())['ok'])
        await ws.write_message(json.dumps({'id': '2', 'action': 'action.execute', 'args': {'name': 'select'}}))
        while True:
            response = json.loads(await ws.read_message())
            if response.get('id') == '2':
                self.assertFalse(response['ok'])
                break
        await ws.write_message(json.dumps({'id': '3', 'action': 'status'}))
        while True:
            response = json.loads(await ws.read_message())
            if response.get('id') == '3':
                self.assertTrue(response['ok'])
                break
        ws.close()

    @gen_test
    async def test_management_settings_and_plugin_activation(self):
        from test_management import package
        ws = await websocket_connect(HTTPRequest(self.get_url('/websocket').replace('http:', 'ws:'), headers={'Origin':self.get_url('/').rstrip('/')}))
        await ws.read_message()
        counter = 0
        async def request(action, args=None):
            nonlocal counter
            counter += 1
            request_id = str(counter)
            await ws.write_message(json.dumps({'id':request_id,'action':action,'args':args or {}}))
            while True:
                result = json.loads(await ws.read_message())
                if result.get('id') == request_id:
                    return result
        try:
            data = self._app.preferences.get()
            data['menu_width'] = 820
            self.assertTrue((await request('settings.save', {'settings':data}))['ok'])
            self.assertEqual((await request('status'))['data']['settings']['menu_width'],820)
            self.assertFalse((await request('panel.open'))['data'].get('ready',False))
            self.assertFalse((await request('action.execute',{'name':'select'}))['ok'])
            preview = self._app.plugins.prepare(package())
            self._app.bridge.busy = True
            self.assertFalse((await request('plugin.install',{'token':preview['token']}))['ok'])
            self._app.bridge.busy = False
            self.assertTrue((await request('plugin.install',{'token':preview['token']}))['ok'])
            self.assertEqual((await request('status'))['data']['plugin']['active']['version'],'1.1.0')
            self.assertTrue((await request('plugin.rollback'))['ok'])
            self.assertEqual((await request('status'))['data']['plugin']['active']['version'],'1.0.0')
            self.assertFalse((await request('plugin.check'))['ok'])
        finally:
            ws.close()


class BridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bridge = PhotoshopBridge()
        self.threads = []
        class Document:
            Name = 'sample.psd'
        class Documents:
            Count = 1
        class App:
            ActiveDocument = Document()
            def DoJavaScript(inner, script):
                self.threads.append(threading.get_ident())
                return 'done'
        self.app = App()
        self.app.Documents = Documents()
        self.bridge._application = lambda: self.app

    async def asyncTearDown(self):
        await self.bridge.close()

    async def test_serial_thread_and_missing_document_recovery(self):
        await self.bridge.execute('color')
        self.app.Documents.Count = 0
        with self.assertRaisesRegex(ValueError, '打开文档'):
            await self.bridge.execute('select')
        self.app.Documents.Count = 1
        await self.bridge.execute('moveToBottom')
        self.assertEqual(len(set(self.threads)), 1)
        self.assertNotEqual(self.threads[0], threading.get_ident())

    async def test_cancellation_keeps_busy_until_actual_com_finishes(self):
        started, release = threading.Event(), threading.Event()
        def execute(action):
            started.set()
            release.wait(3)
            return 'done'
        self.bridge._execute = execute
        task = asyncio.create_task(self.bridge.execute('color'))
        try:
            await asyncio.to_thread(started.wait, 2)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertTrue(self.bridge.busy)
            with self.assertRaisesRegex(RuntimeError, '尚未完成'):
                await self.bridge.execute('select')
        finally:
            release.set()
        for _ in range(100):
            if not self.bridge.busy:
                break
            await asyncio.sleep(.01)
        self.assertFalse(self.bridge.busy)


if __name__ == '__main__':
    unittest.main()
