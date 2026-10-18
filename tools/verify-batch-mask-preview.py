"""Owned-document batch preview verification; actual input/canvas appearance is separate."""
import asyncio,copy,json,sys,time,shutil,threading,msvcrt
from pathlib import Path
from contextlib import nullcontext
from urllib.request import urlopen
import win32com.client,win32gui
r=Path(__file__).resolve().parents[1];sys.path[:0]=[str(r),str(r/'tools')]
from backend.uxp_bridge import UxpBridge
from backend.mask_preview import MaskPreview
from backend.settings import atomic_json
from quiet_ps_session import inventory,select,ResourceLease
from benchmark_read_helpers import special
n=int(sys.argv[1]);mode=sys.argv[2];normal='normal' in sys.argv
assert 2<=n<=128 and mode in ('feather','density','both','cancel'), 'Invalid batch verification arguments'
work=r/'.runtime'/('batch169-'+str(n)+'-'+mode+'-'+('normal-' if normal else 'low-')+str(time.time_ns()));work.mkdir()
READ=r'''(function(){function quote(v){return '"'+String(v).replace(/\\/g,'\\\\').replace(/"/g,'\\"').replace(/\r/g,'\\r').replace(/\n/g,'\\n')+'"';}
function json(v){if(v===null)return 'null';if(v instanceof Array){var a=[];for(var i=0;i<v.length;i++)a.push(json(v[i]));return '['+a.join(',')+']';}if(typeof v==='object'){var a=[];for(var k in v)a.push(quote(k)+':'+json(v[k]));return '{'+a.join(',')+'}';}return typeof v==='string'?quote(v):String(v);}
var stage='selection';try{var d=app.activeDocument,s=stringIDToTypeID,c=charIDToTypeID;function hex(v){var t='';for(var i=0;i<v.length;i++)t+=('00'+(v.charCodeAt(i)&255).toString(16)).slice(-2);return t;}var r=new ActionReference();r.putProperty(s('property'),s('targetLayersIDs'));r.putEnumerated(s('document'),s('ordinal'),s('targetEnum'));var a=executeActionGet(r).getList(s('targetLayersIDs')),out=[],ids=[];for(var i=0;i<a.count;i++)ids.push(a.getReference(i).getIdentifier());ids.sort(function(a,b){return a-b;});var keys=['adjustment','AGMStrokeStyleInfo','layerEffects','hasVectorMask','hasUserMask','userMaskFeather','userMaskDensity'];for(var i=0;i<ids.length;i++){r=new ActionReference();r.putIdentifier(s('layer'),ids[i]);stage='layer:'+ids[i];var v=executeActionGet(r),values=[];for(var k=0;k<keys.length;k++){stage='content:'+keys[k];var key=s(keys[k]),z=new ActionDescriptor();if(v.hasKey(key)){var t=v.getType(key);if(t===DescValueType.OBJECTTYPE)z.putObject(key,v.getObjectType(key),v.getObjectValue(key));else if(t===DescValueType.LISTTYPE)z.putList(key,v.getList(key));else if(t===DescValueType.BOOLEANTYPE)z.putBoolean(key,v.getBoolean(key));else if(t===DescValueType.DOUBLETYPE)z.putDouble(key,v.getDouble(key));else if(t===DescValueType.INTEGERTYPE)z.putInteger(key,v.getInteger(key));}if(v.hasKey(key))values.push(hex(z.toStream()));else values.push(null);}stage='path:'+ids[i];r=new ActionReference();r.putProperty(s('property'),s('pathContents'));r.putEnumerated(s('path'),s('path'),s('vectorMask'));r.putIdentifier(s('layer'),ids[i]);out.push({id:ids[i],feather:v.getDouble(s('vectorMaskFeather')),density:v.getInteger(s('vectorMaskDensity'))*100/255,content:values,path:hex(executeActionGet(r).toStream())});}var tree=[];function walk(ls,parent){for(var i=0;i<ls.length;i++){tree.push([ls[i].id,parent]);if(ls[i].typename==='LayerSet')walk(ls[i].layers,ls[i].id);}}walk(d.layers,0);var cursor=-1;for(var i=0;i<d.historyStates.length;i++)if(d.historyStates[i]==d.activeHistoryState)cursor=i;return json({document:d.id,active:d.activeLayer.id,selected:ids,members:out,tree:tree,cursor:cursor});}catch(e){return json({read_error:String(e),stage:stage});}})()'''
async def main():
 s=json.load(urlopen('http://127.0.0.1:15151/api/status',timeout=5));assert s['version']=='0.4.169' and s['photoshop']['uxp_version']=='0.3.36' and not s['photoshop']['busy'] and not s['menu']['visible'] and not s['photoshop']['uxp_recovery']['active']
 app=win32com.client.GetActiveObject('Photoshop.Application');ps,_=select(inventory());previous=app.ActiveDocument if app.Documents.Count else None
 # All edits here are in a named disposable document, never in the user's document.
 fixture='app.documents.add(UnitValue(64,"px"),UnitValue(64,"px"),72,"Batch169 '+str(n)+' '+mode+'",NewDocumentMode.RGB,DocumentFill.TRANSPARENT);var d=app.activeDocument;'+special('shape')+'var a=d.activeLayer,ls=[a];for(var i=1;i<'+str(n)+';i++)ls.push(a.duplicate());var s=stringIDToTypeID,c=charIDToTypeID;for(var i=0;i<ls.length;i++){d.activeLayer=ls[i];function set(k,u,v){var r=new ActionReference();r.putIdentifier(s("layer"),ls[i].id);var z=new ActionDescriptor(),to=new ActionDescriptor();z.putReference(s("null"),r);to.putUnitDouble(s(k),s(u),v);z.putObject(s("to"),s("layer"),to);executeAction(s("set"),z,DialogModes.NO);}set("vectorMaskFeather","pixelsUnit",1+i%3);set("vectorMaskDensity","percentUnit",65+i%20);}'
 if mode=='both':fixture+='var g=d.layerSets.add();for(var i=0;i<ls.length;i+=2)ls[i].move(g,ElementPlacement.INSIDE);'
 fixture+='for(var i=0;i<ls.length;i++){var r=new ActionReference();r.putIdentifier(s("layer"),ls[i].id);var z=new ActionDescriptor();z.putReference(s("null"),r);z.putBoolean(s("makeVisible"),false);if(i)z.putEnumerated(s("selectionModifier"),s("selectionModifierType"),s("addToSelection"));executeAction(s("select"),z,DialogModes.NO);}'
 cut=fixture.index(';var d=app.activeDocument;')+1
 fixture=fixture[:cut]+'app.activeDocument.suspendHistory("Batch169 fixture",'+json.dumps(fixture[cut:])+');'
 app.DoJavaScript(fixture);owned=app.ActiveDocument;atomic_json(work/'owned.json',{'id':owned.ID,'name':owned.Name});foreground=win32gui.GetForegroundWindow()
 shutil.copy2(Path(s['data_dir'])/'uxp-config.json',work/'uxp-config.json');bridge=UxpBridge(work/'tasks.json',work/'uxp-config.json');progress=[];preview=None;stop=threading.Event();paused=threading.Event();thread=None
 try:
  deadline=time.monotonic()+12
  while True:
   try:bridge.transport.folder;break
   except RuntimeError:
    if time.monotonic()>deadline:raise
    await asyncio.sleep(.1)
  data=(await asyncio.to_thread(bridge.transport.call,'inspect',shape_inspect=True))['shape_editor'];atomic_json(work/'editor.json',data)
  assert data.get('available') and data.get('mask_batch') and data['live_preview'],data
  before=json.loads(app.DoJavaScript(READ));atomic_json(work/'before.json',before);assert 'read_error' not in before,before
  target=await asyncio.to_thread(bridge._capture_target);assert target['active_layer_id']==before['active'] and target['layer_ids']==before['selected']
  initial={'density':35} if mode=='density' else {'feather':7.5}
  final={'density':42} if mode=='density' else {'feather':12.5,**({'density':42} if mode in ('both','cancel') else {})}
  params={'mask_batch':True,'revision':data['revision'],'mask':initial};preview=MaskPreview(1,params,trace=True)
  def publisher():
   started=time.monotonic();advanced=False;ended=False
   while not stop.is_set():
    if win32gui.GetForegroundWindow()!=foreground:paused.set();preview.cancel();preview.publish();return
    elapsed=time.monotonic()-started
    ack={}
    if preview.binding:
     try:ack=json.loads((preview.binding[0]/('mask-preview-status-'+preview.binding[1]['id']+'.json')).read_text('utf-8-sig'))
     except (OSError,ValueError):pass
     if ack.get('id')!=preview.binding[1]['id'] or ack.get('session')!=preview.binding[1]['session']:ack={}
    if ack.get('seq',0)>=1 and not advanced:
     atomic_json(work/'live-first.json',{'elapsed_ms':round(elapsed*1000),**ack});preview.update({**params,'mask':final});advanced=True
    if ack.get('seq',0)>=2 and not ended:
     atomic_json(work/'live-final.json',{'elapsed_ms':round(elapsed*1000),**ack})
     ended=True
     if mode=='cancel':preview.cancel()
     else:preview.update({**params,'mask':final},commit=True)
    if elapsed>55 and not ended:preview.cancel()
    preview.publish()
    view=preview.progress()
    if view and (not progress or view!=progress[-1]['value']):progress.append({'at_ms':round(elapsed*1000),'value':view})
    stop.wait(.04)
  thread=threading.Thread(target=publisher);thread.start()
  with (nullcontext() if normal else ResourceLease(ps['pid'],work/'resources.json',seconds=65)):
   result=await bridge.execute_shape(params,frozen_target=target,preview=preview)
  stop.set();thread.join();await bridge.tasks.flush();assert not bridge.transport.pending.value and not bridge.transport.pending.error and not bridge.busy
  if paused.is_set():atomic_json(work/'safe-pause.json',{'original_terminal':True});raise RuntimeError('Foreground changed; test paused')
  assert (work/'live-first.json').exists() and (work/'live-final.json').exists(),'No verified preview before confirmation'
  atomic_json(work/'progress.json',progress)
  stages={v['value']['stage'] for v in progress}
  assert 'redraw' in stages,stages
  if n>=8:assert 'verify' in stages,stages
  if mode=='cancel':assert 'restore-redraw' in stages or 'restore-verify' in stages,stages
  after=json.loads(app.DoJavaScript(READ));atomic_json(work/'after.json',after)
  for k in ('document','active','selected','tree'):assert before[k]==after[k],k
  for a,b in zip(before['members'],after['members']):
   for k in ('id','content','path'):assert a[k]==b[k],k
   for k in ('feather','density'):
    wanted=a[k] if mode=='cancel' or k not in final else final[k];assert abs(b[k]-wanted)<(.01 if k=='feather' else 100/255+.001),(k,b[k],wanted)
  if mode=='cancel':assert after['cursor']==before['cursor']
  else:
   assert after['cursor']==before['cursor']+1,(before['cursor'],after['cursor'])
   app.DoJavaScript("executeAction(charIDToTypeID('undo'),undefined,DialogModes.NO);")
   restored=json.loads(app.DoJavaScript(READ));atomic_json(work/'restored.json',restored);assert restored==before,{k:(before.get(k),restored.get(k)) for k in before if before.get(k)!=restored.get(k)}
  atomic_json(work/'verified.json',{'layers':n,'mode':mode,'low_cpu':not normal,'target_content_path_order_preserved':True,'unmodified_property_preserved':True,'one_undo_or_cancel_restored':True,'result':json.loads(result['result']),'physical_mouse':False,'live_readback_redraw_before_confirmation':True})
  print(json.dumps({'folder':str(work),'layers':n,'mode':mode,'verified':True,'updates':json.loads(result['result'])['preview']['updates']}),flush=True)
 finally:
  stop.set()
  if thread:thread.join()
  if preview:preview.close()
  unknown=bool(bridge.transport.pending.value or bridge.transport.pending.error);await bridge.close()
  if not unknown and not paused.is_set() and win32gui.GetForegroundWindow()==foreground:
   owned.Close(2)
   if previous:app.ActiveDocument=previous
  atomic_json(work/'finished.json',{'unknown':unknown,'paused':paused.is_set()})
with (r/'.runtime/ps169-test.lock').open('a+b') as lease:
 lease.seek(0);lease.write(b'0');lease.flush();lease.seek(0);msvcrt.locking(lease.fileno(),msvcrt.LK_NBLCK,1)
 try:asyncio.run(main())
 finally:lease.seek(0);msvcrt.locking(lease.fileno(),msvcrt.LK_UNLCK,1)
