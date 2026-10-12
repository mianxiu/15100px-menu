"""Real installed UXP executor with independent Photoshop COM readback.

All writes use disposable documents. Also exercises the installed menu/API
target guard and stale-selection cancellation.
"""
import asyncio,json,time,sys
from pathlib import Path
from urllib.request import urlopen
import win32com.client
from tornado.httpclient import HTTPRequest
from tornado.websocket import websocket_connect
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.uxp_bridge import UxpBridge
from backend.layer_context import require_menu_target
from backend.version import APP_VERSION
BASE='http://127.0.0.1:15151'
def status():return json.load(urlopen(BASE+'/api/status',timeout=5))
READ="""(function(){var s=stringIDToTypeID,r=new ActionReference();r.putEnumerated(s('layer'),s('ordinal'),s('targetEnum'));var d=executeActionGet(r),t='';if(d.hasKey(s('adjustment')))t=typeIDToStringID(d.getList(s('adjustment')).getObjectType(0));function count(ls){var n=ls.length;for(var i=0;i<ls.length;i++)if(ls[i].typename==='LayerSet')n+=count(ls[i].layers);return n;}return [d.getInteger(s('layerID')),d.getInteger(s('layerKind')),t,count(app.activeDocument.layers),app.activeDocument.historyStates.length].join('|');})();"""
async def main():
    s=status();assert s['uxp']['version']=='0.3.5' and not s['photoshop']['busy']
    app=win32com.client.GetActiveObject('Photoshop.Application');previous=app.ActiveDocument if app.Documents.Count else None
    docs=[];checks=[];timings=[];name='Menu quick '+str(time.time_ns())
    bridge=UxpBridge(task_history=ROOT/'.runtime/quick-live-tasks.json',config=Path(s['data_dir'])/'uxp-config.json')
    def js(code):return app.DoJavaScript(code)
    def state():return js(READ)
    foreground=js('app.foregroundColor.rgb.red+","+app.foregroundColor.rgb.green+","+app.foregroundColor.rgb.blue')
    async def context(predicate=lambda v:bool(v.get('quick_mask'))):
        active_id=int(state().split('|')[0]);document_id=int(js('app.activeDocument.id'))
        start=time.monotonic()
        while time.monotonic()-start<4:
            v=status()['photoshop']['layer_context']
            if v.get('document_id')==document_id and active_id in v.get('layer_ids',[]) and predicate(v):return v
            await asyncio.sleep(.02)
        raise AssertionError(v)
    async def execute(action):
        frozen=await context();before=state();start=time.perf_counter()
        async def guard(target):require_menu_target(frozen,action,target)
        result=await bridge.execute(action,guard)
        after=state();timings.append({'action':action,'ms':round((time.perf_counter()-start)*1000,2)})
        checks.append({'action':action,'before':before,'after':after,'task_id':result['task_id']})
        return before.split('|'),after.split('|')
    ws=None
    try:
        js('app.documents.add(64,64,72,'+json.dumps(name)+',NewDocumentMode.RGB,DocumentFill.WHITE);');docs.append(app.ActiveDocument)
        await context(lambda v:v.get('kind')=='background' and v.get('quick_mask')==123)
        before,after=await execute('layer.new');assert after[1]=='1' and int(after[3])==int(before[3])+1
        js('var c=new SolidColor();c.rgb.red=12;c.rgb.green=34;c.rgb.blue=56;app.foregroundColor=c;')
        before,after=await execute('layer.solid');assert after[2]=='solidColorLayer' and int(after[3])==int(before[3])+1
        solid_id=int(after[0])
        color=js("(function(){var s=stringIDToTypeID,r=new ActionReference();r.putEnumerated(s('layer'),s('ordinal'),s('targetEnum'));var d=executeActionGet(r).getList(s('adjustment')).getObjectValue(0).getObjectValue(s('color'));return [d.getDouble(s('red')),d.getDouble(s('green')),d.getDouble(s('blue'))].join(',');})();")
        assert all(abs(a-b)<.1 for a,b in zip(map(float,color.split(',')),(12,34,56))),color
        checks.append({'solid_rgb_readback':color})
        for action,type in [('adjustment.curves','curves'),('adjustment.hueSaturation','hueSaturation'),('adjustment.colorBalance','colorBalance'),('adjustment.blackWhite','blackAndWhite')]:
            before,after=await execute(action);assert after[2]==type and int(after[3])==int(before[3])+1,(action,after)
        js("(function(){var s=stringIDToTypeID,r=new ActionReference();r.putIdentifier(s('layer'),"+str(solid_id)+");var d=new ActionDescriptor();d.putReference(s('null'),r);d.putEnumerated(s('selectionModifier'),s('selectionModifierType'),s('addToSelection'));d.putBoolean(s('makeVisible'),false);executeAction(s('select'),d,DialogModes.NO);})();")
        frozen=await context(lambda v:len(v.get('layer_ids',[]))==2);selected=frozen['layer_ids']
        before,after=await execute('layer.group');assert after[1]=='7' and int(after[3])==int(before[3])+1
        assert int(js('app.activeDocument.activeLayer.layers.length'))==2
        checks.append({'group_selected_ids':selected,'group_members_verified_in_uxp':True})
        # Rejected stale target must add neither a layer nor a history entry.
        frozen=await context();js('app.activeDocument.activeLayer=app.activeDocument.layers[1];');before=state()
        try:await bridge.execute('layer.new',lambda target:require_menu_target(frozen,'layer.new',target))
        except RuntimeError as e:assert '已改变' in str(e)
        else:raise AssertionError('Stale menu target accepted')
        assert state()==before;checks.append({'frozen_selection_change':'cancelled_without_history_or_write'})
        # Native production API: creation through the displayed menu epoch.
        await context()
        app.DoJavaScript('app.bringToFront();');await asyncio.sleep(.8)
        ws=await websocket_connect(HTTPRequest(BASE.replace('http','ws')+'/websocket',headers={'Origin':BASE}))
        async def call(action,args=None):
            id=str(time.time_ns());await ws.write_message(json.dumps({'id':id,'action':action,'args':args or {}}))
            while True:
                r=json.loads(await asyncio.wait_for(ws.read_message(),15))
                if r.get('id')==id:return r
        opened=await call('panel.hold_begin');assert opened['ok'],opened
        current=status();epoch=current['menu']['epoch'] if 'epoch' in current['menu'] else None
        # Obtain the epoch from status only when exposed; direct API still
        # enforces foreground and target capture without manufacturing input.
        args={'name':'layer.new'}
        if epoch is not None:args['menu_epoch']=epoch
        result=await call('action.execute',args);assert result['ok'],result
        checks.append({'production_menu_api':'layer.new','task':result['data']})
        report={'version':APP_VERSION,'uxp':'0.3.5','checks':checks,'execution_ms':timings,
                'scope':'Real disposable Photoshop documents, installed UXP executor and production menu/API. Physical keys/hover/click acceptance pending.'}
        (ROOT/f'.runtime/quick-layers-{APP_VERSION}-live.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
        print('PASS actual PS: seven commands, foreground RGB, exact grouping, frozen target protection, production API')
    finally:
        if ws:
            try:await ws.write_message(json.dumps({'id':'cleanup','action':'panel.hide'}))
            except Exception:pass
            ws.close()
        await bridge.close()
        await asyncio.sleep(.5)
        red,green,blue=map(float,foreground.split(','))
        js(f'var c=new SolidColor();c.rgb.red={red};c.rgb.green={green};c.rgb.blue={blue};app.foregroundColor=c;')
        for doc in docs:app.ActiveDocument=doc;assert doc.Name.startswith(name);doc.Close(2)
        if previous is not None:app.ActiveDocument=previous
if __name__=='__main__':asyncio.run(main())
