"""Installed UXP shape writes on one owned scratch, with independent COM readback.
No synthesized keys/mouse. Physical CapsLock acceptance remains separate.
"""
import asyncio,copy,json,sys,time
from pathlib import Path
from urllib.request import urlopen
import win32com.client
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools'))
from backend.uxp_bridge import UxpBridge
from backend.version import APP_VERSION
from benchmark_read_helpers import fixture

READ=r'''(function(){
function name(id){var n=typeIDToStringID(id);return n || typeIDToCharID(id);}
function value(d,k){var t=d.getType(k);if(t===DescValueType.OBJECTTYPE){var o=desc(d.getObjectValue(k));o._obj=name(d.getObjectType(k));return o;}if(t===DescValueType.LISTTYPE){var l=d.getList(k),a=[];for(var i=0;i<l.count;i++)a.push(value(l,i));return a;}if(t===DescValueType.ENUMERATEDTYPE)return {_enum:name(d.getEnumerationType(k)),_value:name(d.getEnumerationValue(k))};if(t===DescValueType.UNITDOUBLE)return {_unit:name(d.getUnitDoubleType(k)),_value:d.getUnitDoubleValue(k)};if(t===DescValueType.DOUBLETYPE)return d.getDouble(k);if(t===DescValueType.INTEGERTYPE)return d.getInteger(k);if(t===DescValueType.BOOLEANTYPE)return d.getBoolean(k);if(t===DescValueType.STRINGTYPE)return d.getString(k);return null;}
function desc(d){var o={};for(var i=0;i<d.count;i++){var k=d.getKey(i);o[name(k)]=value(d,k);}return o;}
function quote(v){return '"'+String(v).replace(/\\/g,'\\\\').replace(/"/g,'\\"').replace(/\r/g,'\\r').replace(/\n/g,'\\n')+'"';}
function json(v){if(v===null)return 'null';if(v instanceof Array){var a=[];for(var i=0;i<v.length;i++)a.push(json(v[i]));return '['+a.join(',')+']';}if(typeof v==='object'){var a=[];for(var k in v)a.push(quote(k)+':'+json(v[k]));return '{'+a.join(',')+'}';}return typeof v==='string'?quote(v):String(v);}
var s=stringIDToTypeID,r=new ActionReference();r.putEnumerated(s('layer'),s('ordinal'),s('targetEnum'));var d=executeActionGet(r),out={};
var keys=['layerID','layerKind','hasVectorMask','adjustment','AGMStrokeStyleInfo','vectorMaskFeather','vectorMaskDensity','hasUserMask','userMaskFeather','userMaskDensity'];for(var i=0;i<keys.length;i++)if(d.hasKey(s(keys[i])))out[keys[i]]=value(d,s(keys[i]));
out.path=null;if(out.hasVectorMask){var p=new ActionReference();p.putEnumerated(s('path'),s('path'),s('vectorMask'));var raw=executeActionGet(p).toStream(),hex='';for(var i=0;i<raw.length;i++){var c=raw.charCodeAt(i).toString(16);hex+=('0000'+c).slice(-4);}out.path=hex;}
out.order=[];for(var i=0;i<app.activeDocument.layers.length;i++)out.order.push(app.activeDocument.layers[i].id);out.history=app.activeDocument.historyStates.length;out.historyCursor=-1;for(var i=0;i<out.history;i++)if(app.activeDocument.historyStates[i]==app.activeDocument.activeHistoryState){out.historyCursor=i;break;}return json(out);
})();'''

def make_content(raw):
 # Native creation of a fresh owned fill fixture; not a production COM fallback.
 value=json.dumps(raw)
 return r'''(function(){var s=stringIDToTypeID;
 function put(d,k,v){var id=s(k);if(v instanceof Array){var l=new ActionList();for(var i=0;i<v.length;i++)l.putObject(s(v[i]._obj),desc(v[i]));d.putList(id,l);}else if(typeof v==='object'){if(v._enum)d.putEnumerated(id,s(v._enum),s(v._value));else if(v._unit)d.putUnitDouble(id,s(v._unit),v._value);else d.putObject(id,s(v._obj),desc(v));}else if(typeof v==='boolean')d.putBoolean(id,v);else if(typeof v==='string')d.putString(id,v);else if(k==='location'||k==='midpoint'||k==='interfaceIconFrameDimmed')d.putInteger(id,v);else d.putDouble(id,v);}
 function desc(o){var d=new ActionDescriptor();for(var k in o)if(k!=='_obj')put(d,k,o[k]);return d;}
 var raw='''+value+r''',d=new ActionDescriptor(),r=new ActionReference();r.putClass(s('contentLayer'));d.putReference(s('null'),r);var using=new ActionDescriptor();using.putObject(s('type'),s(raw._obj),desc(raw));d.putObject(s('using'),s('contentLayer'),using);executeAction(s('make'),d,DialogModes.NO);})();'''

async def main():
 s=json.load(urlopen('http://127.0.0.1:15151/api/status',timeout=5))
 plugin_version=json.loads((ROOT/'uxp/offline-probe/manifest.json').read_text('utf-8'))['version']
 assert s['version']==APP_VERSION and s['photoshop']['uxp_version']==plugin_version and not s['photoshop']['busy']
 assert not s['menu']['visible']
 app=win32com.client.GetActiveObject('Photoshop.Application');previous=app.ActiveDocument if app.Documents.Count else None
 folder=ROOT/'.runtime'/('shape-live-'+str(time.time_ns()));folder.mkdir()
 import shutil
 config=folder/'uxp-config.json';shutil.copy2(Path(s['data_dir'])/'uxp-config.json',config)
 bridge=UxpBridge(folder/'tasks.json',config);scratch=None;checks=[]
 def read():return json.loads(app.DoJavaScript(READ))
 async def inspect():
  response=await asyncio.to_thread(bridge.transport.call,'inspect',shape_inspect=True)
  assert response['phase']=='completed',response
  data=response['shape_editor'];assert data['available'],data
  return data
 async def execute(case,alter):
  data=await inspect();params={k:copy.deepcopy(data[k]) for k in ('revision','fill','stroke')+ (('mask',) if 'mask' in data else ())};alter(params,data)
  target=await asyncio.to_thread(bridge._capture_target);before=read();start=time.perf_counter()
  if case=='long-lived-solid-draft':
   print('Holding a local paint draft for 35 seconds before submission',flush=True)
   await asyncio.sleep(35)
   start=time.perf_counter()
  result=await bridge.execute_shape(params,frozen_target=target);elapsed=(time.perf_counter()-start)*1000;after=read()
  assert after['layerID']==before['layerID'] and after['order']==before['order'] and after['path']==before['path']
  assert after.get('hasVectorMask',False)==before.get('hasVectorMask',False) and after['layerKind']==before['layerKind']
  for key in ('hasUserMask','userMaskFeather','userMaskDensity'):assert after.get(key)==before.get(key),(case,key)
  if 'mask' in params:
   def number(value):return value['_value'] if isinstance(value,dict) else value
   assert abs(number(after['vectorMaskFeather'])-params['mask']['feather'])<=.01,(case,after)
   assert abs(number(after['vectorMaskDensity'])*100/255-params['mask']['density'])<=100/255+.001,(case,after)
   if params['fill']==data['fill'] and params['stroke']==data['stroke']:
    for key in ('adjustment','AGMStrokeStyleInfo'):assert after.get(key)==before.get(key),(case,'mask-only rewrote paint',key)
  assert after['historyCursor']==before['historyCursor']+1,(case,before['historyCursor'],after['historyCursor'])
  confirmed=await inspect();assert confirmed['fill']['kind']==params['fill']['kind'] and confirmed['stroke']['kind']==params['stroke']['kind']
  app.DoJavaScript('var d=app.activeDocument;d.activeHistoryState=d.historyStates[d.historyStates.length-2];')
  restored=read()
  for key in ('layerID','adjustment','AGMStrokeStyleInfo','path','order','vectorMaskDensity','vectorMaskFeather','userMaskDensity','userMaskFeather'):assert restored.get(key)==before.get(key),(case,key)
  checks.append({'case':case,'execute_ms':round(elapsed,2),'task_id':result['task_id'],'one_undo':True,'path_and_order_unchanged':True,'placement_moves':0})
  print(case,'passed',flush=True)
 try:
  app.DoJavaScript(fixture('shape',4));scratch=app.ActiveDocument
  data=await inspect();assert data.get('mask')=={'feather':0,'density':100},data
  # A separate pixel mask must retain its own independent properties.
  app.DoJavaScript("var s=stringIDToTypeID,d=new ActionDescriptor(),r=new ActionReference();d.putClass(s('new'),s('channel'));r.putEnumerated(s('channel'),s('channel'),s('mask'));d.putReference(s('at'),r);d.putEnumerated(s('using'),s('userMaskEnabled'),s('revealAll'));executeAction(s('make'),d,DialogModes.NO);")
  await execute('vector-feather-only',lambda p,d:p['mask'].update(feather=7.5))
  await execute('vector-density-only',lambda p,d:p['mask'].update(density=63))
  await execute('vector-mask-maximum',lambda p,d:p['mask'].update(feather=1000,density=0))
  def mask_color(p,d):p['mask'].update(feather=12.5,density=42);p['fill']['rgb']=[25,75,160]
  await execute('vector-mask-and-color-one-undo',mask_color)
  old=await inspect();params={k:copy.deepcopy(old[k]) for k in ('revision','fill','stroke','mask')}
  target=await asyncio.to_thread(bridge._capture_target)
  app.DoJavaScript("var s=stringIDToTypeID,d=new ActionDescriptor(),r=new ActionReference(),v=new ActionDescriptor();r.putEnumerated(s('layer'),s('ordinal'),s('targetEnum'));d.putReference(s('null'),r);v.putInteger(s('vectorMaskDensity'),128);d.putObject(s('to'),s('layer'),v);executeAction(s('set'),d,DialogModes.NO);")
  after_external=read()
  try:await bridge.execute_shape(params,frozen_target=target)
  except Exception as error:assert '已改变' in str(error),str(error)
  else:raise AssertionError('Stale mask revision was accepted')
  assert read()==after_external
  checks.append({'case':'stale-mask-revision','no_write':True})
  app.DoJavaScript('var d=app.activeDocument;d.activeHistoryState=d.historyStates[d.historyStates.length-2];')
  def solid(p,d):p['fill']['rgb']=[20,80,170];p['stroke'].update(enabled=True,width=3,rgb=[255,20,0])
  await execute('solid-fill-and-stroke',solid)
  await execute('long-lived-solid-draft',solid)
  gradient={'kind':'gradient','enabled':True,'stops':[{'rgb':[10,20,30],'location':0},{'rgb':[60,100,220],'location':1800},{'rgb':[240,230,200],'location':4096}]}
  await execute('gradient-fill',lambda p,d:p.update(fill=copy.deepcopy(gradient)))
  await execute('gradient-stroke',lambda p,d:p.update(stroke={**copy.deepcopy(gradient),'width':4}))
  data=await inspect();assert data['patterns'],'Expected loaded local PS patterns'
  await execute('pattern-fill',lambda p,d:p.update(fill={'kind':'pattern','enabled':True,'name':d['patterns'][0]}))
  await execute('pattern-stroke',lambda p,d:p.update(stroke={'kind':'pattern','enabled':True,'name':d['patterns'][0],'width':5}))
  def swap(p,d):
   fill=copy.deepcopy(p['fill']);stroke=copy.deepcopy(p['stroke']);width=stroke.pop('width')
   p['fill']=stroke;p['stroke']={**fill,'width':width}
  await execute('swap-fill-and-stroke',swap)
  data=await inspect();params={k:copy.deepcopy(data[k]) for k in ('revision','fill','stroke')};params['fill']['rgb']=[100,20,40]
  target=await asyncio.to_thread(bridge._capture_target);target['active_layer_id']+=1;before=read()
  try:await bridge.execute_shape(params,frozen_target=target)
  except (ValueError,RuntimeError):pass
  else:raise AssertionError('Stale active layer was accepted')
  assert read()==before;checks.append({'case':'stale-target','no_write':True})
  params['revision']='stale:revision';target=await asyncio.to_thread(bridge._capture_target)
  try:await bridge.execute_shape(params,frozen_target=target)
  except RuntimeError:pass
  else:raise AssertionError('Stale paint revision accepted')
  assert read()==before;checks.append({'case':'stale-paint-revision','no_write':True})
  # The same property reads must not expose a picker for locked/pixel/multi targets.
  app.DoJavaScript('app.activeDocument.activeLayer.allLocked=true;')
  response=await asyncio.to_thread(bridge.transport.call,'inspect',shape_inspect=True)
  assert not response['shape_editor']['available'];app.DoJavaScript('app.activeDocument.activeLayer.allLocked=false;')
  app.DoJavaScript('app.activeDocument.artLayers.add();')
  response=await asyncio.to_thread(bridge.transport.call,'inspect',shape_inspect=True)
  assert not response['shape_editor']['available'];checks.append({'case':'locked-and-pixel','editor_disabled':True})
  # A plain solid fill shares layerKind=4 with shapes but has no vector mask.
  app.DoJavaScript("var s=stringIDToTypeID,d=new ActionDescriptor(),r=new ActionReference();r.putClass(s('contentLayer'));d.putReference(s('null'),r);var t=new ActionDescriptor(),f=new ActionDescriptor(),c=new ActionDescriptor();c.putDouble(s('red'),30);c.putDouble(s('grain'),60);c.putDouble(s('blue'),90);f.putObject(s('color'),s('RGBColor'),c);t.putObject(s('type'),s('solidColorLayer'),f);d.putObject(s('using'),s('contentLayer'),t);executeAction(s('make'),d,DialogModes.NO);")
  response=await asyncio.to_thread(bridge.transport.call,'inspect',shape_inspect=True)
  assert response['shape_editor']['available'] and response['shape_editor']['vector'] is False
  await execute('plain-solid-fill',lambda p,d:p['fill'].update(rgb=[120,150,180]))
  raw_gradient={'_obj':'gradientLayer','type':{'_enum':'gradientType','_value':'linear'},'angle':{'_unit':'angleUnit','_value':0},'scale':{'_unit':'percentUnit','_value':100},
    'gradient':{'_obj':'gradientClassEvent','name':'Menu owned fill','gradientForm':{'_enum':'gradientForm','_value':'customStops'},'interfaceIconFrameDimmed':4096,
      'colors':[{'_obj':'colorStop','color':{'_obj':'RGBColor','red':c,'grain':c,'blue':c},'type':{'_enum':'colorStopType','_value':'userStop'},'location':loc,'midpoint':50} for c,loc in ((0,0),(255,4096))],
      'transparency':[{'_obj':'transferSpec','opacity':{'_unit':'percentUnit','_value':100},'location':loc,'midpoint':50} for loc in (0,4096)]}}
  app.DoJavaScript(make_content(raw_gradient))
  await execute('plain-gradient-fill',lambda p,d:p['fill']['stops'][0].update(rgb=[40,70,100]))
  data=await inspect();app.DoJavaScript(make_content({'_obj':'patternLayer','pattern':{'_obj':'pattern','name':data['patterns'][0]}}))
  await execute('plain-pattern-fill',lambda p,d:p['fill'].update(name=d['patterns'][-1]))
  data=await inspect();params={k:copy.deepcopy(data[k]) for k in ('revision','fill','stroke')};params['stroke']['enabled']=True
  before=read();target=await asyncio.to_thread(bridge._capture_target)
  try:await bridge.execute_shape(params,frozen_target=target)
  except RuntimeError:pass
  else:raise AssertionError('Plain fill accepted a shape-only stroke')
  assert read()==before;checks.append({'case':'plain-fill-rejects-stroke','no_write':True})
  report={'version':APP_VERSION,'uxp':plugin_version,'checks':checks,'physical_capslock_acceptance':False}
  (ROOT/f'.runtime/shape-live-{APP_VERSION}.json').write_text(json.dumps(report,indent=2),'utf-8')
  print(json.dumps(report),flush=True)
 finally:
  unresolved=bool(bridge.transport.pending.value or bridge.transport.pending.error)
  await bridge.close()
  if unresolved:
   print('Original request remains pending; scratch retained and no further PS control sent',flush=True)
  else:
   if scratch:app.ActiveDocument=scratch;scratch.Close(2)
   if previous is not None:app.ActiveDocument=previous
asyncio.run(main())
