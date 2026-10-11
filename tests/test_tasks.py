import asyncio
import threading
import unittest
from unittest.mock import Mock
from backend.photoshop_bridge import PhotoshopBridge
from backend.tasks import TaskStore, TaskCancelled

class TaskTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bridge=PhotoshopBridge()
        self.bridge._capture_target=lambda:{'document_id':1,'active_layer_id':2,'layer_ids':[2]}
    async def asyncTearDown(self):await self.bridge.close()
    async def wait_idle(self):
        for _ in range(100):
            if not self.bridge.busy:return
            await asyncio.sleep(.01)
        self.fail('COM completion did not release busy')
    async def test_success_unique_ids_snapshot_and_no_task_for_rejected_command(self):
        self.bridge._execute=Mock(return_value='done')
        first=await self.bridge.execute('color');second=await self.bridge.execute('color')
        self.assertNotEqual(first['task_id'],second['task_id'])
        record=self.bridge.tasks.get(first['task_id'])
        self.assertEqual(record['state'],'succeeded')
        self.assertEqual(record['target']['document_id'],1)
        record['target']['layer_ids'].append(99)
        self.assertEqual(self.bridge.tasks.get(first['task_id'])['target']['layer_ids'],[2])
        with self.assertRaises(ValueError):await self.bridge.execute('invalid')
        self.assertEqual(len(self.bridge.tasks.snapshot()['items']),2)
    async def test_write_timeout_is_unknown_then_same_task_succeeds_without_replay(self):
        release=threading.Event();self.bridge.operation_timeout=.02
        self.bridge._execute=Mock(side_effect=lambda action:release.wait(3) and 'done')
        try:
            with self.assertRaisesRegex(RuntimeError,'结果尚未确定') as error:await self.bridge.execute('color')
            task_id=error.exception.task_id
            self.assertEqual(self.bridge.tasks.get(task_id)['state'],'result-unknown')
            self.assertTrue(self.bridge.busy)
            with self.assertRaises(RuntimeError):await self.bridge.execute('color')
            release.set();await self.wait_idle()
            record=self.bridge.tasks.get(task_id)
            self.assertEqual(record['state'],'succeeded');self.assertFalse(record['error'])
            self.assertTrue(record['wait_error']);self.bridge._execute.assert_called_once()
        finally:release.set()
    async def test_capture_timeout_never_writes_and_settles_cancelled(self):
        release=threading.Event();self.bridge.operation_timeout=.02
        def capture():
            release.wait(3)
            return {'document_id':1,'active_layer_id':2,'layer_ids':[2]}
        self.bridge._capture_target=capture;self.bridge._execute=Mock()
        try:
            with self.assertRaisesRegex(RuntimeError,'目标读取超时') as error:await self.bridge.execute('color')
            task_id=error.exception.task_id
            self.assertEqual(self.bridge.tasks.get(task_id)['state'],'cancel-requested')
            self.assertTrue(self.bridge.busy)
            release.set();await self.wait_idle()
            self.assertEqual(self.bridge.tasks.get(task_id)['state'],'cancelled')
            self.bridge._execute.assert_not_called()
        finally:release.set()
    async def test_late_write_error_updates_same_unknown_task(self):
        release=threading.Event();self.bridge.operation_timeout=.02
        def write(action):
            release.wait(3);raise RuntimeError('late PS failure')
        self.bridge._execute=Mock(side_effect=write)
        try:
            with self.assertRaises(RuntimeError) as error:await self.bridge.execute('color')
            task_id=error.exception.task_id
            release.set();await self.wait_idle()
            record=self.bridge.tasks.get(task_id)
            self.assertEqual(record['state'],'failed');self.assertIn('late PS failure',record['error'])
            self.bridge._execute.assert_called_once()
        finally:release.set()
    async def test_menu_cancellation_is_recorded_without_dispatch(self):
        async def handoff(target):raise TaskCancelled('菜单已重开')
        self.bridge._execute=Mock()
        with self.assertRaises(TaskCancelled) as error:await self.bridge.execute('color',before_dispatch=handoff)
        self.assertEqual(self.bridge.tasks.get(error.exception.task_id)['state'],'cancelled')
        self.bridge._execute.assert_not_called()
    def test_history_is_bounded_and_final_state_cannot_regress(self):
        store=TaskStore(limit=4);ids=[]
        for _ in range(10):
            task_id=store.create('color','标色');ids.append(task_id)
            store.update(task_id,'running');store.update(task_id,'succeeded')
        self.assertEqual([item['id'] for item in store.snapshot()['items']],ids[-4:][::-1])
        with self.assertRaises(ValueError):store.update(ids[-1],'result-unknown')
        with self.assertRaises(ValueError):store.get(ids[0])
