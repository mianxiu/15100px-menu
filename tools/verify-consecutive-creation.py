"""Confirm each receipt supplies the next target, with no polling or retry."""
import asyncio,json,shutil,sys,time
from pathlib import Path
from urllib.request import urlopen
import win32com.client
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.uxp_bridge import UxpBridge
from backend.version import APP_VERSION

async def main():
    status=json.load(urlopen('http://127.0.0.1:15151/api/status'))
    assert status['version']==APP_VERSION and status['photoshop']['uxp_ready']
    assert not status['photoshop']['busy'] and not status['menu']['visible']
    folder=ROOT/'.runtime'/('consecutive-creation-'+str(time.time_ns()));folder.mkdir()
    config=folder/'uxp-config.json';shutil.copy2(Path(status['data_dir'])/'uxp-config.json',config)
    bridge=UxpBridge(folder/'tasks.json',config)
    app=win32com.client.GetActiveObject('Photoshop.Application')
    previous=app.ActiveDocument if app.Documents.Count else None
    app.DoJavaScript('app.documents.add(64,64,72,"Consecutive creation scratch",NewDocumentMode.RGB,DocumentFill.TRANSPARENT);')
    scratch=app.ActiveDocument
    target=await asyncio.to_thread(bridge._capture_target)
    evidence=[]
    try:
        for action in ['layer.new','adjustment.curves','adjustment.hueSaturation','layer.new','adjustment.colorBalance','adjustment.blackWhite','layer.solid','layer.new','layer.group','layer.new']:
            frozen={key:target[key] for key in ('session','document_id','layer_ids')}
            frozen['active_layer_id']=frozen['layer_ids'][0]
            started=time.perf_counter()
            result=await bridge.execute(action,frozen_target=frozen)
            elapsed=(time.perf_counter()-started)*1000
            created=json.loads(result['result'])
            target=bridge.layer_context
            assert target['document_id']==frozen['document_id']
            assert target['layer_ids']==[created['layer_id']] and target['quick_mask']==127
            assert not bridge.busy and not bridge.transport.pending.value
            evidence.append({'action':action,'task_id':result['task_id'],
                'anchor':frozen['active_layer_id'],'created':created['layer_id'],
                'placement_moves':created['placement_moves'],'execute_ms':round(elapsed,2)})
            # No timer, polling, COM read or capture before the next operation.
        count=int(app.DoJavaScript('(function(){function count(ls){var n=0;for(var i=0;i<ls.length;i++){n++;if(ls[i].typename==="LayerSet")n+=count(ls[i].layers);}return n;}return count(app.activeDocument.layers);})();'))
        assert count==11
        assert int(app.DoJavaScript('app.activeDocument.activeLayer.id'))==target['layer_ids'][0]
        report={'version':APP_VERSION,'plugin':status['photoshop']['uxp_version'],
            'cases':evidence,'scope':'Real PS scratch; confirmed result supplies exact next target, ten consecutive operations including grouping then native inside-group creation, without additional capture, polling, wait or retry. Physical menu opening remains separate.'}
        (ROOT/f'.runtime/consecutive-creation-{APP_VERSION}.json').write_text(json.dumps(report,indent=2),'utf-8')
        print(json.dumps(report),flush=True)
    finally:
        unresolved=bool(bridge.transport.pending.value or bridge.transport.pending.error)
        await bridge.close()
        if unresolved:print('Original result unresolved; scratch retained, no further Photoshop control')
        else:
            app.ActiveDocument=scratch;scratch.Close(2)
            if previous is not None:app.ActiveDocument=previous

asyncio.run(main())
