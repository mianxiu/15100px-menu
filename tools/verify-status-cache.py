"""Read-only actual Photoshop status/cache verification; no document writes."""
import asyncio
import json
from pathlib import Path
import sys
import time
from urllib.request import urlopen
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.photoshop_bridge import PhotoshopBridge

async def main():
    live=json.load(urlopen('http://127.0.0.1:15151/api/status',timeout=5))
    assert not live['photoshop']['busy']
    bridge=PhotoshopBridge()
    try:
        await bridge.status(force=True)
        if bridge._status_future is not None:await bridge._status_future
        original=bridge._status
        before=bridge._status_snapshot()
        assert before['connected'] and before['status_fresh']
        calls=[]
        def slow_read():
            calls.append(1)
            bridge._application().DoJavaScript('$.sleep(600);')
            return original()
        bridge._status=slow_read
        started=time.monotonic()
        results=await asyncio.gather(*(bridge.status(force=True) for _ in range(20)))
        duration=time.monotonic()-started
        assert duration<.5 and len(calls)==1
        assert all(r['status_fresh'] and r['status_wait_reason']=='status-read-pending'
                   and r['document']==before['document'] and r['status_updated_at']==before['status_updated_at'] for r in results)
        assert all(r['message']==before['message'] for r in results)
        await bridge._status_future
        after=bridge._status_snapshot()
        assert after['connected'] and after['status_fresh'] and not after['status_read_pending']
        assert after['status_updated_at']!=before['status_updated_at']
        report={'passed':True,'concurrent_requests':20,'actual_com_reads':len(calls),
                'response_batch_seconds':duration,'before':before,'after':after,
                'scope':'independent source bridge; actual read-only PS query with 600ms test delay',
                'physical_management_menu_acceptance':'pending'}
        Path('.runtime/status-cache-photoshop-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'passed':True,'response_batch_seconds':duration,'actual_com_reads':len(calls)},ensure_ascii=False))
    finally:await bridge.close()
if __name__=='__main__':asyncio.run(main())
