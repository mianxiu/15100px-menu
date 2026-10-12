"""Exercise the installed service's Home/new-preset path on an empty PS."""
import asyncio
import json
import sys
import time
from pathlib import Path
from urllib.request import urlopen
import win32com.client
from tornado.httpclient import HTTPRequest
from tornado.websocket import websocket_connect

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.version import APP_VERSION

async def main():
    url='http://127.0.0.1:15151';s=json.load(urlopen(url+'/api/status'))
    assert s['version']==APP_VERSION and not s['photoshop']['busy'] and not s['menu']['visible']
    assert s['photoshop']['uxp_version']=='0.3.2'
    app=win32com.client.GetActiveObject('Photoshop.Application')
    assert int(app.Documents.Count)==0,'No user document can be touched by this verifier'
    app.DoJavaScript('app.bringToFront();');await asyncio.sleep(.3)
    socket=await websocket_connect(HTTPRequest(url.replace('http','ws')+'/websocket',headers={'Origin':url}))
    async def call(action,args):
        identity=str(time.time_ns());await socket.write_message(json.dumps({'id':identity,'action':action,'args':args}))
        while True:
            message=json.loads(await asyncio.wait_for(socket.read_message(),20))
            if message.get('id')==identity:
                assert message['ok'],message
                return message['data']
    created=None
    try:
        shown=await call('panel.hold_begin',{})
        assert shown['panel_context']['kind']=='home'
        item=s['recent_documents']['items'][0]
        result=await call('document.recent',{'params':{'preset_id':item['id']}})
        created=json.loads(result['result'])['document_id']
        actual=app.DoJavaScript('app.activeDocument.id+"|"+app.activeDocument.width.as("px")+"|"+app.activeDocument.height.as("px");').split('|')
        assert int(actual[0])==created and int(app.Documents.Count)==1
        latest=json.load(urlopen(url+'/api/status'))
        task=next(t for t in latest['tasks']['items'] if t['id']==result['task_id'])
        assert task['state']=='succeeded' and task['channel']=='uxp-local-files'
        assert not latest['photoshop']['busy'] and not latest['menu']['visible']
        report={'version':APP_VERSION,'service':s['service'],'preset':item,'menu_context':shown['panel_context'],
                'result':result,'task':task,'independent_dimensions':actual,
                'scope':'Actual installed EXE/API and native Home popup; not physical click/hold acceptance'}
        (ROOT/'.runtime/recent-production-live.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
        print('PASS installed Home popup -> recent preset -> real UXP document, task succeeded, independent dimensions')
    finally:
        socket.close()
        if created is not None:
            app.DoJavaScript('if(app.activeDocument.id!=='+str(created)+')throw Error("Scratch target changed");app.activeDocument.close(SaveOptions.DONOTSAVECHANGES);')

asyncio.run(main())
