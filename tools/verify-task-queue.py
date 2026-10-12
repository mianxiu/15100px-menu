"""Verify FIFO/cancellation/target guards using only an owned PS scratch document."""
import asyncio,json,sys,threading,time
from pathlib import Path
from urllib.request import urlopen
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.photoshop_bridge import PhotoshopBridge
from backend.tasks import TaskCancelled

async def main():
    live=json.load(urlopen('http://127.0.0.1:15151/api/status',timeout=5))
    assert not live['photoshop']['busy'],'Do not interrupt a production operation'
    bridge=PhotoshopBridge();loop=asyncio.get_running_loop();events=[]
    bridge.tasks.on_change=lambda task:events.append({'id':task['id'],'state':task['state']})
    async def js(source):return await loop.run_in_executor(bridge.executor,lambda:bridge._application().DoJavaScript(source))
    name='Menu queue verification '+str(time.time_ns());quoted=json.dumps(name);previous=None;pending=[]
    original_execute=bridge._execute;started=threading.Event()
    def delayed(action):
        if action=='label.red':
            started.set();bridge._captured_app.DoJavaScript('$.sleep(600);')
        return original_execute(action)
    bridge._execute=delayed
    async def start():
        started.clear();task=asyncio.create_task(bridge.execute('label.red',enqueue=True));pending.append(task)
        deadline=time.monotonic()+5
        while not started.is_set():
            if task.done():await task
            assert time.monotonic()<deadline,'COM did not start'
            await asyncio.sleep(.001)
        return task
    async def enqueue(action):
        previous_count=len(bridge._queue);task=asyncio.create_task(bridge.execute(action,enqueue=True));pending.append(task)
        deadline=time.monotonic()+3
        while len(bridge._queue)==previous_count:
            if task.done():await task
            assert time.monotonic()<deadline,'Request did not enqueue'
            await asyncio.sleep(.001)
        return task,bridge._queue[-1]
    async def color():return await js("(function(){var s=stringIDToTypeID,r=new ActionReference();r.putEnumerated(s('layer'),s('ordinal'),s('targetEnum'));return typeIDToStringID(executeActionGet(r).getEnumerationValue(s('color')));})();")
    try:
        previous=await js("app.documents.length?app.activeDocument.name:''")
        await js(f'app.documents.add(32,32,72,{quoted},NewDocumentMode.RGB,DocumentFill.TRANSPARENT);app.activeDocument.activeLayer.name="original";')
        first=await start();blue,blue_id=await enqueue('label.blue');green,green_id=await enqueue('label.grain')
        bridge.request_cancel(blue_id)
        try:await blue
        except TaskCancelled:pass
        else:raise AssertionError('Cancelled queued blue dispatched')
        red_result=await first;green_result=await green
        assert await color()=='grain','FIFO green write/readback failed'
        assert green_result['target']==red_result['target'],'Queued target binding changed'
        assert bridge.tasks.get(blue_id)['state']=='cancelled'
        assert [e['state'] for e in events if e['id']==green_id]==['queued','capturing','capturing','running','succeeded']
        def change_target(action):
            result=delayed(action)
            if action=='label.red':bridge._captured_app.DoJavaScript('app.activeDocument.artLayers.add().name="changed selection";')
            return result
        bridge._execute=change_target
        first=await start();blue,changed_id=await enqueue('label.blue');await first
        try:await blue
        except TaskCancelled:pass
        else:raise AssertionError('Changed selection was modified')
        assert await color()=='none','New selection was changed'
        await js('app.activeDocument.activeLayer=app.activeDocument.layers.getByName("original");')
        assert await color()=='red','Original target color did not remain red'
        bridge._execute=delayed;bridge.queue_timeout=.03
        first=await start();blue,expired_id=await enqueue('label.blue')
        try:await blue
        except TaskCancelled:pass
        else:raise AssertionError('Expired task dispatched')
        assert bridge.busy,'Queue deadline released running COM ownership'
        await first;assert await color()=='red'
        report={'passed':['actual FIFO final green readback','queued cancellation prevents blue','same original COM/target binding','changed selection prevents queued write','queue deadline prevents write without interrupting running task'],
                'photoshop_version':str(await loop.run_in_executor(bridge.executor,lambda:bridge._application().Version)),
                'tasks':bridge.tasks.snapshot(),'events':events,
                'scope':'independent source bridge, actual COM commands in owned scratch document',
                'physical_menu_and_management_acceptance':'pending','modal_waiting':'not implemented'}
        Path('.runtime/task-queue-photoshop-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'passed':report['passed'],'tasks':len(report['tasks']['items'])},ensure_ascii=False))
    finally:
        await asyncio.gather(*pending,return_exceptions=True)
        await js('(function(){for(var i=app.documents.length-1;i>=0;i--){var d=app.documents[i];'+f'if(d.name==={quoted})d.close(SaveOptions.DONOTSAVECHANGES);'+'}'+(f'try{{app.activeDocument=app.documents.getByName({json.dumps(previous)});}}catch(e){{}}' if previous else '')+'}());')
        await bridge.close()
if __name__=='__main__':asyncio.run(main())
