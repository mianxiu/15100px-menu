"""Verify protected writes in disposable PS documents, restoring user document."""
import asyncio
import json
import sys
import time
from pathlib import Path
from urllib.request import urlopen

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.photoshop_bridge import PhotoshopBridge


async def main():
    status=json.load(urlopen('http://127.0.0.1:15151/api/status',timeout=5))
    if status['photoshop']['busy']:raise RuntimeError('Wait for current operation; do not interrupt')
    bridge=PhotoshopBridge()
    loop=asyncio.get_running_loop()
    async def js(source):
        return await loop.run_in_executor(bridge.executor,lambda:bridge._application().DoJavaScript(source))
    stem='Menu target verification '+str(time.time_ns())
    names=[stem+' A',stem+' B']
    a,b=map(json.dumps,names)
    helper="""var s=stringIDToTypeID;
        function select(id,add){var r=new ActionReference();r.putIdentifier(s('layer'),id);
            var d=new ActionDescriptor();d.putReference(s('null'),r);
            if(add)d.putEnumerated(s('selectionModifier'),s('selectionModifierType'),s('addToSelection'));
            d.putBoolean(s('makeVisible'),false);executeAction(s('select'),d,DialogModes.NO);}
        function color(id){var r=new ActionReference();r.putIdentifier(s('layer'),id);
            return typeIDToStringID(executeActionGet(r).getEnumerationValue(s('color')));}
    """
    previous=None
    passed=[]
    try:
        previous=await js("app.documents.length ? app.activeDocument.name : ''")
        setup="""(function(){
            var a=app.documents.add(32,32,72,%s,NewDocumentMode.RGB,DocumentFill.TRANSPARENT);
            var first=a.activeLayer.id;var second=a.artLayers.add().id;var third=a.artLayers.add().id;
            var b=app.documents.add(32,32,72,%s,NewDocumentMode.RGB,DocumentFill.TRANSPARENT);
            return '['+first+','+second+','+third+']';
        }());""" % (a,b)
        ids=json.loads(await js(setup))
        async def reset(multi=False):
            await js('(function(){'+helper+f'app.activeDocument=app.documents.getByName({a});select({ids[0]},false);'
                     +(f'select({ids[1]},true);' if multi else '')+'}());')
        async def read():
            return await js('(function(){'+helper+"return '['+"+
                "+','+".join(f"color({ident})" for ident in ids)+"+']';}());")
        await reset()
        result=await bridge.execute('label.red')
        assert result['target']['layer_ids']==[ids[0]]
        assert await read()=='[red,none,none]'
        await bridge.execute('label.none')
        passed.append('unchanged target writes and read-back')
        async def blocked(name,source,multi=False):
            await reset(multi)
            async def change(target):await js(source)
            try:await bridge.execute('label.blue',before_dispatch=change)
            except RuntimeError as exc:
                assert '取消' in str(exc),str(exc)
            else:raise AssertionError('Changed target was not rejected: '+name)
            await reset()
            assert await read()=='[none,none,none]'
            passed.append(name)
        await blocked('document switch rejects reused layer IDs',f'app.activeDocument=app.documents.getByName({b});')
        await blocked('selection change rejected','(function(){'+helper+f'select({ids[1]},false);'+'}());')
        await blocked('multi-selection member replacement rejected','(function(){'+helper+f'select({ids[0]},false);select({ids[2]},true);'+'}());',True)
        # Delete/close after capture; ensure no write is redirected to B.
        await reset()
        async def deleted(target):await js('app.activeDocument.activeLayer.remove();')
        try:await bridge.execute('label.blue',before_dispatch=deleted)
        except RuntimeError as exc:assert '取消' in str(exc)
        else:raise AssertionError('Deleted target was not rejected')
        passed.append('deleted layer rejected')
        async def closed(target):await js(f'app.activeDocument.close(SaveOptions.DONOTSAVECHANGES);app.activeDocument=app.documents.getByName({b});')
        try:await bridge.execute('label.blue',before_dispatch=closed)
        except RuntimeError as exc:assert '取消' in str(exc)
        else:raise AssertionError('Closed document was not rejected')
        color_b=await js('(function(){'+helper+'return color(app.activeDocument.activeLayer.id);}());')
        assert color_b=='none',color_b
        passed.append('closed document rejected; other document unchanged')
        report={'photoshop_version':str(await loop.run_in_executor(bridge.executor,lambda:bridge._application().Version)),
                'passed':passed,'physical_menu_acceptance':'pending'}
        Path('.runtime/operation-target-photoshop-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False))
    finally:
        # Only close our unique scratch documents; preserve all user documents.
        await js('(function(){for(var i=app.documents.length-1;i>=0;i--){var d=app.documents[i];'
                 +f'if(d.name==={a} || d.name==={b})d.close(SaveOptions.DONOTSAVECHANGES);'
                 +'}'+(f'try{{app.activeDocument=app.documents.getByName({json.dumps(previous)});}}catch(e){{}}' if previous else '')+'}());')
        await bridge.close()


if __name__=='__main__':asyncio.run(main())
