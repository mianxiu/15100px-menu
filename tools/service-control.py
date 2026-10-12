"""Read service identity or request normal idle shutdown, never kill a process."""
import argparse,asyncio,json,time
from pathlib import Path
from tornado.httpclient import AsyncHTTPClient,HTTPRequest
from tornado.websocket import websocket_connect
async def main():
    parser=argparse.ArgumentParser();parser.add_argument('operation',choices=('status','quit'))
    parser.add_argument('--output',type=Path);args=parser.parse_args()
    client=AsyncHTTPClient();url='http://127.0.0.1:15151'
    status=json.loads((await client.fetch(url+'/api/status',request_timeout=5)).body)
    compact={key:status[key] for key in ('version','service','photoshop','menu','data_dir')}
    if args.output:args.output.write_text(json.dumps(compact,indent=2),'utf-8')
    if args.operation=='quit':
        if status['photoshop']['busy']:raise RuntimeError('Operation running or unknown; do not update')
        ws=await websocket_connect(HTTPRequest(url.replace('http','ws')+'/websocket',headers={'Origin':url}))
        await ws.read_message();await ws.write_message(json.dumps({'id':'release-quit','action':'service.quit','args':{}}))
        ws.close()
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            try:await client.fetch(url+'/api/health',request_timeout=1)
            except Exception:break
            await asyncio.sleep(.2)
        else:raise RuntimeError('Normal shutdown did not complete')
        print('Service exited normally')
    else:print(json.dumps(compact,ensure_ascii=False))
asyncio.run(main())
