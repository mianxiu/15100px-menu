"""Create only our test documents; UXP writes, independent COM readback."""
import json
import sys
from pathlib import Path
from urllib.request import urlopen
import win32com.client

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.uxp_bridge import UxpTransport
from backend.recent_documents import RecentDocuments

s=json.load(urlopen('http://127.0.0.1:15151/api/status'))
assert not s['photoshop']['busy'] and not s['photoshop_start']['active']
transport=UxpTransport(Path(s['data_dir'])/'uxp-config.json')
heartbeat=json.loads((transport.folder/'probe-last.json').read_text('utf-8-sig'))
assert heartbeat['probe_version']=='0.3.2'
reader=RecentDocuments();snapshot=reader.refresh(heartbeat['photoshop_version'])
assert snapshot['items']
(ROOT/'.runtime/recent-preview.json').write_text(json.dumps(snapshot,ensure_ascii=False),'utf-8')
app=win32com.client.GetActiveObject('Photoshop.Application')
assert int(app.Documents.Count)==0,'This verifier requires an empty Photoshop workspace'
results=[]
samples=[snapshot['items'][0],next(x for x in snapshot['items'] if x['name']=='A4')]
for item in samples:
    preset=reader.resolve(item['id']);expected=transport.call('inspect')['target']
    assert expected['document_ids']==[]
    result=transport.call('new_document',target=expected,preset=preset)['result']
    try:
        values=app.DoJavaScript('(function(){var d=app.activeDocument;return [d.id,d.width.as("px"),d.height.as("px"),d.resolution,String(d.mode)].join("|");})();').split('|',4)
        actual=dict(zip(('id','width','height','resolution'),map(float,values[:4])))
        actual.update(mode=values[4])
        assert actual['id']==result['document_id']
        if preset['units']=='pixelsUnit':
            assert abs(actual['width']-preset['width'])<=.51 and abs(actual['height']-preset['height'])<=.51,actual
        else:assert actual['width']==2480 and actual['height']==3508 and actual['resolution']==300,actual
        try:transport.call('new_document',target=expected,preset=preset)
        except RuntimeError:pass
        else:raise AssertionError('Duplicate stale document target accepted')
        assert int(app.Documents.Count)==1
        results.append({'preset':item,'uxp':result,'independent_com':actual,'stale_target_rejected':True})
    finally:
        app.DoJavaScript('if(app.activeDocument.id!=='+str(result['document_id'])+')throw Error("Scratch target changed");app.activeDocument.close(SaveOptions.DONOTSAVECHANGES);')
(ROOT/'.runtime/recent-uxp-live-verification.json').write_text(json.dumps({'version':'0.3.2','results':results,'all_own_documents_closed':True},ensure_ascii=False,indent=2),'utf-8')
print('PASS actual UXP pixel and A4 preset JSON, independent dimensions, stale targets rejected, own documents closed')
