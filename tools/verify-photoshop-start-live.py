"""Observe an actual installed startup; never activate COM or modify documents."""
import argparse, asyncio, hashlib, json, time
from pathlib import Path
from urllib.request import urlopen
from tornado.httpclient import HTTPRequest
from tornado.websocket import websocket_connect
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.version import APP_VERSION
URL = 'http://127.0.0.1:15151'

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--check-duplicate', action='store_true')
    args = parser.parse_args()
    samples, duplicate = [], None
    deadline = time.monotonic() + 95
    while time.monotonic() < deadline:
        begin = time.monotonic()
        status = json.load(urlopen(URL+'/api/status', timeout=5))
        launch = status['photoshop_start']
        samples.append({'phase': launch['phase'], 'read_ms': round((time.monotonic()-begin)*1000, 2)})
        if args.check_duplicate and duplicate is None and launch['active']:
            ws = await websocket_connect(HTTPRequest(URL.replace('http','ws')+'/websocket', headers={'Origin':URL}))
            await ws.write_message(json.dumps({'id':'duplicate-start-test','action':'photoshop.start','args':{}}))
            while True:
                reply = json.loads(await asyncio.wait_for(ws.read_message(), 5))
                if reply.get('id') == 'duplicate-start-test': break
            ws.close()
            assert not reply['ok'], reply
            duplicate = reply
        if launch['phase'] in ('failed', 'ready', 'started'):
            assert launch['phase'] == 'ready', launch
            break
        await asyncio.sleep(.5)
    else: raise RuntimeError('Startup did not become ready')
    worker = launch['worker']
    assert status['version'] == worker['version'] == APP_VERSION
    assert worker['state'] == 'succeeded' and not worker['existing_instance']
    assert worker['processor_architecture'] == 'AMD64'
    assert status['photoshop']['uxp_ready'] and status['menu']['ready']
    native = {}
    for name in ('MenuHost.exe', 'HotkeyHost.exe'):
        source = hashlib.sha256((ROOT/'native'/name).read_bytes()).hexdigest()
        bundled = hashlib.sha256((Path(status['service']['resource_root'])/'native'/name).read_bytes()).hexdigest()
        assert source == bundled
        native[name] = source
    report = {'version': status['version'], 'service':status['service'], 'startup':launch,
              'native':native, 'samples':samples, 'duplicate':duplicate,
              'scope':'Actual installed frozen worker cold start and fresh UXP readiness; no physical keyboard gestures.'}
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), 'utf-8')
    print(json.dumps({'ready':True, 'worker_pid':worker['pid'], 'desktop_pid':launch['desktop_pid'],
                     'com_ms':worker['completed_at_ms']-worker['started_at_ms'],
                     'duplicate_rejected':duplicate is not None, 'native_hashes_match':True}))

asyncio.run(main())
