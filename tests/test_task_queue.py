import asyncio,threading,unittest
from unittest.mock import Mock
from backend.photoshop_bridge import PhotoshopBridge
from backend.tasks import TaskCancelled

class QueueTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bridge=PhotoshopBridge();self.release=threading.Event();self.started=threading.Event()
        self.target={'document_id':1,'active_layer_id':2,'layer_ids':[2],'instance_binding':'original'}
        self.app=object();self.writes=[];self.captures=[]
        def capture():
            self.bridge._captured_app=self.app
            return dict(self.target)
        self.bridge._capture_target=capture
        def recapture(binding):
            self.captures.append(binding)
            if binding[1]!=self.target:raise TaskCancelled('目标已改变')
            return dict(binding[1])
        self.bridge._capture_queued_target=recapture
        def execute(action):
            self.writes.append(action)
            if len(self.writes)==1:self.started.set();self.release.wait(3)
            return 'done'
        self.bridge._execute=execute
        self.pending=[]
    async def asyncTearDown(self):
        self.release.set();await asyncio.gather(*self.pending,return_exceptions=True)
        if not self.bridge.closed:await self.bridge.close()
    async def start(self):
        task=asyncio.create_task(self.bridge.execute('color',enqueue=True));self.pending.append(task)
        while not self.started.is_set():await asyncio.sleep(.001)
        return task
    async def queue(self,action='moveToTop'):
        task=asyncio.create_task(self.bridge.execute(action,enqueue=True));self.pending.append(task)
        while not self.bridge._queue and not task.done():await asyncio.sleep(.001)
        return task
    async def test_fifo_fixed_binding_cancel_middle_and_no_parallel_write(self):
        first=await self.start();second=await self.queue();second_id=self.bridge._queue[0]
        third=asyncio.create_task(self.bridge.execute('moveToBottom',enqueue=True));self.pending.append(third)
        while len(self.bridge._queue)<2:await asyncio.sleep(.001)
        third_id=self.bridge._queue[1]
        self.assertEqual(self.writes,['color'])
        self.bridge.request_cancel(second_id);self.bridge.request_cancel(second_id)
        with self.assertRaises(TaskCancelled):await second
        self.release.set();await first;result=await third
        self.assertEqual(self.writes,['color','moveToBottom'])
        self.assertIs(self.captures[0][0],self.app)
        self.assertEqual(result['target'],self.target)
        self.assertEqual(self.bridge.tasks.get(third_id)['state'],'succeeded')
        self.assertFalse(self.bridge.busy);self.assertFalse(self.bridge._queue)
    async def test_queue_deadline_never_submits_or_releases_running_owner(self):
        self.bridge.queue_timeout=.02
        await self.start();second=await self.queue()
        with self.assertRaisesRegex(TaskCancelled,'期限'):await second
        self.assertEqual(self.writes,['color']);self.assertTrue(self.bridge.busy)
        self.assertEqual(self.bridge.tasks.snapshot()['items'][0]['state'],'cancelled')
    async def test_changed_target_rejects_without_write(self):
        first=await self.start();second=await self.queue();self.target={**self.target,'layer_ids':[3],'active_layer_id':3}
        self.release.set();await first
        with self.assertRaises(TaskCancelled):await second
        self.assertEqual(self.writes,['color'])
    async def test_close_cancels_waiting_tasks_without_dispatch(self):
        await self.start();second=await self.queue()
        closing=asyncio.create_task(self.bridge.close());self.pending.append(closing)
        with self.assertRaisesRegex(TaskCancelled,'退出'):await second
        self.assertEqual(self.writes,['color']);self.release.set();await closing
    async def test_unknown_result_rejects_new_and_cancels_existing_queue(self):
        self.bridge.operation_timeout=.03
        first=await self.start();second=await self.queue()
        with self.assertRaises(RuntimeError):await first
        with self.assertRaisesRegex(RuntimeError,'结果未知'):await self.bridge.execute('color',enqueue=True)
        self.release.set()
        with self.assertRaisesRegex(TaskCancelled,'超时'):await second
        self.assertEqual(self.writes,['color'])
    async def test_fifo_order_for_multiple_live_requests(self):
        first=await self.start();second=await self.queue()
        third=asyncio.create_task(self.bridge.execute('moveToBottom',enqueue=True));self.pending.append(third)
        while len(self.bridge._queue)<2:await asyncio.sleep(.001)
        self.release.set();await asyncio.gather(first,second,third)
        self.assertEqual(self.writes,['color','moveToTop','moveToBottom'])
    async def test_cancelled_running_wait_does_not_resume_queued_mutations(self):
        first=await self.start();second=await self.queue()
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):await first
        self.release.set()
        with self.assertRaisesRegex(TaskCancelled,'超时'):await second
        self.assertEqual(self.writes,['color'])
    async def test_menu_session_guard_still_cancels_queued_write(self):
        first=await self.start()
        async def guard(target):raise TaskCancelled('菜单已重新打开')
        second=asyncio.create_task(self.bridge.execute('color',guard,enqueue=True));self.pending.append(second)
        while not self.bridge._queue:await asyncio.sleep(.001)
        self.release.set();await first
        with self.assertRaisesRegex(TaskCancelled,'菜单'):await second
        self.assertEqual(self.writes,['color'])
    async def test_unfixed_target_and_bounded_queue_are_rejected(self):
        first=await self.start();self.bridge.queue_limit=1
        await self.queue()
        with self.assertRaisesRegex(RuntimeError,'已满'):await self.bridge.execute('color',enqueue=True)
        self.bridge._captured_app=None
        with self.assertRaisesRegex(RuntimeError,'尚未固定'):await self.bridge.execute('color',enqueue=True)
        self.release.set();await first

    async def test_production_dispatch_rejects_busy_without_record_or_later_execution(self):
        import tempfile
        from types import SimpleNamespace
        from backend.main import Application
        with tempfile.TemporaryDirectory() as folder:
            app=Application(15190,bridge=self.bridge,runtime=folder);events=[]
            app.desktop=SimpleNamespace(require_action_focus=Mock(),hide=Mock(),menu_epoch=1,event=events.append)
            first=asyncio.create_task(app.dispatch('action.execute',{'name':'color','menu_epoch':1}));self.pending.append(first)
            while not self.started.is_set():await asyncio.sleep(.001)
            for _ in range(10):
                with self.assertRaisesRegex(RuntimeError,'本次操作未接受'):
                    await app.dispatch('action.execute',{'name':'moveToTop','menu_epoch':1})
            self.assertEqual(len(self.bridge.tasks.records),1);self.assertFalse(self.bridge._queue)
            self.assertFalse(self.bridge._status_snapshot()['queue_ready'])
            self.assertEqual(self.bridge._status_snapshot()['execution_policy'],'busy-reject')
            self.release.set();await first;await asyncio.sleep(.01)
            self.assertEqual(self.writes,['color']);app.desktop.hide.assert_called_once()
            self.assertFalse(any(e.get('queue_ready') for e in events))
            await app.dispatch('action.execute',{'name':'moveToTop','menu_epoch':1})
            self.assertEqual(self.writes,['color','moveToTop'])

    async def test_production_concurrent_acceptance_window_is_rejected(self):
        import tempfile
        from types import SimpleNamespace
        from backend.main import Application
        with tempfile.TemporaryDirectory() as folder:
            app=Application(15190,bridge=self.bridge,runtime=folder)
            app.desktop=SimpleNamespace(require_action_focus=Mock(),hide=Mock(),menu_epoch=1,event=Mock())
            broadcast_started=asyncio.Event();broadcast_release=asyncio.Event()
            async def broadcast(event):
                if event.get('action')=='color' and not broadcast_started.is_set():
                    broadcast_started.set();await broadcast_release.wait()
            app.broadcast=broadcast;self.release.set()
            first=asyncio.create_task(app.dispatch('action.execute',{'name':'color','menu_epoch':1}));self.pending.append(first)
            try:
                await broadcast_started.wait();self.assertFalse(self.bridge.busy)
                with self.assertRaisesRegex(RuntimeError,'本次操作未接受'):
                    await app.dispatch('action.execute',{'name':'moveToTop','menu_epoch':1})
                self.assertEqual(len(self.bridge.tasks.records),0)
            finally:broadcast_release.set()
            await first;self.assertEqual(self.writes,['color'])
