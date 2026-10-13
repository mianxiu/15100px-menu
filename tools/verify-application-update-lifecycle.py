"""Exercise a frozen older updater build against a real published release.

Use a private bootstrap build when testing the first updater release. It must
have lower PE/service versions and support the normal update endpoints. No
version override or installation bypass is exposed by the application.
"""
import argparse
import asyncio
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid
from tornado.httpclient import AsyncHTTPClient, HTTPRequest, HTTPClientError
from tornado.websocket import websocket_connect

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.application_updates import executable_version, sha256, version
from backend.settings import DEFAULTS, atomic_json


async def main(args):
    profile=ROOT/'.runtime'/('github-update-e2e-'+uuid.uuid4().hex);profile.mkdir()
    entry=profile/'PhotoshopMenu.exe';shutil.copy2(args.old_exe,entry)
    runtime=profile/'data';runtime.mkdir()
    settings={**DEFAULTS,'enabled':False};atomic_json(runtime/'settings.json',settings)
    atomic_json(runtime/'application-update.json',{'auto_check':False,'phase':'idle'})
    atomic_json(runtime/'offline-install.json',{'version':executable_version(entry),'owned':{str(entry):sha256(entry)}})
    baseline=(runtime/'settings.json').read_bytes();old_hash=sha256(entry)
    base=f'http://127.0.0.1:{args.port}';client=AsyncHTTPClient();ws=None;process=None
    async def status():return json.loads((await client.fetch(base+'/api/status',request_timeout=5)).body)
    async def call(action):
        nonlocal ws
        if ws is None:ws=await websocket_connect(HTTPRequest(base.replace('http','ws')+'/websocket',headers={'Origin':base}))
        identity=uuid.uuid4().hex
        await ws.write_message(json.dumps({'id':identity,'action':action,'args':{}}))
        while True:
            raw=await asyncio.wait_for(ws.read_message(),45)
            if raw is None:raise RuntimeError('Connection ended before update acknowledgement')
            response=json.loads(raw)
            if response.get('id')==identity:
                if not response['ok']:raise RuntimeError(response['error'])
                return response['data']
    async def wait_for(predicate,seconds=60):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            try:
                item=await status()
                if predicate(item):return item
            except (OSError,HTTPClientError):pass
            await asyncio.sleep(.25)
        raise RuntimeError('Bounded wait exceeded; no process was killed')
    try:
        try:await client.fetch(base+'/api/health',request_timeout=1)
        except (OSError,HTTPClientError):pass
        else:raise RuntimeError('Test port already in use')
        process=subprocess.Popen([str(entry),'--headless','--no-desktop','--port',str(args.port),'--data-dir',str(runtime)],
                                 cwd=profile,creationflags=subprocess.CREATE_NO_WINDOW)
        initial=await wait_for(lambda s:s['version']==executable_version(args.old_exe))
        assert not initial['menu']['native_hotkeys'] and not initial['photoshop']['busy']
        started=time.monotonic();await call('application.update.check')
        checked=await wait_for(lambda s:s['application_update']['phase'] not in ('idle','checking'))
        update=checked['application_update']
        assert update['phase']=='available' and update['available'],update
        assert version(update['release']['version'])>version(initial['version'])
        assert sha256(entry)==old_hash,'Check must not replace the running entry'
        await call('application.update.download')
        downloaded=await wait_for(lambda s:s['application_update']['phase'] not in ('available','downloading'),600)
        update=downloaded['application_update'];assert update['phase']=='ready',update
        new_hash=update['staged']['sha256'];new_version=update['staged']['version']
        assert sha256(entry)==old_hash,'Download must not replace the running entry'
        await call('application.update.install');ws.close();ws=None
        final=await wait_for(lambda s:s['version']==new_version and s['application_update'].get('installation',{}).get('phase')=='completed',90)
        assert Path(final['service']['executable'])==entry
        assert sha256(entry)==new_hash and (runtime/'settings.json').read_bytes()==baseline
        receipt=json.loads((runtime/'offline-install.json').read_text('utf-8'))
        assert receipt['owned'][str(entry)]==new_hash and receipt['version']==new_version
        job=runtime/'application-updates'/final['application_update']['job']
        assert sha256(job/'previous-PhotoshopMenu.exe')==old_hash
        assert final['application_update']['auto_check'] is False
        assert not final['menu']['native_hotkeys'] and not final['photoshop']['busy']
        report={'from':initial['version'],'to':final['version'],'anonymous_release':update['release']['url'],
                'entry':str(entry),'profile':str(profile),'original_sha256':old_hash,'new_sha256':new_hash,
                'config_preserved':True,'installation_receipt_updated':True,'old_exe_recoverable':True,
                'actual_updater_endpoints':True,'check_download_never_replace':True,
                'elapsed_seconds':round(time.monotonic()-started,2),'scope':'Isolated older frozen bootstrap; real GitHub API, assets, production updater endpoints and separate EXE helper. No Photoshop documents modified.'}
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
        print(json.dumps(report,ensure_ascii=False),flush=True)
        await call('service.quit');ws.close();ws=None
        if process:await asyncio.to_thread(process.wait,45)
    finally:
        if ws:ws.close()
        client.close()
        # Failure leaves processes/data for diagnosis, never forcibly kills.


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('old_exe',type=Path);parser.add_argument('--port',type=int,default=15163)
    parser.add_argument('--output',type=Path,default=ROOT/'.runtime/github-update-e2e.json')
    asyncio.run(main(parser.parse_args()))
