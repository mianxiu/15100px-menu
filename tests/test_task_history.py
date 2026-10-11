import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from backend.tasks import TaskStore
from backend.tasks import TaskCancelled
from backend.photoshop_bridge import PhotoshopBridge


class HistoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_menu_guard_runs_after_durable_write_wait(self):
        with tempfile.TemporaryDirectory() as folder:
            bridge=PhotoshopBridge(task_history=Path(folder)/'tasks.json')
            bridge._capture_target=lambda:{'document_id':1,'active_layer_id':2,'layer_ids':[2]}
            bridge._execute=Mock()
            flush=bridge.tasks.flush
            changed=False
            async def save():
                nonlocal changed
                await flush()
                if bridge.tasks.snapshot()['items'][0]['state']=='running':changed=True
            bridge.tasks.flush=save
            async def guard(target):
                if changed:raise TaskCancelled('菜单已重新打开')
            try:
                with self.assertRaises(TaskCancelled):await bridge.execute('color',before_dispatch=guard)
                bridge._execute.assert_not_called()
                self.assertEqual(bridge.tasks.snapshot()['items'][0]['state'],'cancelled')
            finally:
                bridge.tasks.flush=flush
                await bridge.close()

    async def test_restart_keeps_results_and_marks_unfinished_unknown_without_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'tasks.json'
            store = TaskStore(path=path)
            done = store.create('label.red', '红色')
            store.update(done, 'running', target={'document_id':7,'layer_ids':[8]})
            store.update(done, 'succeeded', message='done')
            running = store.create('color', '标色')
            store.update(running, 'running')
            capturing = store.create('color', '读取')
            await store.close()
            restored = TaskStore(path=path)
            self.assertEqual(restored.get(done)['state'], 'succeeded')
            self.assertEqual(restored.get(done)['target']['document_id'], 7)
            for task_id in (running,capturing):
                item = restored.get(task_id)
                self.assertEqual(item['state'], 'result-unknown')
                self.assertTrue(item['restored'])
                elapsed = item['elapsed_ms']
                self.assertEqual(restored.get(task_id)['elapsed_ms'], elapsed)
                with self.assertRaises(ValueError):restored.update(task_id,'running')
            await restored.close()
            again = TaskStore(path=path)
            self.assertEqual(again.get(running)['previous_state'],'running')
            await again.close()

    async def test_corrupt_history_preserved_and_modifying_command_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'tasks.json'
            path.write_text('broken', encoding='utf-8')
            bridge = PhotoshopBridge(task_history=path)
            bridge._capture_target = Mock()
            bridge._execute = Mock()
            try:
                with self.assertRaisesRegex(RuntimeError,'读取失败'):await bridge.execute('color')
                bridge._execute.assert_not_called()
                bridge._capture_target.assert_not_called()
                self.assertFalse(bridge.busy)
                self.assertEqual(path.read_text(),'broken')
            finally:
                with self.assertRaises(RuntimeError):await bridge.close()

    async def test_write_failure_prevents_dispatch(self):
        with tempfile.TemporaryDirectory() as folder:
            bridge = PhotoshopBridge(task_history=Path(folder)/'tasks.json')
            bridge.tasks._write = Mock(side_effect=OSError('disk full'))
            bridge._capture_target = Mock()
            bridge._execute = Mock()
            try:
                with self.assertRaisesRegex(RuntimeError,'保存失败'):await bridge.execute('color')
                bridge._execute.assert_not_called()
                bridge._capture_target.assert_not_called()
            finally:
                with self.assertRaises(RuntimeError):await bridge.close()

    async def test_bounded_history_survives_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'tasks.json'
            store = TaskStore(limit=4,path=path)
            ids=[]
            for _ in range(8):
                task_id=store.create('color','标色');ids.append(task_id)
                store.update(task_id,'running');store.update(task_id,'succeeded')
            await store.close()
            self.assertEqual(len(json.loads(path.read_text(encoding='utf-8'))['items']),4)
            restored=TaskStore(limit=4,path=path)
            self.assertEqual([i['id'] for i in restored.snapshot()['items']],ids[-4:][::-1])
            await restored.close()
