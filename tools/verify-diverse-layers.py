"""Installed production UXP matrix; only owned disposable Photoshop documents.

COM supplies independent fixtures/readback, never an executor fallback. Measures
full bridge transactions, checks payload preservation and one undo. This does
not synthesize physical Caps/mouse input or claim cross-machine acceptance.
"""
import argparse, asyncio, hashlib, importlib.util, json, sys, time
from pathlib import Path
from urllib.request import urlopen
import win32com.client

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.uxp_bridge import UxpBridge
from backend.version import APP_VERSION
from benchmark_read_helpers import ACTIONS, TREE, SEMANTIC, special, summary, native

KINDS=['pixel','empty','pixel-effects','text','text-effects','smart','smart-effects',
       'smart-mask','masked','shape','shape-effects','solid','gradient','curves',
       'levels','hue','balance','blackwhite','clipped','hidden','blend','nested','pattern','smart-filter']
OPERATIONS=['label.red','label.none','moveToTop','moveToBottom','convertSmartObject']+list(dict.fromkeys(ACTIONS))

def native_edge(action):
    return 'var s=stringIDToTypeID,r=new ActionReference(),z=new ActionDescriptor();r.putEnumerated(s("layer"),s("ordinal"),s("targetEnum"));z.putReference(s("null"),r);r=new ActionReference();r.putEnumerated(s("layer"),s("ordinal"),s("'+('front' if action=='moveToTop' else 'back')+'"));z.putReference(s("to"),r);executeAction(s("move"),z,DialogModes.NO);'

def set_effects():
    # Fixed native Action Manager descriptor: drop shadow plus outer stroke.
    return r'''var s=stringIDToTypeID,r=new ActionReference();r.putProperty(s('property'),s('layerEffects'));r.putEnumerated(s('layer'),s('ordinal'),s('targetEnum'));var z=new ActionDescriptor();z.putReference(s('null'),r);var fx=new ActionDescriptor();fx.putUnitDouble(s('scale'),s('percentUnit'),100);var shadow=new ActionDescriptor();shadow.putBoolean(s('enabled'),true);shadow.putBoolean(s('present'),true);shadow.putBoolean(s('showInDialog'),true);shadow.putEnumerated(s('mode'),s('blendMode'),s('multiply'));var black=new ActionDescriptor();black.putDouble(s('red'),0);black.putDouble(s('green'),0);black.putDouble(s('blue'),0);shadow.putObject(s('color'),s('RGBColor'),black);shadow.putUnitDouble(s('opacity'),s('percentUnit'),65);shadow.putBoolean(s('useGlobalAngle'),false);shadow.putUnitDouble(s('localLightingAngle'),s('angleUnit'),120);shadow.putUnitDouble(s('distance'),s('pixelsUnit'),4);shadow.putUnitDouble(s('chokeMatte'),s('pixelsUnit'),0);shadow.putUnitDouble(s('blur'),s('pixelsUnit'),5);fx.putObject(s('dropShadow'),s('dropShadow'),shadow);var stroke=new ActionDescriptor();stroke.putBoolean(s('enabled'),true);stroke.putBoolean(s('present'),true);stroke.putBoolean(s('showInDialog'),true);stroke.putEnumerated(s('style'),s('frameStyle'),s('outsetFrame'));stroke.putEnumerated(s('paintType'),s('frameFill'),s('solidColor'));stroke.putEnumerated(s('mode'),s('blendMode'),s('normal'));stroke.putUnitDouble(s('opacity'),s('percentUnit'),100);stroke.putUnitDouble(s('size'),s('pixelsUnit'),2);stroke.putObject(s('color'),s('RGBColor'),black);fx.putObject(s('frameFX'),s('frameFX'),stroke);z.putObject(s('to'),s('layerEffects'),fx);executeAction(s('set'),z,DialogModes.NO);'''

def setup(kind,count=4,size=181,max_setup_seconds=300):
    base='smart' if kind=='smart-filter' else kind.replace('-effects','').replace('-mask','')
    if base in ('pixel','empty','clipped','hidden','blend','nested'):
        make='var a=d.artLayers.add();'+('d.selection.selectAll();d.selection.fill(app.foregroundColor);d.selection.deselect();' if base!='empty' else '')
    elif base in ('hue','balance','blackwhite'):
        from benchmark_read_helpers import native
        make=native({'hue':'adjustment.hueSaturation','balance':'adjustment.colorBalance','blackwhite':'adjustment.blackWhite'}[base])
    elif base=='pattern':
        make=r'''var s=stringIDToTypeID,r=new ActionReference();r.putProperty(s('property'),s('presetManager'));r.putEnumerated(s('application'),s('ordinal'),s('targetEnum'));var presets=executeActionGet(r).getList(s('presetManager')),name=null;for(var pi=0;pi<presets.count;pi++){var pt=typeIDToStringID(presets.getObjectType(pi))||typeIDToCharID(presets.getObjectType(pi));if(/pattern|PttR/i.test(pt)){var names=presets.getObjectValue(pi).getList(s('name'));if(names.count){name=names.getString(0);break;}}}if(!name)throw Error('No installed pattern fixture');var ref=new ActionReference();ref.putClass(s('contentLayer'));var z=new ActionDescriptor();z.putReference(s('null'),ref);var pattern=new ActionDescriptor();pattern.putString(s('name'),name);var t=new ActionDescriptor();t.putObject(s('pattern'),s('pattern'),pattern);var u=new ActionDescriptor();u.putObject(s('type'),s('patternLayer'),t);z.putObject(s('using'),s('contentLayer'),u);executeAction(s('make'),z,DialogModes.NO);'''
    else:make=special(base)
    if base=='pattern':make='(function(){'+make+'})();'
    body='var diverseFixtureDeadline=(new Date()).getTime()+'+str(max_setup_seconds*1000)+';var lower=d.artLayers.add();lower.name="Lower";'+make+'var anchor=d.activeLayer;anchor.name="Anchor";'
    if kind.endswith('-effects'):body+=set_effects()
    if kind=='smart-mask':body+='var s=stringIDToTypeID,'+special('masked').split('var s=stringIDToTypeID,',1)[1]
    if kind=='smart-filter':body+="var z=new ActionDescriptor();z.putUnitDouble(stringIDToTypeID('radius'),stringIDToTypeID('pixelsUnit'),2);executeAction(stringIDToTypeID('gaussianBlur'),z,DialogModes.NO);"
    if kind=='clipped':body+='anchor.grouped=true;'
    if kind=='hidden':body+='anchor.visible=false;'
    if kind=='blend':body+='anchor.opacity=37;anchor.blendMode=BlendMode.MULTIPLY;'
    body+='var upper=d.artLayers.add();upper.name="Upper";'
    if kind=='nested':body+='var g=d.layerSets.add();g.name="Outer";var h=g.layerSets.add();h.name="Inner";h.artLayers.add().name="Inside lower";anchor.move(h,ElementPlacement.INSIDE);h.artLayers.add().name="Inside upper";'
    # Unique names belong only to disposable fixture copies. Avoid building a
    # long chain of colliding native "Upper copy N" names during test setup.
    body+='for(var i=d.layers.length;i<'+str(count)+';i++){if((new Date()).getTime()>diverseFixtureDeadline)throw Error("Owned diverse fixture setup budget exceeded");var diverseCopy=upper.duplicate();diverseCopy.name="Diverse fixture "+i;}d.activeLayer=anchor;'
    return 'app.documents.add(UnitValue('+str(size)+',"px"),UnitValue('+str(size)+',"px"),72,"Diverse owned '+kind+'",NewDocumentMode.RGB,DocumentFill.TRANSPARENT);var d=app.activeDocument;d.suspendHistory("Diverse fixture",'+json.dumps(body)+');'

# Also preserve visibility, blend and clipping; labels deliberately excluded.
PAYLOAD=SEMANTIC.replace("'vectorMaskDensity']","'vectorMaskDensity','visible','opacity','mode','group','AGMStrokeStyleInfo','smartObjectMore','filterFX','filterFXList']")
PAYLOAD=PAYLOAD.replace("else if(t==DescValueType.DOUBLETYPE)a.putDouble(k,d.getDouble(k));", "else if(t==DescValueType.DOUBLETYPE)a.putDouble(k,d.getDouble(k));else if(t==DescValueType.ENUMERATEDTYPE)a.putEnumerated(k,d.getEnumerationType(k),d.getEnumerationValue(k));")
# PS native label edits regenerate only smartObjectMore.placed (UUID). Preserve
# and compare every other extension field, including transforms and dimensions.
# A native-control experiment is required before accepting this normalization.
PAYLOAD=PAYLOAD.replace("a.putObject(k,d.getObjectType(k),d.getObjectValue(k));", "{var object=d.getObjectValue(k);if(keys[i]==='smartObjectMore'&&object.hasKey(s('placed')))object.erase(s('placed'));a.putObject(k,d.getObjectType(k),object);}")

async def run(args):
    status=lambda:json.load(urlopen('http://127.0.0.1:15151/api/status',timeout=5))
    s=status();assert s['version']==APP_VERSION and not s['photoshop']['busy'] and not s['menu']['visible']
    assert not s['photoshop'].get('uxp_recovery',{}).get('active')
    assert not (Path(s['data_dir'])/'uxp-pending.json').exists()
    work=ROOT/'.runtime/diverse-layers';work.mkdir(exist_ok=True)
    bridge=UxpBridge(work/'tasks.json',Path(s['data_dir'])/'uxp-config.json')
    app=win32com.client.GetActiveObject('Photoshop.Application');previous=app.ActiveDocument if app.Documents.Count else None
    scratch=None;report={'version':s['version'],'uxp':s['photoshop']['uxp_version'],'photoshop':str(app.Version),'width_px':args.size,'height_px':args.size,'cases':[],'complete':False,'physical_input':False}
    js=lambda code:app.DoJavaScript(code)
    def save():args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    def selection_code():return 'app.activeDocument.activeLayer='+('app.activeDocument.layerSets[0].layerSets[0].artLayers.getByName("Anchor")' if kind=='nested' else 'app.activeDocument.artLayers.getByName("Anchor")')+';'
    def readall(prefix=''):
        # One COM call per verification boundary, still independent PS reads.
        # No verification calls are included in transaction timing.
        raw=str(js(prefix+'(function(){var tree='+TREE.rstrip(';')+';var payload='+PAYLOAD.rstrip(';')+';var d=app.activeDocument,cursor=-1;for(var i=0;i<d.historyStates.length;i++)if(d.historyStates[i]==d.activeHistoryState){cursor=i;break;}if(cursor<0)throw Error("No history cursor");return tree+"\\n::DIVERSE::\\n"+payload+"\\n::DIVERSE::\\n"+cursor;})()'))
        tree,payload,cursor=raw.split('\n::DIVERSE::\n');return tree,payload,int(cursor)
    async def ready():
        deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            try:
                beat=json.loads((bridge.transport.folder/'probe-last.json').read_text('utf-8-sig'))
                # A large COM fixture can outlive the lease; wait for recovery
                # then. Short readbacks need no artificial next-5s-heartbeat
                # barrier. This is test setup only, outside measured commands.
                if 0<=time.time()*1000-beat['plugin_time_ms']<4000:return
            except (OSError,ValueError,RuntimeError):pass
            await asyncio.sleep(.03)
        raise RuntimeError('No post-COM heartbeat; no action submitted')
    async def execute(action,target):
        assert target['document_id']==fixture_id,'Owned fixture is no longer active; no operation submitted'
        start=time.perf_counter();result=await bridge.execute(action,frozen_target=target)
        assert not bridge.busy and not bridge.transport.pending.value
        return json.loads(result['result']),round((time.perf_counter()-start)*1000,3)
    try:
        for kind in args.kinds.split(','):
            assert kind in KINDS
            try:js(setup(kind,args.count,args.size,args.max_setup_seconds))
            except Exception:
                if app.Documents.Count and str(app.ActiveDocument.Name)=='Diverse owned '+kind:scratch=app.ActiveDocument
                raise
            scratch=app.ActiveDocument
            assert str(scratch.Name)=='Diverse owned '+kind
            fixture_id=int(js('app.activeDocument.id;'))
            before,payload,index=readall();anchor=int(js('app.activeDocument.activeLayer.id;'))
            assert ('layerEffects:' in payload)==kind.endswith('-effects'),('Effects fixture invalid',kind)
            if kind.startswith('smart'):assert 'smartObject:' in payload,('Smart fixture invalid',kind)
            case={'kind':kind,'count':len(before.splitlines()),'payload_sha256':hashlib.sha256(payload.encode()).hexdigest(),'operations':[]};report['cases'].append(case);save()
            fields=dict(line.split(':',1) for line in payload.splitlines())
            case['fixture_features']={'effects':'layerEffects' in fields,'vector_path':'vectorPath' in fields,
                'smart_object':'smartObject' in fields,'filter_descriptor':any(b'filterFX' in bytes.fromhex(value) for value in fields.values())}
            if kind=='smart-filter':assert case['fixture_features']['filter_descriptor'],'Smart filter fixture descriptor missing'
            def reset():
                actual_tree,actual_payload,actual_index=readall('app.activeDocument.activeHistoryState=app.activeDocument.historyStates['+str(index)+'];'+selection_code())
                assert actual_tree==before and actual_payload==payload and actual_index==index,('Undo mismatch',kind)
            await ready();frozen=await asyncio.to_thread(bridge._capture_target)
            epoch=time.time()*1000;deadline=time.monotonic()+5;observed={}
            while time.monotonic()<deadline:
                observed=status()['photoshop'].get('layer_context',{})
                if observed.get('document_id')==frozen['document_id'] and observed.get('layer_ids')==[anchor] and observed.get('plugin_time_ms',0)>=epoch:break
                await asyncio.sleep(.02)
            else:raise AssertionError(('Fresh type cache missing',kind,observed))
            expected='smart' if kind.startswith('smart') else 'text' if kind.startswith('text') else 'shape-fill' if kind in ('shape','shape-effects','solid','gradient','pattern') else 'adjustment' if kind in ('curves','levels','hue','balance','blackwhite') else 'pixel'
            assert observed['kind']==expected and observed['quick_mask']==127 and observed['mask']&2,('Unexpected capabilities',kind,observed)
            case['fresh_context']={k:observed[k] for k in ('kind','types','mask','quick_mask','same_parent','locked')};save()
            native_payloads={}
            if kind=='clipped':
                # Moving a clipping member away from its base, or grouping it,
                # releases clipping in PS native commands too. Compare the
                # whole payload with those exact native outcomes, not a
                # blanket exclusion of the clipping property.
                for action in ('moveToTop','moveToBottom','layer.group'):
                    _,native_payloads[action],_=readall(native(action) if action=='layer.group' else native_edge(action));reset()
                case['native_clipping_reference']=list(native_payloads)
            for action in args.actions.split(','):
                assert action in OPERATIONS
                await ready();frozen=await asyncio.to_thread(bridge._capture_target)
                result,ms=await execute(action,frozen)
                now,actual_payload,after_index=readall()
                assert after_index==index+(0 if result.get('unchanged') else 1),('Expected one history state or verified native no-op',kind,action,index,after_index)
                if action!='convertSmartObject':
                    expected_payload=native_payloads.get(action,payload)
                    if actual_payload!=expected_payload:
                        (work/'payload-before.txt').write_text(expected_payload,'utf-8');(work/'payload-after.txt').write_text(actual_payload,'utf-8')
                        raise AssertionError(('Payload changed',kind,action))
                if action in ('label.red','label.none'):
                    color=js('(function(){var s=stringIDToTypeID,r=new ActionReference();r.putIdentifier(s("layer"),'+str(anchor)+');return typeIDToStringID(executeActionGet(r).getEnumerationValue(s("color")));})()')
                    assert color==action.split('.')[1] and now==before
                elif action.startswith('layer.') or action.startswith('adjustment.'):
                    assert result['verified'] and result['placement_moves']==0
                    assert len(now.splitlines())==len(before.splitlines())+1
                elif action=='convertSmartObject':
                    assert result['verified']
                    actual_kind=int(js('(function(){var s=stringIDToTypeID,r=new ActionReference();r.putEnumerated(s("layer"),s("ordinal"),s("targetEnum"));return executeActionGet(r).getInteger(s("layerKind"));})()'))
                    assert actual_kind==5,('Independent smart kind mismatch',kind)
                    if result.get('unchanged'):assert now==before
                    else:
                        made=str(result['smart_object_id']);old_rows=before.splitlines();new_rows=now.splitlines()
                        old_anchor=next(v for v in old_rows if v.split('\t')[1]==str(anchor))
                        new_anchor=next(v for v in new_rows if v.split('\t')[1]==made)
                        assert len(new_rows)==len(old_rows) and old_anchor.split('\t')[0]==new_anchor.split('\t')[0]
                        assert [v for v in old_rows if v!=old_anchor]==[v for v in new_rows if v!=new_anchor]
                # Reset using the exact pre-operation cursor: one native undo.
                reset();case['operations'].append({'action':action,'ms':ms,'one_undo':not result.get('unchanged',False),'verified_noop':result.get('unchanged',False),'payload_preserved':True,'payload_checked':'after-undo' if action=='convertSmartObject' else 'during-and-after-undo','timings_ms':result.get('timings_ms',{}),
                    'tree_reader':result.get('tree_reader'),'tree_count':result.get('tree_count')});save()
            # Frozen target must refuse a different selection without history.
            await ready();target=await asyncio.to_thread(bridge._capture_target)
            stale,_,ci=readall('app.activeDocument.activeLayer=app.activeDocument.artLayers.getByName("Upper");')
            try:await bridge.execute('label.blue',frozen_target=target)
            except RuntimeError:pass
            else:raise AssertionError('Stale target accepted')
            stale_after,_,ci_after=readall();assert ci_after==ci and stale_after==stale
            case['stale_refused']=True;case['complete']=True;save()
            print(json.dumps({'kind':kind,'passed':len(case['operations']),'stale_refused':True}),flush=True)
            scratch.Close(2);scratch=None
        report['complete']=True
        report['timings']={action:summary([v['ms'] for c in report['cases'] for v in c['operations'] if v['action']==action]) for action in {v['action'] for c in report['cases'] for v in c['operations']}}
        save()
    except Exception as error:
        report['error']=str(error);save();raise
    finally:
        unresolved=bool(bridge.transport.pending.value or bridge.transport.pending.error)
        await bridge.close()
        if unresolved:print('Unresolved original request: retained scratch, no more PS controls',flush=True)
        else:
            if scratch:app.ActiveDocument=scratch;scratch.Close(2)
            if previous:app.ActiveDocument=previous

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--kinds',default=','.join(KINDS));p.add_argument('--actions',default=','.join(OPERATIONS));p.add_argument('--count',type=int,default=4);p.add_argument('--size',type=int,default=181);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--max-setup-seconds',type=int,default=300,choices=range(10,301),metavar='10..300',help='Cooperative scratch construction budget, outside command timing; never interrupts an already running native step');args=p.parse_args()
    if not 4<=args.count<=1000:p.error('Use 4–1000 layers')
    if not 16<=args.size<=8192:p.error('Use 16–8192 pixels')
    asyncio.run(run(args))
