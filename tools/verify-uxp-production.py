"""Exercise the exact production bridge on a disposable Photoshop document."""
import asyncio,json,sys,time,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.uxp_bridge import UxpBridge
import win32com.client

async def main():
    app=win32com.client.GetActiveObject('Photoshop.Application')
    previous=app.ActiveDocument if app.Documents.Count else None
    name='UXP production '+str(time.time_ns())
    app.DoJavaScript('app.documents.add(32,32,72,'+json.dumps(name)+',NewDocumentMode.RGB,DocumentFill.TRANSPARENT);')
    scratch=app.ActiveDocument
    bridge=UxpBridge(task_history=Path('.runtime/uxp-production-tasks.json'),config=Path(os.environ['LOCALAPPDATA'])/'PhotoshopMenu/uxp-config.json')
    results=[]
    try:
        for action in ('label.red','label.none','color'):
            results.append(await bridge.execute(action))
        app.DoJavaScript("app.activeDocument.artLayers.add();app.activeDocument.activeLayer.name='Top';")
        results.append(await bridge.execute('moveToBottom'))
        assert app.DoJavaScript("app.activeDocument.layers[app.activeDocument.layers.length-1].name")=='Top'
        results.append(await bridge.execute('moveToTop'))
        assert app.DoJavaScript('app.activeDocument.layers[0].name')=='Top'
        results.append(await bridge.execute('select'))
        results.append(await bridge.execute('label.blue'))
        assert json.loads(results[-1]['result'])['count']==2
        app.DoJavaScript("var g=app.activeDocument.layerSets.add();g.name='Group';var a=g.artLayers.add();a.name='A';var b=g.artLayers.add();b.name='B';app.activeDocument.activeLayer=b;")
        results.append(await bridge.execute('moveToBottom'))
        assert app.DoJavaScript("app.activeDocument.layerSets[0].layers[1].name")=='B'
        results.append(await bridge.execute('moveToTop'))
        results.append(await bridge.execute('select'))
        assert json.loads((await bridge.execute('label.none'))['result'])['count']==2
        assert all(t['channel']=='uxp-local-files' for t in bridge.tasks.snapshot()['items'] if not t.get('restored'))
        Path('.runtime/uxp-production-physical.json').write_text(json.dumps({'version':'0.4.69','results':results,'verified_at':time.time()},indent=2),'utf-8')
        print('PASS production UXP bridge: labels, root/group order, selection, task channel')
    finally:
        await bridge.close()
        app.ActiveDocument=scratch
        app.DoJavaScript('app.activeDocument.close(SaveOptions.DONOTSAVECHANGES);')
        if previous is not None:app.ActiveDocument=previous
asyncio.run(main())
