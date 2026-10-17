import importlib.util,json,math,os,sys,time,uuid
from pathlib import Path
from urllib.request import urlopen
import win32com.client
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'tools'));from benchmark_read_helpers import fixture,summary
sp=importlib.util.spec_from_file_location('diverse',R/'tools/verify-diverse-layers.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
import argparse
p=argparse.ArgumentParser(description='Read-only DOM versus scalar multiGet tree parity on owned PS scratch documents; temporary companion fixture must already be loaded.')
p.add_argument('--probe-folder',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--modal',action='store_true');p.add_argument('--cases',default='');p.add_argument('--max-setup-seconds',type=int,default=120);args=p.parse_args()
assert 10<=args.max_setup_seconds<=300,'Use a bounded 10–300 second fixture budget'
F=args.probe_folder;output=args.output;rows=[]
assert 'com.15100px.tree-study' in str(F.resolve()), 'Only the companion probe data folder is permitted'
s=json.load(urlopen('http://127.0.0.1:15151/api/status'));assert not s['photoshop']['busy'] and not s['menu']['visible']
p=win32com.client.GetActiveObject('Photoshop.Application');previous=p.ActiveDocument if p.Documents.Count else None;scratch=None
cases=[(k,4) for k in m.KINDS]+[(k,n) for n in [100,300] for k in ['pixel-effects','smart-effects','mixed','nested']]+[('mixed',1000),('pixel-effects',1000),('background',100)]
if args.cases:cases=[(k,n) for k,n in cases if k+str(n) in args.cases.split(',')]
assert cases,'No matching fixed fixtures'
def save(complete=False,error=None):output.write_text(json.dumps({'version':s['version'],'uxp':s['photoshop']['uxp_version'],'photoshop':str(p.Version),'read_only':True,'scope':'modal-read-only' if args.modal else 'read-only','dom_baseline':'production first tree traversal with cached constants and snapshot-local kind map','complete':complete,'error':error,'samples_per_case':12,'rows':rows},indent=2),'utf-8')
try:
 for kind,count in cases:
  if kind=='mixed':code=fixture('mixed',count).replace('Read strategy benchmark scratch mixed'+str(count),'Diverse owned mixed')
  elif kind=='background':code='app.documents.add(UnitValue(181,"px"),UnitValue(181,"px"),72,"Diverse owned background",NewDocumentMode.RGB,DocumentFill.WHITE);var d=app.activeDocument;d.suspendHistory("Background fixture",'+json.dumps('for(var i=1;i<'+str(count)+';i++)d.artLayers.add();')+');'
  else:code=m.setup(kind,count)
  # Cooperative checks between native duplicate calls; no forced PS stop.
  # A single native call must still return normally. This budget is outside
  # measured reads and never weakens any production request deadline.
  guard='var diverseTreeFixtureDeadline=(new Date()).getTime()+'+str(args.max_setup_seconds*1000)+';function diverseTreeFixtureDuplicate(layer){if((new Date()).getTime()>diverseTreeFixtureDeadline)throw Error("Owned tree fixture setup budget exceeded");return layer.duplicate();}'
  code=guard+code.replace('templates[i%templates.length].duplicate();','diverseTreeFixtureDuplicate(templates[i%templates.length]);').replace('upper.duplicate();','diverseTreeFixtureDuplicate(upper);')
  try:p.DoJavaScript(code)
  except Exception:
   if p.Documents.Count and str(p.ActiveDocument.Name)=='Diverse owned '+kind:scratch=p.ActiveDocument
   raise
  scratch=p.ActiveDocument;doc=int(p.DoJavaScript('app.activeDocument.id;'));samples=[]
  history=str(p.DoJavaScript('app.activeDocument.historyStates.length+"|"+app.activeDocument.activeHistoryState.name;'))
  for iteration in range(5):
   q={'id':uuid.uuid4().hex,'operation':'compare-tree','document_id':doc,'round':iteration,'modal':args.modal,'expires':int(time.time()*1000)+30000}
   temporary=F/(q['id']+'.tmp');temporary.write_text(json.dumps(q),'utf-8');deadline=time.monotonic()+1
   while True:
    try:os.replace(temporary,F/'request.json');break
    except PermissionError:
     if time.monotonic()>deadline:raise
     time.sleep(.006)
   deadline=time.monotonic()+30;value={}
   while time.monotonic()<deadline:
    try:value=json.loads((F/'result.json').read_text('utf-8-sig'))
    except (OSError,ValueError):value={}
    if value.get('id')==q['id']:break
    time.sleep(.004)
   else:raise TimeoutError('Original read-only request did not return; no replay')
   if value.get('error'):
    (R/'.runtime/tree152-error.json').write_text(json.dumps(value,indent=2),'utf-8');raise AssertionError(value['error'])
   assert value['equal'] and value['scope']==('modal-read-only' if args.modal else 'read-only')
   if iteration:samples.extend(value['samples'])
  assert history==str(p.DoJavaScript('app.activeDocument.historyStates.length+"|"+app.activeDocument.activeHistoryState.name;')),'Read-only probe changed history'
  row={'kind':kind,'requested_layers':count,'actual_layers':value['count'],'all_ids_parents_order_groups_equal':True,'history_unchanged':True,'samples':samples,'dom':summary([x['dom'] for x in samples]),'batch':summary([x['batch'] for x in samples])};rows.append(row);save()
  print(json.dumps({k:v for k,v in row.items() if k!='samples'}),flush=True)
  scratch.Close(2);scratch=None
 save(True)
except Exception as error:
 save(False,str(error));raise
finally:
 if scratch:p.ActiveDocument=scratch;scratch.Close(2)
 if previous:p.ActiveDocument=previous
