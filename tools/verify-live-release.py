"""Verify the installed EXE identity and real production UXP actions safely."""
import asyncio,hashlib,json,time
from pathlib import Path
from urllib.request import urlopen
from tornado.websocket import websocket_connect
from tornado.httpclient import HTTPRequest
import win32com.client
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.version import APP_VERSION
async def main():
    app=win32com.client.GetActiveObject('Photoshop.Application')
    previous=app.ActiveDocument if app.Documents.Count else None
    app.DoJavaScript('app.documents.add(32,32,72,"Offline package live test",NewDocumentMode.RGB,DocumentFill.TRANSPARENT);app.bringToFront();')
    scratch=app.ActiveDocument;ws=None;results=[]
    try:
        # Photoshop activation completes through Windows messages after JSX.
        # Do not race the production foreground guard immediately after opening.
        await asyncio.sleep(.3)
        ws=await websocket_connect(HTTPRequest('ws://127.0.0.1:15151/websocket',headers={'Origin':'http://127.0.0.1:15151'}))
        for action in ('label.red','label.none'):
            identity=str(time.time_ns())
            await ws.write_message(json.dumps({'id':identity,'action':'action.execute','args':{'name':action}}))
            while True:
                reply=json.loads(await asyncio.wait_for(ws.read_message(),15))
                if reply.get('id')==identity:break
            assert reply.get('ok'),reply
            results.append(reply)
            value=app.DoJavaScript("(function(){var s=stringIDToTypeID,r=new ActionReference();r.putEnumerated(s('layer'),s('ordinal'),s('targetEnum'));return typeIDToStringID(executeActionGet(r).getEnumerationValue(s('color')));})();")
            assert value==action.split('.')[1]
        status=json.load(urlopen('http://127.0.0.1:15151/api/status',timeout=5))
        assert status['version']==APP_VERSION and status['menu']['ready']
        assert status['photoshop']['uxp_ready'] and status['photoshop']['execution_backend']=='uxp-local-files'
        assert all(c['channel']=='uxp-local-files' for c in status['commands'])
        for reply in results:
            task=next(x for x in status['tasks']['items'] if x['id']==reply['data']['task_id'])
            assert task['channel']=='uxp-local-files' and task['state']=='succeeded'
        hashes={};resource=Path(status['service']['resource_root'])
        for name in ('MenuHost.exe','HotkeyHost.exe'):
            expected=hashlib.sha256((ROOT/'native'/name).read_bytes()).hexdigest()
            assert hashlib.sha256((resource/'native'/name).read_bytes()).hexdigest()==expected
            hashes[name]=expected
        report={'service':status['service'],'photoshop':status['photoshop'],'native':hashes,'results':results,
                'scope':'Actual installed EXE, real focus/target guards, independent color readback. Not physical keyboard gesture acceptance.'}
        (ROOT/('.runtime/release-'+APP_VERSION+'-verification.json')).write_text(json.dumps(report,indent=2),'utf-8')
        print(json.dumps({'version':status['version'],'entry':status['service']['executable'],'uxp_ready':True,'labels_readback':True,'native_hashes_match':True}))
    finally:
        if ws:ws.close()
        app.ActiveDocument=scratch;app.DoJavaScript('app.activeDocument.close(SaveOptions.DONOTSAVECHANGES);')
        if previous is not None:app.ActiveDocument=previous
asyncio.run(main())
