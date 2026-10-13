"""Compare protected UXP creation with native PS commands on a scratch document.

Service must be idle and stopped first. Timings exclude setup/readback/undo and
do not represent physical mouse-to-pixel latency. No unknown request is replayed.
"""
import argparse
import asyncio
import json
from pathlib import Path
import shutil
import statistics
import sys
import time
from urllib.request import urlopen
import win32com.client

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.uxp_bridge import UxpBridge

NATIVE={
 'layer.new':"(function(){var r=new ActionReference();r.putClass(charIDToTypeID('Lyr '));var d=new ActionDescriptor();d.putReference(charIDToTypeID('null'),r);executeAction(charIDToTypeID('Mk  '),d,DialogModes.NO);return app.activeDocument.activeLayer.name;})();",
 'adjustment.curves':"(function(){var s=stringIDToTypeID,r=new ActionReference();r.putClass(s('adjustmentLayer'));var d=new ActionDescriptor();d.putReference(s('null'),r);var u=new ActionDescriptor(),t=new ActionDescriptor();t.putEnumerated(s('presetKind'),s('presetKindType'),s('presetKindDefault'));u.putObject(s('type'),s('curves'),t);d.putObject(s('using'),s('adjustmentLayer'),u);executeAction(s('make'),d,DialogModes.NO);return app.activeDocument.activeLayer.name;})();"
}
def summary(values):
    return {'median_ms':round(statistics.median(values),2),'min_ms':round(min(values),2),'max_ms':round(max(values),2),'n':len(values)}

async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',type=Path,required=True);parser.add_argument('--samples',type=int,default=10);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--frozen-menu',action='store_true');args=parser.parse_args()
    try:urlopen('http://127.0.0.1:15151/api/health',timeout=1)
    except OSError:pass
    else:raise RuntimeError('Stop idle menu service normally before this benchmark')
    app=win32com.client.GetActiveObject('Photoshop.Application');previous=app.ActiveDocument if app.Documents.Count else None
    folder=ROOT/'.runtime'/('creation-benchmark-'+str(time.time_ns()));folder.mkdir()
    config=folder/'config.json';shutil.copy2(args.config,config)
    bridge=UxpBridge(folder/'tasks.json',config);stages={};result={}
    for method,key in [('_capture_target','capture_ms'),('_bind_menu_target','capture_ms'),('_execute','write_ms')]:
        fn=getattr(bridge,method)
        def timed(*a,_fn=fn,_key=key,**kw):
            start=time.perf_counter()
            try:return _fn(*a,**kw)
            finally:stages[_key]=(time.perf_counter()-start)*1000
        setattr(bridge,method,timed)
    app.DoJavaScript('app.documents.add(64,64,72,"Creation benchmark scratch",NewDocumentMode.RGB,DocumentFill.TRANSPARENT);var d=app.activeDocument;var low=d.artLayers.add();low.name="Lower";var mid=d.artLayers.add();mid.name="Middle";d.selection.selectAll();d.selection.fill(app.foregroundColor);d.selection.deselect();var top=d.artLayers.add();top.name="Top";d.activeLayer=mid;')
    scratch=app.ActiveDocument
    frozen={'session':json.loads((bridge.transport.folder/'probe-last.json').read_text('utf-8-sig'))['session'],
            'document_id':int(app.DoJavaScript('app.activeDocument.id')),
            'active_layer_id':int(app.DoJavaScript('app.activeDocument.activeLayer.id'))}
    frozen['layer_ids']=[frozen['active_layer_id']]
    try:
        for action,script in NATIVE.items():
            measured={'native':[],'uxp':[]}
            for index in range(args.samples+2):
                for mode in (('native','uxp') if index%2==0 else ('uxp','native')):
                    # Undo may restore a different active layer. Reselect the
                    # same filled anchor outside timing for every sample.
                    app.DoJavaScript('app.activeDocument.activeLayer=app.activeDocument.artLayers.getByName("Middle");')
                    start=time.perf_counter()
                    if mode=='native':app.DoJavaScript(script)
                    else:completed=await bridge.execute(action,frozen_target=frozen if args.frozen_menu else None)
                    elapsed=(time.perf_counter()-start)*1000
                    phase={}
                    if mode=='uxp':
                        wire=json.loads((bridge.transport.folder/'probe-request.json').read_text('utf-8-sig'))
                        receipt=json.loads((bridge.transport.folder/('result-'+wire['id']+'.json')).read_text('utf-8-sig'))
                        for key,value in receipt.get('timings_ms',{}).items():phase['plugin_'+key]=value
                        for key,value in json.loads(completed['result']).get('timings_ms',{}).items():phase['plugin_'+key]=value
                    assert int(app.DoJavaScript('app.activeDocument.layers.length'))==5
                    if index>=2:measured[mode].append({'total_ms':elapsed,**(dict(stages) if mode=='uxp' else {}),**phase})
                    app.DoJavaScript('app.activeDocument.activeHistoryState=app.activeDocument.historyStates[app.activeDocument.historyStates.length-2];')
                    assert int(app.DoJavaScript('app.activeDocument.layers.length'))==4
            result[action]={mode:{'summary':{key:summary([v[key] for v in values]) for key in values[0]},'samples':values} for mode,values in measured.items()}
            print(json.dumps({action:{mode:data['summary'] for mode,data in result[action].items()}}),flush=True)
        heartbeat=json.loads((bridge.transport.folder/'probe-last.json').read_text(encoding='utf-8-sig'))
        report={'photoshop':str(app.Version),'plugin':heartbeat['probe_version'],
                'frozen_single_menu':args.frozen_menu,'results':result,'scope':'Native COM-invoked PS command vs protected production UXP bridge; optional frozen single-layer menu identity prepared before timing, checked fresh inside PS modal. Filled middle pixel layer; setup/readback/undo excluded, not physical input-to-display latency.'}
        args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    finally:
        await bridge.close();app.ActiveDocument=scratch;app.DoJavaScript('app.activeDocument.close(SaveOptions.DONOTSAVECHANGES);')
        if previous is not None:app.ActiveDocument=previous

asyncio.run(main())
