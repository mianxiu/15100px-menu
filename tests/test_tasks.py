import asyncio
import threading
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
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
            self.assertEqual([phase['state'] for phase in record['timeline']],
                             ['capturing','running','result-unknown','succeeded'])
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

    async def test_text_split_has_bounded_batch_wait_without_changing_capture_or_other_commands(self):
        original=asyncio.wait_for;timeouts=[];self.bridge.operation_timeout=.2
        async def wait(future,timeout):
            timeouts.append(timeout);return await original(future,1)
        with patch('backend.photoshop_bridge.asyncio.wait_for',side_effect=wait):
            result=await self.bridge._execute_task('text.split',execute=lambda _: '{"verified":true,"count":64}')
        self.assertEqual(timeouts,[.2,120]);self.assertEqual(self.bridge.operation_timeout,.2)
        self.assertEqual(self.bridge.tasks.get(result['task_id'])['state'],'succeeded')
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

    async def test_user_cancel_during_target_read_never_dispatches(self):
        release=threading.Event();started=threading.Event()
        def capture():
            started.set();release.wait(3)
            return {'document_id':1,'active_layer_id':2,'layer_ids':[2]}
        self.bridge._capture_target=capture;self.bridge._execute=Mock()
        pending=asyncio.create_task(self.bridge.execute('color'))
        try:
            while not started.is_set():await asyncio.sleep(.001)
            task_id=self.bridge.tasks.snapshot()['items'][0]['id']
            self.bridge.request_cancel(task_id)
            self.bridge.request_cancel(task_id) # Idempotent; no retry or second task.
            self.assertEqual(self.bridge.tasks.get(task_id)['state'],'cancel-requested')
            self.assertTrue(self.bridge.busy)
            release.set()
            with self.assertRaises(TaskCancelled):await pending
            record=self.bridge.tasks.get(task_id)
            self.assertEqual(record['state'],'cancelled');self.assertFalse(record['error'])
            self.bridge._execute.assert_not_called();self.assertFalse(self.bridge.busy)
        finally:release.set();await asyncio.gather(pending,return_exceptions=True)

    async def test_cancel_cannot_interrupt_dispatched_write(self):
        release=threading.Event();started=threading.Event()
        def execute(action):started.set();release.wait(3);return 'done'
        self.bridge._execute=Mock(side_effect=execute)
        pending=asyncio.create_task(self.bridge.execute('color'))
        try:
            while not started.is_set():await asyncio.sleep(.001)
            task_id=self.bridge.tasks.snapshot()['items'][0]['id']
            with self.assertRaisesRegex(ValueError,'不能强制中断'):self.bridge.request_cancel(task_id)
            release.set();await pending
            self.assertEqual(self.bridge.tasks.get(task_id)['state'],'succeeded')
            self.bridge._execute.assert_called_once()
            with self.assertRaises(ValueError):self.bridge.request_cancel(task_id)
        finally:release.set();await asyncio.gather(pending,return_exceptions=True)
    def test_history_is_bounded_and_final_state_cannot_regress(self):
        store=TaskStore(limit=4);ids=[]
        for _ in range(10):
            task_id=store.create('color','标色');ids.append(task_id)
            store.update(task_id,'running');store.update(task_id,'succeeded')
        self.assertEqual([item['id'] for item in store.snapshot()['items']],ids[-4:][::-1])
        with self.assertRaises(ValueError):store.update(ids[-1],'result-unknown')
        with self.assertRaises(ValueError):store.get(ids[0])

    def test_timeline_measures_states_without_duplicate_metadata_updates(self):
        with patch('backend.tasks.time.monotonic', return_value=100) as clock:
            store=TaskStore();task_id=store.create('color','标色')
            clock.return_value=100.2
            store.update(task_id,'capturing',target={'document_id':1})
            clock.return_value=100.3
            store.update(task_id,'running')
            clock.return_value=100.8
            snapshot=store.get(task_id)
            self.assertEqual([phase['duration_ms'] for phase in snapshot['timeline']],[300,500])
            self.assertTrue(snapshot['timeline'][-1]['active'])
            snapshot['timeline'][0]['duration_ms']=99
            clock.return_value=101
            store.update(task_id,'succeeded')
            clock.return_value=500
            final=store.get(task_id)
            self.assertEqual([phase['duration_ms'] for phase in final['timeline']],[300,700,0])
            self.assertFalse(any(phase['active'] for phase in final['timeline']))
            self.assertEqual(final['elapsed_ms'],1000)

    async def test_timeline_restores_without_running_clock_or_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'history.json'
            store=TaskStore(path=path)
            task_id=store.create('color','标色')
            store.update(task_id,'running')
            await store.close()
            restored=TaskStore(path=path)
            try:
                record=restored.get(task_id)
                self.assertEqual(record['state'],'result-unknown')
                self.assertEqual([phase['state'] for phase in record['timeline']],['capturing','running'])
                self.assertFalse(any(phase['active'] for phase in record['timeline']))
                await asyncio.sleep(.01)
                self.assertEqual(record['timeline'],restored.get(task_id)['timeline'])
                with self.assertRaises(ValueError):restored.update(task_id,'succeeded')
            finally:await restored.close()
