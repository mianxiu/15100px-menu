"""Observe timestamped, document-pinned real PS metadata refresh, read-only retry."""
import argparse,asyncio,json,shutil,sys,time
from pathlib import Path
from urllib.request import urlopen
import win32com.client
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.uxp_bridge import UxpBridge
from benchmark_read_helpers import fixture

async def main(args):
    try:urlopen('http://127.0.0.1:15151/api/health',timeout=1)
    except OSError:pass
    else:raise RuntimeError('Normally stop the idle live service first')
    folder=ROOT/'.runtime'/('read-refresh-'+str(time.time_ns()));folder.mkdir()
    shutil.copy2(args.config,folder/'uxp-config.json');bridge=UxpBridge(folder/'tasks.json',folder/'uxp-config.json')
    app=win32com.client.GetActiveObject('Photoshop.Application');previous=app.ActiveDocument if app.Documents.Count else None
    scratch=None;rows=[];counts=[]
    def js(code):
        if scratch is not None:app.ActiveDocument=scratch
        return app.DoJavaScript(code)
    async def inspect(**payload):return await asyncio.to_thread(bridge.transport.call,'inspect',**payload)
    try:
        for format in ('objects','strings'):
            for refresh in ('poll','events'):
                # Native conversion to 32-bit can flatten/drop named vector
                # layers. Each policy needs an independent fresh fixture.
                js(fixture('shape',4));scratch=app.ActiveDocument;doc_id=int(js('app.activeDocument.id;'))
                dimensions=str(js('[app.activeDocument.width.as("px"),app.activeDocument.height.as("px")].join("x");'))
                assert dimensions=='181x181',('Unexpected fixture dimensions',dimensions)
                await inspect(read_experiment={'mode':'dom','refresh':refresh,'document_id':doc_id,'notification_format':format})
                await asyncio.sleep(.2)
                stats=(await inspect(refresh_probe=True))['refresh_probe']
                for name,script,key,wanted in (
                    ('select upper','app.activeDocument.activeLayer=app.activeDocument.artLayers.getByName("Upper");','layer_ids',None),
                    ('select shape','app.activeDocument.activeLayer=app.activeDocument.artLayers.getByName("Anchor");','layer_ids',None),
                    ('lock','app.activeDocument.activeLayer.positionLocked=true;','locked',True),
                    ('unlock','app.activeDocument.activeLayer.positionLocked=false;','locked',False),
                    ('new','app.activeDocument.artLayers.add();','layer_ids',None),
                    ('undo new','app.activeDocument.activeHistoryState=app.activeDocument.historyStates[app.activeDocument.historyStates.length-2];','layer_ids',None),
                    ('redo new','app.activeDocument.activeHistoryState=app.activeDocument.historyStates[app.activeDocument.historyStates.length-1];','layer_ids',None),
                    ('delete','app.activeDocument.activeLayer.remove();','layer_ids',None),
                    ('depth 32','app.activeDocument.bitsPerChannel=BitsPerChannelType.THIRTYTWO;','quick_mask',7),
                    ('depth 8','app.activeDocument.bitsPerChannel=BitsPerChannelType.EIGHT;','quick_mask',127)):
                    epoch=time.time()*1000;started=time.perf_counter();identity=int(js(script+'app.activeDocument.activeLayer.id;'))
                    path=bridge.transport.folder/'layer-context.json';deadline=time.perf_counter()+2.5;value={};reads=0
                    while time.perf_counter()<deadline:
                        try:value=json.loads(path.read_text('utf-8-sig'))
                        except (OSError,json.JSONDecodeError):reads+=1;await asyncio.sleep(.005);continue
                        if value.get('document_id')==doc_id and value.get('plugin_time_ms',0)>=epoch and value.get('layer_ids')==[identity] and (key=='layer_ids' or value.get(key)==wanted):break
                        await asyncio.sleep(.005)
                    else:raise AssertionError({'case':name,'format':format,'refresh':refresh,'last':value})
                    row={'format':format,'refresh':refresh,'case':name,'ms':round((time.perf_counter()-started)*1000,2),'partial_read_retries':reads,'fresh_document_timestamp':True}
                    rows.append(row);print(json.dumps(row),flush=True)
                latest=(await inspect(refresh_probe=True))['refresh_probe']
                counts.append({'format':format,'refresh':refresh,'notifications':latest['notifications']-stats['notifications'],'reads':latest['reads']-stats['reads'],'ready':latest['notification_ready']})
                app.ActiveDocument=scratch;scratch.Close(2);scratch=None
        args.output.write_text(json.dumps({'photoshop':str(app.Version),'dimensions_px':dimensions,'rows':rows,'counts':counts,'scope':'Actual COM/script-driven PS selection, shape lock, make/undo/redo/delete and depth changes; strict doc ID and post-mutation timestamp. Readback parse failures retried, commands never replayed. Not a physical mouse/keyboard event test.'},indent=2),'utf-8')
    finally:
        if not bridge.transport.pending.value:
            try:await inspect(read_experiment=None)
            except Exception:pass
            if scratch:app.ActiveDocument=scratch;scratch.Close(2)
            if previous:app.ActiveDocument=previous
        await bridge.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    asyncio.run(main(p.parse_args()))
