"""Verify default busy rejection against real PS, only in an owned scratch document."""
import asyncio,json,sys,threading,time
from pathlib import Path
from urllib.request import urlopen
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.photoshop_bridge import PhotoshopBridge
async def main():
    live=json.load(urlopen('http://127.0.0.1:15151/api/status',timeout=5));assert not live['photoshop']['busy']
    bridge=PhotoshopBridge();loop=asyncio.get_running_loop();started=threading.Event();original=bridge._execute
    async def js(source):return await loop.run_in_executor(bridge.executor,lambda:bridge._application().DoJavaScript(source))
    def delayed(action):
        started.set();bridge._captured_app.DoJavaScript('$.sleep(600);');return original(action)
    bridge._execute=delayed;previous=None;pending=None;name='Menu busy rejection '+str(time.time_ns());quoted=json.dumps(name)
    async def color():return await js("(function(){var s=stringIDToTypeID,r=new ActionReference();r.putEnumerated(s('layer'),s('ordinal'),s('targetEnum'));return typeIDToStringID(executeActionGet(r).getEnumerationValue(s('color')));})();")
    try:
        previous=await js("app.documents.length?app.activeDocument.name:''")
        await js(f'app.documents.add(32,32,72,{quoted},NewDocumentMode.RGB,DocumentFill.TRANSPARENT);')
        pending=asyncio.create_task(bridge.execute('label.red'));deadline=time.monotonic()+5
        while not started.is_set():
            if pending.done():await pending
            assert time.monotonic()<deadline
            await asyncio.sleep(.001)
        rejected=0
        for _ in range(10):
            try:await bridge.execute('label.blue')
            except RuntimeError:rejected+=1
            else:raise AssertionError('Busy blue was accepted')
        assert rejected==10 and len(bridge.tasks.records)==1 and not bridge._queue
        await pending;assert await color()=='red'
        await asyncio.sleep(.15);assert await color()=='red','Rejected request executed later'
        bridge._execute=original;await bridge.execute('label.blue');assert await color()=='blue'
        report={'passed':['10 busy requests rejected without task records','no delayed blue after red completed','explicit new blue after completion succeeds'],
                'tasks':bridge.tasks.snapshot(),'scope':'default source execution bridge in owned actual PS scratch document','physical_menu_acceptance':'pending'}
        Path('.runtime/busy-reject-photoshop-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'passed':report['passed'],'rejected':rejected},ensure_ascii=False))
    finally:
        if pending:await asyncio.gather(pending,return_exceptions=True)
        await js('(function(){for(var i=app.documents.length-1;i>=0;i--){var d=app.documents[i];'+f'if(d.name==={quoted})d.close(SaveOptions.DONOTSAVECHANGES);'+'}'+(f'try{{app.activeDocument=app.documents.getByName({json.dumps(previous)});}}catch(e){{}}' if previous else '')+'}());')
        await bridge.close()
if __name__=='__main__':asyncio.run(main())
