import asyncio
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock,patch

from backend.stability import StabilityTest,Stopped,summary
from backend.uxp_bridge import UxpBridge
from backend.commands import command_contracts


class StabilityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.bridge=UxpBridge(self.root/'tasks.json',self.root/'uxp-config.json')
        self.app=SimpleNamespace(runtime=self.root,bridge=self.bridge,operation_lock=asyncio.Lock(),
            broadcast=AsyncMock(),require_uxp_enabled=lambda:None,desktop=None,photoshop_launcher=SimpleNamespace(active=False))
        self.test=StabilityTest(self.app)
    async def asyncTearDown(self):
        await self.bridge.close();self.tmp.cleanup()
    async def test_reserves_before_worker_and_rejects_second_start(self):
        gate=asyncio.Event()
        async def job():await gate.wait()
        with patch.object(self.test,'run',job):
            await self.test.start();self.assertTrue(self.app.operation_lock.locked())
            with self.assertRaisesRegex(RuntimeError,'不排队'):await self.test.start()
            self.assertEqual(len(list(self.test.folder.glob('*.json'))),2)
            self.test.stop();self.assertTrue(self.test.stop_requested)
            self.assertFalse(self.test.task.cancelled())
            gate.set();await self.test.task
            self.test.active=False;self.app.operation_lock.release()
    async def test_restore_is_interrupted_never_resumes(self):
        self.test.folder.mkdir();(self.test.folder/'latest.json').write_text(json.dumps({'schema':1,'phase':'running','run_id':'a'*32}),'utf-8')
        restored=StabilityTest(self.app)
        self.assertEqual(restored.snapshot()['phase'],'interrupted');self.assertFalse(restored.active);self.assertIsNone(restored.task)
    async def test_stop_does_not_cancel_inflight_and_partial_report_persists(self):
        self.test.report={'run_id':'a'*32,'started_at':__import__('time').time(),'steps':[],'round':1,'skipped':[]}
        self.test.focus_check=lambda:None
        started=asyncio.Event();finish=asyncio.Event()
        async def op():started.set();await finish.wait();return {'verified':True}
        worker=asyncio.create_task(self.test.step('host',op));await started.wait()
        self.test.active=True;self.test.stop()
        self.assertFalse(worker.done());finish.set();await worker
        with self.assertRaises(Stopped):await self.test.step('next',op)
        report=json.loads((self.test.folder/'latest.json').read_text('utf-8'))
        self.assertEqual(len(report['steps']),1);self.assertEqual(report['steps'][0]['state'],'passed')
    async def test_unknown_does_not_cleanup_or_replay(self):
        self.test.report={'run_id':'a'*32,'started_at':__import__('time').time(),'rounds':1,'round':0,'steps':[],'skipped':[]}
        self.test.active=True;await self.app.operation_lock.acquire()
        calls=[]
        async def command(step,**kw):
            calls.append(step)
            if step=='fixture':return {'verified':True}
            self.bridge.busy=True;raise RuntimeError('original pending')
        async def read():return {}
        async def monitor():pass
        with patch('backend.stability.host_scope',return_value=(1,lambda:None)),patch('backend.stability.read_heartbeat',return_value={'probe_version':'0.3.46'}),patch.object(type(self.bridge.transport),'folder',new_callable=__import__('unittest.mock',fromlist=['PropertyMock']).PropertyMock,return_value=self.root),patch('backend.stability.machine_info',return_value={}),patch.object(self.test,'monitor',monitor),patch.object(self.test,'command',command),patch.object(self.test,'menu_read',read):
            await self.test.run()
        self.assertEqual(calls,['fixture','label']);self.assertTrue(self.test.report['original_request_pending'])
        self.assertEqual(self.test.report['cleanup'],'retained-for-inspection-no-automatic-cleanup')
        self.assertFalse(self.app.operation_lock.locked());self.bridge.busy=False
    async def test_skip_excluded_from_success_statistics(self):
        rows=[{'stage':'x','state':'passed','elapsed_ms':1},{'stage':'x','state':'skipped','elapsed_ms':1000}]
        self.assertEqual(summary(rows)['x']['samples'],1)
        self.assertNotIn('stability.internal',[x['id'] for x in command_contracts()])
    async def test_menu_reads_completed_mailbox_not_basic_background_cache(self):
        import time
        target={'document_id':2,'layer_ids':[3]}
        request={'folder':self.root,'id':'x','session':'s','deadline':time.monotonic()+.2,'completion_deadline':time.monotonic()+.4}
        value={'schema':1,'session':'s','menu_request_id':'x','menu_phase':'completed','plugin_time_ms':time.time()*1000,
            'kind':'shape-fill','mask':15,'quick_mask':127,**target}
        (self.root/'menu-context-result.json').write_text(json.dumps(value),'utf-8')
        (self.root/'layer-context.json').write_text(json.dumps({**value,'menu_phase':'basic'}),'utf-8')
        self.test.report={'steps':[]};self.test.check=lambda:None
        with patch.object(self.test,'inspect',AsyncMock(return_value={'stability':{'target':target}})),patch.object(self.bridge,'request_menu_context',return_value=request),patch.object(self.bridge,'cancel_menu_context') as cancel:
            result=await self.test.menu_read()
        self.assertEqual(result['kind'],'shape-fill');cancel.assert_called_once_with(request)
    async def test_internal_completion_updates_fresh_layer_feedback(self):
        import time
        context={'schema':1,'session':'s','plugin_time_ms':time.time()*1000,'kind':'pixel','mask':15,'document_id':7,'layer_ids':[8]}
        async def execute(action,before_dispatch,capture,execute):return execute(action)
        with patch.object(self.bridge,'_execute_task',execute),patch.object(self.bridge.transport,'call',return_value={'session':'s','result':{'verified':True},'layer_context':context}):
            await self.bridge.execute_stability('a'*32,'finish')
        self.assertEqual(self.bridge.layer_context['document_id'],7)
        self.assertEqual(self.bridge.layer_context['layer_ids'],[8])
    async def test_late_counter_sample_cannot_write_into_a_new_run(self):
        import threading
        entered=threading.Event();release=threading.Event();closed=[]
        class Collector:
            def __init__(self,pid):pass
            def sample(self):entered.set();release.wait(4);return {'time_ms':1}
            def close(self):closed.append(True)
        self.test.active=True;self.test.host_pid=1;self.test.report={'system_samples':[]}
        with patch('backend.stability.Metrics',Collector):
            task=asyncio.create_task(self.test.monitor())
            self.assertTrue(await asyncio.to_thread(entered.wait,3))
            newer={'system_samples':[]};self.test.report=newer;release.set();await task
        self.assertEqual(newer,{'system_samples':[]});self.assertTrue(closed)
