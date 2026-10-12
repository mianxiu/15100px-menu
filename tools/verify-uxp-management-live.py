"""Actual installed backend lifecycle test. Requires PS closed, never closes it."""
import asyncio
import hashlib
import json
from pathlib import Path
from urllib.request import Request,urlopen
from tornado.httpclient import HTTPRequest
from tornado.websocket import websocket_connect

ROOT=Path(__file__).resolve().parents[1]
async def main():
    ws=await websocket_connect(HTTPRequest('ws://127.0.0.1:15151/websocket',headers={'Origin':'http://127.0.0.1:15151'}))
    results=[]
    async def request(action,args=None):
        await ws.write_message(json.dumps({'id':action,'action':action,'args':args or {}}))
        while True:
            reply=json.loads(await asyncio.wait_for(ws.read_message(),10))
            if reply.get('id')==action:results.append(reply);assert reply['ok'],reply;return reply['data']
    try:
        status=await request('status');config=Path(status['data_dir'])/'uxp-config.json'
        credential=config.read_bytes();plugin=Path(status['uxp']['plugin_dir'])
        before={n:hashlib.sha256((plugin/n).read_bytes()).hexdigest() for n in ('manifest.json','main.js','labels.js','probe-config.js')}
        await request('uxp.install')
        await request('uxp.disable')
        assert not (await request('status'))['uxp']['enabled']
        await request('uxp.enable')
        payload=urlopen('http://127.0.0.1:15151/api/uxp/export').read()
        boundary='live-uxp-management'
        body=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="uxp.zip"\r\nContent-Type: application/zip\r\n\r\n'.encode()+payload+f'\r\n--{boundary}--\r\n'.encode())
        preview=json.load(urlopen(Request('http://127.0.0.1:15151/api/uxp/preview',data=body,headers={'Content-Type':f'multipart/form-data; boundary={boundary}','Origin':'http://127.0.0.1:15151'})))
        assert preview['ok'],preview
        await request('uxp.install',{'token':preview['data']['token']})
        await request('uxp.rollback')
        await request('uxp.uninstall')
        assert not plugin.exists()
        assert config.read_bytes()==credential
        await request('uxp.rollback')
        assert (await request('status'))['uxp']['installed']
        assert config.read_bytes()==credential
        assert {n:hashlib.sha256((plugin/n).read_bytes()).hexdigest() for n in before}==before
        report={'entry':status['service'],'results':results,'export_import':True,'plugin_files_restored':True,'credentials_preserved':True,'scope':'Actual installed service and real plugin deployment folder with Photoshop closed; PS loading/execution checked separately.'}
        (ROOT/'.runtime/uxp-management-live-0.4.72.json').write_text(json.dumps(report,indent=2),'utf-8')
        print(json.dumps({'version':status['version'],'install_update_disable_enable_rollback_uninstall':True,'plugin_files_restored':True,'credentials_preserved':True}))
    finally:ws.close()
asyncio.run(main())
