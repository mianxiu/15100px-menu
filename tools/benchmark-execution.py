"""Interleaved real PS COM/UXP execution benchmark, only on a scratch document."""
import argparse,asyncio,json,math,os,statistics,sys,time
from pathlib import Path
from urllib.request import urlopen
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.photoshop_bridge import PhotoshopBridge
from backend.uxp_bridge import UxpBridge

def stats(values):
    ordered=sorted(values)
    return {'n':len(values),'median_ms':round(statistics.median(values),2),
            'p95_ms':round(ordered[math.ceil(.95*len(ordered))-1],2),
            'min_ms':round(min(values),2),'max_ms':round(max(values),2)}

async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--samples',type=int,default=30)
    parser.add_argument('--output',type=Path,default=Path('.runtime/execution-performance-0.4.70.json'))
    args=parser.parse_args()
    if args.samples<10:raise ValueError('At least 10 measured samples required')
    import win32com.client
    app=win32com.client.GetActiveObject('Photoshop.Application')
    previous=app.ActiveDocument if app.Documents.Count else None
    bridges={};results={};scratch=None
    try:
        # The menu service must be stopped to prevent competing writes from input.
        try:json.load(urlopen('http://127.0.0.1:15151/api/health',timeout=1))
        except OSError:pass
        else:raise RuntimeError('Exit Photoshop Menu normally before benchmarking')
        app.DoJavaScript('app.documents.add(64,64,72,"Menu performance scratch",NewDocumentMode.RGB,DocumentFill.TRANSPARENT);')
        scratch=app.ActiveDocument
        folder=Path('.runtime')/('benchmark-'+str(time.time_ns()));folder.mkdir()
        bridges={'COM':PhotoshopBridge(folder/'com-tasks.json'),
                 'UXP':UxpBridge(folder/'uxp-tasks.json',Path(os.environ['LOCALAPPDATA'])/'PhotoshopMenu/uxp-config.json')}
        stages={}
        for name,bridge in bridges.items():
            stages[name]={}
            for method,key in (('_capture_target','capture_ms'),('_execute','write_ms')):
                original=getattr(bridge,method)
                def timed(*a,_fn=original,_name=name,_key=key,**kw):
                    start=time.perf_counter_ns()
                    try:return _fn(*a,**kw)
                    finally:stages[_name][_key]=(time.perf_counter_ns()-start)/1e6
                setattr(bridge,method,timed)
        for count in (1,8):
            if count==8:
                app.DoJavaScript('for(var i=0;i<7;i++)app.activeDocument.artLayers.add();var s=stringIDToTypeID;for(var j=0;j<app.activeDocument.layers.length;j++){var d=new ActionDescriptor();var r=new ActionReference();r.putIdentifier(s("layer"),app.activeDocument.layers[j].id);d.putReference(s("null"),r);if(j)d.putEnumerated(s("selectionModifier"),s("selectionModifierType"),s("addToSelection"));d.putBoolean(s("makeVisible"),false);executeAction(s("select"),d,DialogModes.NO);}')
            samples={name:[] for name in bridges}
            # Warm each route, then alternate route order per pair to limit drift.
            for n in range(args.samples+3):
                order=('COM','UXP') if n%2==0 else ('UXP','COM')
                for name in order:
                    # Always change a color; no no-op requests in measured samples.
                    color='red' if name==order[0] else 'blue'
                    start=time.perf_counter_ns();response=await bridges[name].execute('label.'+color)
                    elapsed=(time.perf_counter_ns()-start)/1e6
                    if bridges[name].busy:await asyncio.sleep(0)
                    verified=json.loads(response['result'])
                    if not verified.get('verified') or verified['count']!=count:raise AssertionError(response)
                    actual=app.DoJavaScript('(function(){var s=stringIDToTypeID;var r=new ActionReference();r.putProperty(s("property"),s("targetLayersIDs"));r.putEnumerated(s("document"),s("ordinal"),s("targetEnum"));var l=executeActionGet(r).getList(s("targetLayersIDs"));var a=[];for(var j=0;j<l.count;j++){var q=new ActionReference();q.putIdentifier(s("layer"),l.getReference(j).getIdentifier());a.push(typeIDToStringID(executeActionGet(q).getEnumerationValue(s("color"))));}return a.join(",");}())').split(',')
                    if actual!=[color]*count:raise AssertionError('Independent readback mismatch: '+str(actual))
                    if n>=3:samples[name].append({'total_ms':elapsed,**stages[name]})
            results[str(count)+'_layers']={name:{'summary':{key:stats([v[key] for v in values]) for key in ('total_ms','capture_ms','write_ms')},'samples':values} for name,values in samples.items()}
            print(json.dumps({str(count)+'_layers':{name:value['summary'] for name,value in results[str(count)+'_layers'].items()}},ensure_ascii=False),flush=True)
        report={'photoshop_version':str(app.Version),'uxp_plugin':'0.3.0','date':time.strftime('%Y-%m-%d %H:%M:%S'),
                'scope':'Full source production bridges: target capture, guarded write, verification, task durability and completion. Not physical key-to-screen latency. Readback outside timing. Three warmups per route/scenario; pair order alternated.',
                'results':results,'failures':0,'all_independent_readbacks_passed':True}
        args.output.write_text(json.dumps(report,indent=2),'utf-8')
    finally:
        for bridge in bridges.values():await bridge.close()
        if scratch is not None:
            app.ActiveDocument=scratch;app.DoJavaScript('app.activeDocument.close(SaveOptions.DONOTSAVECHANGES);')
        if previous is not None:app.ActiveDocument=previous

if __name__=='__main__':asyncio.run(main())
