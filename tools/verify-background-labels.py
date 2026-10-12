"""Installed API + real PS scratch layers. Never writes an existing document."""
import asyncio,json,sys,time
from pathlib import Path
from urllib.request import urlopen
import win32com.client
from tornado.httpclient import HTTPRequest
from tornado.websocket import websocket_connect

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.version import APP_VERSION
from backend.uxp_bridge import UxpBridge

async def main():
    base='http://127.0.0.1:15151';status=json.load(urlopen(base+'/api/status'))
    assert status['version']==APP_VERSION and not status['photoshop']['busy']
    assert status['photoshop']['uxp_ready'] and status['photoshop']['uxp_version']=='0.3.3'
    app=win32com.client.GetActiveObject('Photoshop.Application')
    previous=app.ActiveDocument if app.Documents.Count else None
    name='Menu background verification '+str(time.time_ns());scratch=None;ws=None;checks=[]
    transport_only='--transport-only' in sys.argv
    bridge=UxpBridge(task_history=ROOT/'.runtime/background-bridge-tasks.json',config=Path(status['data_dir'])/'uxp-config.json') if transport_only else None
    read="""(function(){var s=stringIDToTypeID,r=new ActionReference();r.putEnumerated(s('layer'),s('ordinal'),s('targetEnum'));var d=executeActionGet(r);return d.getInteger(s('layerID'))+'|'+app.activeDocument.activeLayer.isBackgroundLayer+'|'+(d.hasKey(s('color'))?typeIDToStringID(d.getEnumerationValue(s('color'))):'absent')+'|'+app.activeDocument.historyStates.length;})();"""
    try:
        app.DoJavaScript('app.documents.add(32,32,72,'+json.dumps(name)+',NewDocumentMode.RGB,DocumentFill.WHITE);app.bringToFront();')
        scratch=app.ActiveDocument;await asyncio.sleep(.3)
        ws=await websocket_connect(HTTPRequest(base.replace('http','ws')+'/websocket',headers={'Origin':base}))
        async def call(action,args):
            if bridge and action=='action.execute':
                try:return {'ok':True,'data':await bridge.execute(args['name'])}
                except RuntimeError as e:return {'ok':False,'error':str(e),'task_id':getattr(e,'task_id',None)}
            if action=='action.execute':
                app.DoJavaScript('app.bringToFront();')
                await asyncio.sleep(.2)
            id=str(time.time_ns());await ws.write_message(json.dumps({'id':id,'action':action,'args':args}))
            while True:
                result=json.loads(await asyncio.wait_for(ws.read_message(),15))
                if result.get('id')==id:return result
        initial=app.DoJavaScript(read)
        for color in ('red','none','blue'):
            reply=await call('action.execute',{'name':'label.'+color})
            assert not reply['ok'] and '背景图层' in reply['error'] and reply['task_id'],reply
            assert app.DoJavaScript(read)==initial,'Background ID/lock/color/history changed on rejection'
            current=json.load(urlopen(base+'/api/status'))
            tasks=bridge.tasks.snapshot() if bridge else current['tasks']
            task=next(t for t in tasks['items'] if t['id']==reply['task_id'])
            assert task['state']=='failed' and not current['photoshop']['busy']
            checks.append({'kind':'background-rejected','color':color,'task':task,'unchanged':True})
        app.DoJavaScript("app.activeDocument.artLayers.add();app.activeDocument.activeLayer.name='Regular';")
        for color in ('red','orange','yellowColor','grain','blue','violet','gray','none'):
            reply=await call('action.execute',{'name':'label.'+color})
            assert reply['ok'],reply
            assert app.DoJavaScript(read).split('|')[2]==color
            checks.append({'kind':'regular-success','color':color,'task_id':reply['data']['task_id']})
        app.DoJavaScript("var s=stringIDToTypeID,r=new ActionReference(),d=new ActionDescriptor();r.putIdentifier(s('layer'),1);d.putReference(s('null'),r);d.putEnumerated(s('selectionModifier'),s('selectionModifierType'),s('addToSelection'));d.putBoolean(s('makeVisible'),false);executeAction(s('select'),d,DialogModes.NO);")
        before=app.DoJavaScript(read)
        reply=await call('action.execute',{'name':'label.red'})
        assert not reply['ok'] and '背景图层' in reply['error'],reply
        assert app.DoJavaScript(read)==before
        normal=app.DoJavaScript("(function(){var s=stringIDToTypeID,r=new ActionReference();r.putIndex(s('layer'),1);return typeIDToStringID(executeActionGet(r).getEnumerationValue(s('color')));})();")
        assert normal=='none','Mixed selection partially colored the regular layer'
        checks.append({'kind':'mixed-rejected','no_partial_writes':True,'reply':reply})
        # Unlock is explicit user-equivalent setup, not performed by label code.
        app.DoJavaScript("var s=stringIDToTypeID,r=new ActionReference(),d=new ActionDescriptor();r.putIdentifier(s('layer'),1);d.putReference(s('null'),r);d.putBoolean(s('makeVisible'),false);executeAction(s('select'),d,DialogModes.NO);app.activeDocument.activeLayer.isBackgroundLayer=false;")
        assert app.DoJavaScript(read).split('|')[1]=='false','Scratch unlock setup did not select Background'
        reply=await call('action.execute',{'name':'label.blue'})
        assert reply['ok'] and app.DoJavaScript(read).split('|')[2]=='blue',reply
        checks.append({'kind':'unlocked-background-success','reply':reply})
        samples=[]
        for _ in range(12):
            s=json.load(urlopen(base+'/api/status'));samples.append(s['photoshop'])
            assert not s['photoshop']['busy'] and s['photoshop']['status_fresh']
            assert '状态等待更新' not in s['photoshop']['message']
            await asyncio.sleep(.12)
        (ROOT/'.runtime/background-labels-0.4.92-live.json').write_text(json.dumps({
            'version':APP_VERSION,'uxp':'0.3.3','checks':checks,'status_samples':samples,
            'transport_only':transport_only,
            'scope':('Installed UXP protocol and source task bridge with real scratch readback; production focus API and physical gestures pending' if bridge else 'Installed production API, actual PS focus guards and scratch readback; physical Caps/hover/cancel acceptance pending')},ensure_ascii=False,indent=2),'utf-8')
        print('PASS real PS: background rejected unchanged; 8 regular labels; mixed selection atomic; explicit unlock label; idle/fresh after tasks')
    finally:
        if ws:ws.close()
        if bridge:await bridge.close()
        if scratch is not None:
            app.ActiveDocument=scratch;assert scratch.Name==name;scratch.Close(2)
        if previous is not None:app.ActiveDocument=previous

if __name__=='__main__':asyncio.run(main())
