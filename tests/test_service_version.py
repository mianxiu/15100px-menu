import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from backend.main import APP_VERSION, reuse, service_identity


class ReuseTests(unittest.IsolatedAsyncioTestCase):
    async def check_reuse(self, responses, headless=True):
        client = SimpleNamespace(fetch=AsyncMock(side_effect=[
            SimpleNamespace(body=json.dumps(body).encode()) for body in responses]))
        with patch('backend.main.AsyncHTTPClient', return_value=client):
            await reuse(15151, headless)
        return client

    async def test_same_version_headless_does_not_open_management(self):
        client = await self.check_reuse([{'app': 'photoshop-menu', 'version': APP_VERSION}])
        self.assertEqual(client.fetch.await_count, 1)

    async def test_same_version_opens_management(self):
        client = await self.check_reuse([{'app': 'photoshop-menu', 'version': APP_VERSION}, {}], False)
        self.assertEqual(client.fetch.call_args.args[0].method, 'POST')

    async def test_legacy_old_version_is_not_silently_reused(self):
        with self.assertRaisesRegex(RuntimeError, '本次未切换版本'):
            await self.check_reuse([{'app': 'photoshop-menu'}, {'version': '0.4.4'}], False)

    async def test_newer_and_unknown_versions_are_rejected(self):
        for version in ('9.0.0', '0.4.5'):
            with self.subTest(version=version), self.assertRaisesRegex(RuntimeError, '本次未切换版本'):
                await self.check_reuse([{'app': 'photoshop-menu', 'version': version}])
        with self.assertRaisesRegex(RuntimeError, '未知'):
            await self.check_reuse([{'app': 'photoshop-menu'}, {}])

    async def test_foreign_service_is_never_reused(self):
        with self.assertRaisesRegex(RuntimeError, '其他服务'):
            await self.check_reuse([{'app': 'other', 'version': APP_VERSION}], False)

    def test_service_identity_reports_actual_process(self):
        identity = service_identity()
        self.assertEqual(identity['version'], APP_VERSION)
        self.assertEqual(identity['pid'], os.getpid())

