"""Measure completion-to-current-selection feedback on the running service.

Only a disposable document is modified. Each next operation starts after the
previous receipt is confirmed and the service reports the exact new selection.
This is a production bridge/cache test, not physical menu input latency.
"""
import asyncio
import json
from pathlib import Path
import shutil
import statistics
import sys
import time
from urllib.request import urlopen
import win32com.client

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.uxp_bridge import UxpBridge
from backend.version import APP_VERSION

def status():
    return json.load(urlopen('http://127.0.0.1:15151/api/status',timeout=3))

async def current_selection(document,layer):
    deadline=time.perf_counter()+5
    while time.perf_counter()<deadline:
        value=await asyncio.to_thread(status)
        context=value['photoshop']['layer_context']
        if context.get('document_id')==document and context.get('layer_ids')==[layer]:
            return context
        await asyncio.sleep(.005)
    raise RuntimeError('Service selection feedback did not become current')

async def main():
    initial=status()
    assert initial['version']==APP_VERSION and initial['photoshop']['uxp_ready']
    assert not initial['photoshop']['busy'] and not initial['menu']['visible']
    folder=ROOT/'.runtime'/('creation-readiness-'+str(time.time_ns()))
    folder.mkdir()
    config=folder/'uxp-config.json'
    shutil.copy2(Path(initial['data_dir'])/'uxp-config.json',config)
    bridge=UxpBridge(folder/'tasks.json',config)
    app=win32com.client.GetActiveObject('Photoshop.Application')
    previous=app.ActiveDocument if app.Documents.Count else None
    app.DoJavaScript('app.documents.add(64,64,72,"Creation readiness scratch",NewDocumentMode.RGB,DocumentFill.TRANSPARENT);var d=app.activeDocument;d.selection.selectAll();d.selection.fill(app.foregroundColor);d.selection.deselect();')
    scratch=app.ActiveDocument
    document=int(app.DoJavaScript('app.activeDocument.id'))
    count=int(app.DoJavaScript('app.activeDocument.layers.length'))
    samples=[]
    try:
        layer=int(app.DoJavaScript('app.activeDocument.activeLayer.id'))
        context=await current_selection(document,layer)
        for action in ['adjustment.curves','layer.new']*4:
            frozen={key:context[key] for key in ('session','document_id','layer_ids')}
            frozen['active_layer_id']=context['layer_ids'][0]
            started=time.perf_counter()
            result=await bridge.execute(action,frozen_target=frozen)
            completed=time.perf_counter()
            assert not bridge.busy and not bridge.transport.pending.value
            wire=json.loads((bridge.transport.folder/'probe-request.json').read_text('utf-8-sig'))
            receipt=json.loads((bridge.transport.folder/('result-'+wire['id']+'.json')).read_text('utf-8-sig'))
            assert receipt['phase']=='completed' and receipt['operation']=='set_label'
            layer=receipt['result']['layer_id']
            context=await current_selection(document,layer)
            ready=time.perf_counter()
            count+=1
            assert int(app.DoJavaScript('app.activeDocument.activeLayer.id'))==layer
            assert int(app.DoJavaScript('app.activeDocument.layers.length'))==count
            samples.append({'action':action,'task_id':result['task_id'],
                'execute_ms':round((completed-started)*1000,2),
                'feedback_after_completion_ms':round((ready-completed)*1000,2),
                'total_to_current_feedback_ms':round((ready-started)*1000,2)})
        waits=[sample['feedback_after_completion_ms'] for sample in samples]
        report={'version':APP_VERSION,'plugin':initial['photoshop']['uxp_version'],
            'samples':samples,'feedback_median_ms':round(statistics.median(waits),2),
            'feedback_max_ms':max(waits),'all_operations_confirmed_once':True,
            'scope':'Real PS consecutive scratch creation through production bridge; actual running backend selection cache. Feedback timing uses confirmed receipt layer ID and HTTP polling; independent COM readback follows outside timing. Not physical CapsLock/menu latency.'}
        (ROOT/f'.runtime/creation-readiness-{APP_VERSION}.json').write_text(json.dumps(report,indent=2),'utf-8')
        print(json.dumps(report),flush=True)
    finally:
        await bridge.close()
        app.ActiveDocument=scratch
        scratch.Close(2)
        if previous is not None:app.ActiveDocument=previous

asyncio.run(main())
