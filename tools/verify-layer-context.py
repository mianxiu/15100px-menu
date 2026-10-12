"""Real installed UXP/cache tests on a disposable PS document, no UI injection.

Independent COM setup/readback; source production bridge exercises the installed
executor. Physical hotkeys, hover and focus acceptance remain separate.
"""
import asyncio,json,sys,time
from pathlib import Path
from urllib.request import urlopen
import win32com.client
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.uxp_bridge import UxpBridge
from backend.version import APP_VERSION
from backend.layer_context import require_menu_target

BASE='http://127.0.0.1:15151'
def status():return json.load(urlopen(BASE+'/api/status',timeout=5))

async def main():
    s=status();assert s['version']==APP_VERSION and not s['photoshop']['busy'] and not s['menu']['visible']
    assert s['photoshop']['uxp_ready'] and s['photoshop']['uxp_version']==s['uxp']['bundled_version']
    app=win32com.client.GetActiveObject('Photoshop.Application')
    previous=app.ActiveDocument if app.Documents.Count else None
    name='Menu layer types '+str(time.time_ns());scratch=None;checks=[];latencies=[]
    bridge=UxpBridge(task_history=ROOT/'.runtime/type-live-tasks.json',config=Path(s['data_dir'])/'uxp-config.json')
    def js(code):return app.DoJavaScript(code)
    active_id="var s=stringIDToTypeID,r=new ActionReference();r.putEnumerated(s('layer'),s('ordinal'),s('targetEnum'));executeActionGet(r).getInteger(s('layerID'));"
    read="(function(){var s=stringIDToTypeID,r=new ActionReference();r.putEnumerated(s('layer'),s('ordinal'),s('targetEnum'));var d=executeActionGet(r);return d.getInteger(s('layerID'))+'|'+(d.hasKey(s('color'))?typeIDToStringID(d.getEnumerationValue(s('color'))):'absent')+'|'+app.activeDocument.historyStates.length;})();"
    async def context(kind,ids=None,predicate=lambda value:True):
        start=time.perf_counter();deadline=start+3
        if ids is None:ids=[int(js(active_id))]
        while time.perf_counter()<deadline:
            value=status()['photoshop'].get('layer_context',{})
            if value.get('kind')==kind and value.get('layer_ids')==sorted(ids) and predicate(value):
                latencies.append((time.perf_counter()-start)*1000)
                checks.append({'kind':kind,'context':value});return value
            await asyncio.sleep(.02)
        raise AssertionError({'expected':kind,'ids':ids,'last':value})
    async def success(action,color=None):
        result=await bridge.execute(action)
        if color:assert js(read).split('|')[1]==color
        checks.append({'action':action,'result':result,'independent_readback':True})
    async def reject(action):
        before=js(read)
        try:await bridge.execute(action)
        except RuntimeError as e:
            assert js(read)==before,'Rejected action changed layer/history'
            checks.append({'rejected':action,'error':str(e),'no_write_or_history':True})
        else:raise AssertionError('Expected rejection: '+action)
    def select(ids):
        commands=[]
        for index,id in enumerate(ids):
            commands.append("var r=new ActionReference(),d=new ActionDescriptor();r.putIdentifier(s('layer'),%d);d.putReference(s('null'),r);%sd.putBoolean(s('makeVisible'),false);executeAction(s('select'),d,DialogModes.NO);"%(id,"d.putEnumerated(s('selectionModifier'),s('selectionModifierType'),s('addToSelection'));" if index else ''))
        js("var s=stringIDToTypeID;"+''.join(commands))
    try:
        js('app.documents.add(32,32,72,'+json.dumps(name)+',NewDocumentMode.RGB,DocumentFill.WHITE);')
        scratch=app.ActiveDocument
        bg=await context('background');assert bg['mask']==0
        await reject('label.red');await reject('moveToTop')
        js("app.activeDocument.artLayers.add();app.activeDocument.activeLayer.name='Pixel';")
        pixel=await context('pixel');assert pixel['mask']==3
        await success('label.red','red');await success('label.none','none')
        js("var l=app.activeDocument.artLayers.add();l.kind=LayerKind.TEXT;l.name='Text';l.textItem.contents='type';")
        text=await context('text');assert text['mask']==11
        await success('label.blue','blue');await success('moveToBottom')
        assert js('app.activeDocument.layers[1].name')=='Text'
        await context('text',predicate=lambda v:v['mask']==7);await success('moveToTop')
        assert js('app.activeDocument.layers[0].name')=='Text'
        await context('text',predicate=lambda v:v['mask']==11)
        js("app.activeDocument.artLayers.add();app.activeDocument.activeLayer.name='Smart';executeAction(stringIDToTypeID('newPlacedLayer'),undefined,DialogModes.NO);")
        smart=await context('smart');assert smart['mask']&2
        await success('label.orange','orange')
        js("var s=stringIDToTypeID,d=new ActionDescriptor(),r=new ActionReference(),f=new ActionDescriptor(),c=new ActionDescriptor();r.putClass(s('contentLayer'));d.putReference(s('null'),r);c.putDouble(s('red'),50);c.putDouble(s('green'),80);c.putDouble(s('blue'),100);f.putObject(s('color'),s('RGBColor'),c);var u=new ActionDescriptor();u.putObject(s('type'),s('solidColorLayer'),f);d.putObject(s('using'),s('contentLayer'),u);executeAction(s('make'),d,DialogModes.NO);")
        fill=await context('shape-fill');await success('label.gray','gray')
        js("var s=stringIDToTypeID,d=new ActionDescriptor(),r=new ActionReference(),u=new ActionDescriptor(),t=new ActionDescriptor();r.putClass(s('adjustmentLayer'));d.putReference(s('null'),r);t.putBoolean(s('useLegacy'),false);u.putObject(s('type'),s('brightnessEvent'),t);d.putObject(s('using'),s('adjustmentLayer'),u);executeAction(s('make'),d,DialogModes.NO);")
        adjustment=await context('adjustment');await success('label.violet','violet')
        js("var g=app.activeDocument.layerSets.add();g.name='Empty';app.activeDocument.activeLayer=g;")
        empty=await context('group');assert not empty['mask']&1
        await reject('select');await success('label.yellowColor','yellowColor')
        js("var g=app.activeDocument.activeLayer;g.artLayers.add().name='Child A';g.artLayers.add().name='Child B';app.activeDocument.activeLayer=g;")
        group=await context('group',predicate=lambda v:bool(v['mask']&1));assert group['mask']&1
        await success('select');multi=await context('pixel',[int(js("app.activeDocument.layerSets[0].layers[0].id")),int(js("app.activeDocument.layerSets[0].layers[1].id"))])
        assert len(multi['layer_ids'])==2 and not multi['mask']&1
        await success('label.grain','grain')
        child=multi['layer_ids'][0];select([child]);js('app.activeDocument.activeLayer.positionLocked=true;')
        locked=await context('pixel',[child],lambda v:v.get('locked',False));assert locked['locked'] and locked['mask']==3
        await reject('moveToTop');js('app.activeDocument.activeLayer.positionLocked=false;')
        await context('pixel',[child],lambda v:not v.get('locked',False))
        js('app.activeDocument.layerSets[0].allLocked=true;')
        ancestor=await context('pixel',[child],lambda v:v.get('locked',False));assert ancestor['locked'] and not ancestor['mask']&12
        await reject('moveToBottom');js('app.activeDocument.layerSets[0].allLocked=false;')
        select([child,pixel['layer_ids'][0]])
        cross=await context('pixel',[child,pixel['layer_ids'][0]]);assert not cross['same_parent'] and cross['mask']==2
        await reject('moveToBottom');await success('label.red','red')
        select([pixel['layer_ids'][0],text['layer_ids'][0]])
        mixed=await context('mixed',[pixel['layer_ids'][0],text['layer_ids'][0]]);assert mixed['mask']&2 and not mixed['mask']&1
        await success('label.blue','blue')
        select([bg['layer_ids'][0],pixel['layer_ids'][0]])
        bgmixed=await context('mixed',[bg['layer_ids'][0],pixel['layer_ids'][0]]);assert bgmixed['mask']==0
        await reject('label.red')
        select(pixel['layer_ids']);frozen=await context('pixel',pixel['layer_ids']);select(text['layer_ids'])
        before=js(read)
        try:await bridge.execute('label.orange',lambda target:require_menu_target(frozen,'label.orange',target))
        except RuntimeError as e:assert '已改变' in str(e)
        else:raise AssertionError('Frozen menu target was not protected')
        assert js(read)==before
        checks.append({'frozen_menu_selection_changed':'cancelled_before_write'})
        report={'version':APP_VERSION,'uxp':s['photoshop']['uxp_version'],'checks':checks,'cache_observation_ms':latencies,
                'scope':'Actual installed backend type cache and UXP executor, source production bridge; COM scratch setup/readback. Physical Caps/hover/focus/cancel pending.'}
        (ROOT/('.runtime/layer-context-'+APP_VERSION+'-live.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
        print('PASS real PS cache/types, labels/order/selection, disabled atomic rejection, frozen target protection')
    finally:
        await bridge.close()
        if scratch is not None:app.ActiveDocument=scratch;assert scratch.Name==name;scratch.Close(2)
        if previous is not None:app.ActiveDocument=previous

if __name__=='__main__':asyncio.run(main())
