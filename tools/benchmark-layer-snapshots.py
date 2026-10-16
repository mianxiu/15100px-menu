"""Measure fresh production menu snapshots on disposable Photoshop documents.

No timed COM reads, cached-result reuse, writes through the bridge, or changes
to polling/expiry. Original documents are restored after each run.
"""
import argparse,json,math,statistics,sys,time
from pathlib import Path
from urllib.request import urlopen
import win32com.client
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.uxp_bridge import UxpBridge

def measure(args):
    s=json.load(urlopen('http://127.0.0.1:15151/api/status',timeout=5))
    assert not s['photoshop']['busy'] and not s['photoshop'].get('uxp_recovery',{}).get('active')
    assert not s['menu']['visible'] and not s['photoshop_start']['active'] and s['photoshop']['uxp_ready']
    bridge=UxpBridge(args.output.with_suffix('.tasks.json'),Path(s['data_dir'])/'uxp-config.json')
    ps=win32com.client.GetActiveObject('Photoshop.Application');previous=ps.ActiveDocument if ps.Documents.Count else None
    scratch=None;rows=[]
    def js(code):return ps.DoJavaScript(code)
    def stats(samples):
        ordered=sorted(samples)
        return {'median':round(statistics.median(samples),3),'p95':round(ordered[math.ceil(.95*len(ordered))-1],3),'max':round(max(samples),3)}
    try:
        for count,nested in [(c,False) for c in args.counts]+[(100,True)]:
            js('app.documents.add(32,32,72,"Read148 scratch",NewDocumentMode.RGB,DocumentFill.TRANSPARENT);var d=app.activeDocument;'+
               ('var g=d.layerSets.add();g.artLayers.add();var ls=g.artLayers;' if nested else 'var ls=d.artLayers;')+
               'd.suspendHistory("Disposable benchmark setup",'+json.dumps('for(var i=1;i<'+str(count)+';i++)ls.add();')+');')
            scratch=ps.ActiveDocument
            ids=json.loads(js('(function(){var ls=app.activeDocument.'+('layerSets[0].artLayers' if nested else 'artLayers')+';var a=[];for(var i=0;i<ls.length;i++)a.push(ls[i].id);return "["+a.join(",")+"]";})()'))
            assert len(ids)==count
            for position in (('middle',) if nested else ('top','middle','bottom','multi')):
                indices=[0] if position=='top' else [count-1] if position=='bottom' else [count//2]
                if position=='multi':indices=[count//2,count//2+1]
                selected=[ids[i] for i in indices]
                select='var ss=stringIDToTypeID;'
                for i,id in enumerate(selected):
                    select+='var r=new ActionReference(),v=new ActionDescriptor();r.putIdentifier(ss("layer"),'+str(id)+');v.putReference(ss("null"),r);v.putBoolean(ss("makeVisible"),false);'+('v.putEnumerated(ss("selectionModifier"),ss("selectionModifierType"),ss("addToSelection"));' if i else '')+'executeAction(ss("select"),v,DialogModes.NO);'
                js(select);document=int(js('app.activeDocument.id;'))
                # Fixture construction can occupy Photoshop longer than the
                # heartbeat lease. Await fresh readiness before publishing the
                # first request; never extend that lease or replay a request.
                ready_until=time.monotonic()+25
                while True:
                    try:bridge.transport.folder;break
                    except RuntimeError:
                        if time.monotonic()>=ready_until:raise
                        time.sleep(.05)
                expected=2|(1 if len(indices)==1 and count>1 else 0)|(4 if indices!=list(range(len(indices))) else 0)|(8 if indices!=list(range(count-len(indices),count)) else 0)
                samples=[]
                for iteration in range(args.samples+1):
                    started=time.perf_counter();request=bridge.request_menu_context(iteration)
                    deadline=time.monotonic()+12;value={}
                    while time.monotonic()<deadline:
                        try:value=json.loads((request['folder']/'menu-context-result.json').read_text('utf-8-sig'))
                        except (OSError,ValueError):value={}
                        if value.get('menu_request_id')==request['id'] and value.get('menu_phase')=='completed':break
                        time.sleep(.003)
                    else:raise TimeoutError('Fresh read did not complete; no request replayed')
                    assert value['document_id']==document and value['layer_ids']==sorted(selected) and value['mask']==expected,value
                    assert value['quick_mask']==127 and value['kind']=='pixel' and not value['locked'] and value['same_parent']
                    if iteration:samples.append({'selection_ms':value['timings_ms']['selection_ms'],'roundtrip_ms':round((time.perf_counter()-started)*1000,3)})
                    time.sleep(.025)
                row={'count':count,'nested':nested,'position':position,'samples':samples,**{key:stats([v[key] for v in samples]) for key in ('selection_ms','roundtrip_ms')}}
                rows.append(row);print(json.dumps({k:v for k,v in row.items() if k!='samples'}),flush=True)
            scratch.Close(2);scratch=None
    finally:
        if scratch:ps.ActiveDocument=scratch;scratch.Close(2)
        if previous:ps.ActiveDocument=previous
        bridge.executor.shutdown(wait=True)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps({'backend':s['version'],'uxp':s['photoshop']['uxp_version'],'photoshop':s['photoshop']['photoshop_version'],'physical_key_to_screen_measured':False,'rows':rows},indent=2),'utf-8')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--samples',type=int,default=20);p.add_argument('--counts',type=int,nargs='+',default=[4,100,300]);a=p.parse_args()
    if not 5<=a.samples<=50 or any(not 4<=c<=500 for c in a.counts):p.error('Use 5–50 samples and 4–500 layers')
    measure(a)
