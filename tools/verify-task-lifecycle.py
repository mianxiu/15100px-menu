"""Exercise task records using actual PS writes only in our scratch document."""
import asyncio
import json
from pathlib import Path
import sys
import time
import threading
from urllib.request import urlopen

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.photoshop_bridge import PhotoshopBridge
from backend.tasks import TaskStore, TaskCancelled

async def main():
    live=json.load(urlopen('http://127.0.0.1:15151/api/status',timeout=5))
    assert not live['photoshop']['busy'], 'Do not interrupt a running operation'
    history = Path('.runtime/task-history-photoshop-verification.json')
    bridge=PhotoshopBridge(task_history=history)
    loop=asyncio.get_running_loop()
    async def js(source):
        return await loop.run_in_executor(bridge.executor,lambda:bridge._application().DoJavaScript(source))
    name='Menu task verification '+str(time.time_ns())
    quoted=json.dumps(name)
    previous=None
    changes=[]
    bridge.tasks.on_change=lambda task:changes.append({'id':task['id'],'state':task['state']})
    try:
        previous=await js("app.documents.length?app.activeDocument.name:''")
        await js(f'app.documents.add(32,32,72,{quoted},NewDocumentMode.RGB,DocumentFill.TRANSPARENT);')
        def read_color():
            return js("(function(){var s=stringIDToTypeID,r=new ActionReference();r.putEnumerated(s('layer'),s('ordinal'),s('targetEnum'));return typeIDToStringID(executeActionGet(r).getEnumerationValue(s('color')));})();")
        red=await bridge.execute('label.red')
        assert await read_color()=='red'
        original_capture=bridge._capture_target
        started=threading.Event()
        def delayed_capture():
            started.set()
            bridge._application().DoJavaScript('$.sleep(600);')
            return original_capture()
        bridge._capture_target=delayed_capture
        pending=asyncio.create_task(bridge.execute('label.blue'))
        try:
            while not started.is_set():await asyncio.sleep(.001)
            cancelled_id=bridge.tasks.snapshot()['items'][0]['id']
            bridge.request_cancel(cancelled_id)
            try:await pending
            except TaskCancelled:pass
            else:raise AssertionError('Cancelled task was dispatched')
            assert bridge.tasks.get(cancelled_id)['state']=='cancelled'
            assert await read_color()=='red', 'Cancelled blue label changed scratch document'
        finally:
            bridge._capture_target=original_capture
            await asyncio.gather(pending,return_exceptions=True)
        cleared=await bridge.execute('label.none')
        assert await read_color()=='none'
        assert red['task_id']!=cleared['task_id']
        for result in (red,cleared):
            record=bridge.tasks.get(result['task_id'])
            assert record['state']=='succeeded' and record['target']==result['target']
            assert [phase['state'] for phase in record['timeline']]==['capturing','running','succeeded']
            assert sum(phase['duration_ms'] for phase in record['timeline'])==record['elapsed_ms']
            assert [event['state'] for event in changes if event['id']==result['task_id']]==['capturing','capturing','running','succeeded']
        await bridge.tasks.flush()
        restored=TaskStore(path=history)
        try:
            assert restored.get(cancelled_id)['state']=='cancelled'
            for result in (red,cleared):
                record=restored.get(result['task_id'])
                assert record['state']=='succeeded' and record['restored']
                assert record['target']==result['target']
                assert record['timeline']==bridge.tasks.get(result['task_id'])['timeline']
        finally:await restored.close()
        report={'photoshop_version':str(await loop.run_in_executor(bridge.executor,lambda:bridge._application().Version)),
                'passed':['actual red write and readback','cancel during actual PS read prevents blue write','cancelled task restored','actual clear and readback','unique IDs and ordered transitions','captured target attached to same task','durable result and target restored without replay'],
                'tasks':bridge.tasks.snapshot(),'physical_menu_and_management_acceptance':'pending'}
        Path('.runtime/task-lifecycle-photoshop-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'passed':report['passed'],'ids':[red['task_id'],cleared['task_id']]},ensure_ascii=False))
    finally:
        await js('(function(){for(var i=app.documents.length-1;i>=0;i--){var d=app.documents[i];'
                 +f'if(d.name==={quoted})d.close(SaveOptions.DONOTSAVECHANGES);'+'}'
                 +(f'try{{app.activeDocument=app.documents.getByName({json.dumps(previous)});}}catch(e){{}}' if previous else '')+'}());')
        await bridge.close()

if __name__=='__main__':asyncio.run(main())
