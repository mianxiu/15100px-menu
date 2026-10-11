"""Exercise task records using actual PS writes only in our scratch document."""
import asyncio
import json
from pathlib import Path
import sys
import time
from urllib.request import urlopen

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.photoshop_bridge import PhotoshopBridge
from backend.tasks import TaskStore

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
        cleared=await bridge.execute('label.none')
        assert await read_color()=='none'
        assert red['task_id']!=cleared['task_id']
        for result in (red,cleared):
            record=bridge.tasks.get(result['task_id'])
            assert record['state']=='succeeded' and record['target']==result['target']
            assert [event['state'] for event in changes if event['id']==result['task_id']]==['capturing','capturing','running','succeeded']
        await bridge.tasks.flush()
        restored=TaskStore(path=history)
        try:
            for result in (red,cleared):
                record=restored.get(result['task_id'])
                assert record['state']=='succeeded' and record['restored']
                assert record['target']==result['target']
        finally:await restored.close()
        report={'photoshop_version':str(await loop.run_in_executor(bridge.executor,lambda:bridge._application().Version)),
                'passed':['actual red write and readback','actual clear and readback','unique IDs and ordered transitions','captured target attached to same task','durable result and target restored without replay'],
                'tasks':bridge.tasks.snapshot(),'physical_menu_and_management_acceptance':'pending'}
        Path('.runtime/task-lifecycle-photoshop-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'passed':report['passed'],'ids':[red['task_id'],cleared['task_id']]},ensure_ascii=False))
    finally:
        await js('(function(){for(var i=app.documents.length-1;i>=0;i--){var d=app.documents[i];'
                 +f'if(d.name==={quoted})d.close(SaveOptions.DONOTSAVECHANGES);'+'}'
                 +(f'try{{app.activeDocument=app.documents.getByName({json.dumps(previous)});}}catch(e){{}}' if previous else '')+'}());')
        await bridge.close()

if __name__=='__main__':asyncio.run(main())
