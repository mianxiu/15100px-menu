"""Compare installed UXP fill/adjustment insertion with native PS commands.

Writes only disposable named documents; tests parent, position, native names,
original tree preservation, one undo and stale-target rejection independently
through COM. Physical menu interaction remains a separate acceptance step.
"""
import asyncio
import json
import sys
import time
from pathlib import Path
from urllib.request import urlopen
import win32com.client

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.version import APP_VERSION
from backend.uxp_bridge import UxpBridge
from backend.layer_context import require_menu_target

BASE = 'http://127.0.0.1:15151'
VERSION = json.loads((ROOT/'uxp/offline-probe/manifest.json').read_text('utf-8'))['version']
READ = r"""(function(){var out=[];function walk(ls,parent){for(var i=0;i<ls.length;i++){var l=ls[i];out.push([parent,l.id,l.name].join('\t'));if(l.typename==='LayerSet')walk(l.layers,l.id);}}walk(app.activeDocument.layers,0);return out.join('\n');})();"""
ROOT_SETUP = "var d=app.activeDocument;function pixel(ls,name){var l=ls.artLayers.add();l.name=name;d.activeLayer=l;d.selection.selectAll();d.selection.fill(app.foregroundColor);d.selection.deselect();return l;}var low=pixel(d,'Lower'),mid=pixel(d,'Middle'),high=pixel(d,'Upper');d.activeLayer=mid;"
GROUP_SETUP = "var d=app.activeDocument;function pixel(ls,name){var l=ls.artLayers.add();l.name=name;d.activeLayer=l;d.selection.selectAll();d.selection.fill(app.foregroundColor);d.selection.deselect();return l;}var rootLow=pixel(d,'Root lower');var outer=d.layerSets.add();outer.name='Outer';var g=outer.layerSets.add();g.name='Target group';var a=pixel(g,'Child lower'),b=pixel(g,'Child middle'),c=pixel(g,'Child upper');var rootHigh=pixel(d,'Root upper');d.activeLayer=b;"
EMPTY_SETUP = "var d=app.activeDocument;var low=d.artLayers.add();low.name='Root lower';var g=d.layerSets.add();g.name='Empty group';var high=d.artLayers.add();high.name='Root upper';d.activeLayer=g;"
MULTI = "var s=stringIDToTypeID,r=new ActionReference();r.putIdentifier(s('layer'),low.id);var z=new ActionDescriptor();z.putReference(s('null'),r);z.putEnumerated(s('selectionModifier'),s('selectionModifierType'),s('addToSelection'));z.putBoolean(s('makeVisible'),false);executeAction(s('select'),z,DialogModes.NO);"


def native(command):
    type_name = {'layer.solid': 'solidColorLayer', 'adjustment.curves': 'curves',
                 'adjustment.hueSaturation': 'hueSaturation', 'adjustment.colorBalance': 'colorBalance',
                 'adjustment.blackWhite': 'blackAndWhite'}[command]
    obj = 'contentLayer' if command == 'layer.solid' else 'adjustmentLayer'
    settings = ''
    if command == 'layer.solid':
        settings = "var rgb=new ActionDescriptor();rgb.putDouble(s('red'),app.foregroundColor.rgb.red);rgb.putDouble(s('green'),app.foregroundColor.rgb.green);rgb.putDouble(s('blue'),app.foregroundColor.rgb.blue);t.putObject(s('color'),s('RGBColor'),rgb);"
    elif command in ('adjustment.curves', 'adjustment.hueSaturation'):
        settings = "t.putEnumerated(s('presetKind'),s('presetKindType'),s('presetKindDefault'));"
        if command == 'adjustment.hueSaturation':
            settings += "t.putBoolean(s('colorize'),false);"
    elif command == 'adjustment.colorBalance':
        settings = "var levels=new ActionList();levels.putInteger(0);levels.putInteger(0);levels.putInteger(0);t.putList(s('shadowLevels'),levels);t.putList(s('midtoneLevels'),levels);t.putList(s('highlightLevels'),levels);t.putBoolean(s('preserveLuminosity'),true);"
    else:
        settings = ''.join("t.putInteger(s('"+key+"'),"+str(value)+");" for key, value in [('red',40),('yellow',60),('green',40),('cyan',60),('blue',20),('magenta',80)]) + "t.putBoolean(s('useTint'),false);"
    return "var s=stringIDToTypeID,r=new ActionReference();r.putClass(s('"+obj+"'));var t=new ActionDescriptor();"+settings+"var u=new ActionDescriptor();u.putObject(s('type'),s('"+type_name+"'),t);var z=new ActionDescriptor();z.putReference(s('null'),r);z.putObject(s('using'),s('"+obj+"'),u);executeAction(s('make'),z,DialogModes.NO);"


def status():
    return json.load(urlopen(BASE+'/api/status', timeout=5))


async def main():
    current = status()
    assert current['version'] == APP_VERSION and current['uxp']['version'] == VERSION
    assert current['photoshop']['uxp_ready'] and not current['photoshop']['busy']
    app = win32com.client.GetActiveObject('Photoshop.Application')
    previous = app.ActiveDocument if app.Documents.Count else None
    prefix = 'Menu insertion verification '+str(time.time_ns())
    docs, checks = [], []
    bridge = UxpBridge(task_history=ROOT/'.runtime/created-layer-live-tasks.json',
                       config=Path(current['data_dir'])/'uxp-config.json')

    def js(code):
        return app.DoJavaScript(code)

    def tree():
        return [{'parent':int(parent),'id':int(id),'name':name}
                for parent,id,name in (line.split('\t',2) for line in js(READ).splitlines())]

    def create(case, setup):
        js('app.documents.add(32,32,72,'+json.dumps(prefix+' '+case)+',NewDocumentMode.RGB,DocumentFill.WHITE);'+setup)
        doc=app.ActiveDocument
        docs.append(doc)
        return doc

    def signature(rows, id):
        made=next(row for row in rows if row['id']==id)
        parent=next((row['name'] for row in rows if row['id']==made['parent']),None)
        siblings=[row for row in rows if row['parent']==made['parent']]
        index=next(i for i,row in enumerate(siblings) if row['id']==id)
        return {'name':made['name'],'parent_name':parent,
                'next_name':siblings[index+1]['name'] if index+1<len(siblings) else None}

    async def context():
        doc_id=int(js('app.activeDocument.id'))
        active_id=int(js('app.activeDocument.activeLayer.id'))
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            value=status()['photoshop']['layer_context']
            if value.get('document_id')==doc_id and active_id in value.get('layer_ids',[]):
                return value
            await asyncio.sleep(.02)
        raise AssertionError(value)

    empty_pixel=ROOT_SETUP.replace("d.selection.selectAll();d.selection.fill(app.foregroundColor);d.selection.deselect();",'')
    cases=[('root-middle',ROOT_SETUP),('root-empty-pixel',empty_pixel),('root-bottom',ROOT_SETUP+'d.activeLayer=low;'),
           ('group-child',GROUP_SETUP),('group-itself',GROUP_SETUP+'d.activeLayer=g;'),
           ('group-empty',EMPTY_SETUP),('multi-focus-lower',ROOT_SETUP+MULTI),('background','')]
    commands=['layer.solid','adjustment.curves','adjustment.hueSaturation','adjustment.colorBalance','adjustment.blackWhite']
    try:
        for case,setup in cases:
            for command in commands:
                # Native make consumes an empty selected pixel layer and keeps
                # its name. Our required behaviour preserves the original;
                # compare default creation name/position with a filled anchor,
                # then independently assert the empty original tree is intact.
                reference=create(case+' native '+command,ROOT_SETUP if case=='root-empty-pixel' else setup)
                js(native(command))
                reference_rows=tree()
                expected=signature(reference_rows,int(js('app.activeDocument.activeLayer.id')))
                reference.Close(2)
                docs.remove(reference)
                doc=create(case+' plugin '+command,setup)
                frozen=await context()
                before=tree()
                async def guard(target):
                    require_menu_target(frozen,command,target)
                binding={key:frozen[key] for key in ('session','document_id','layer_ids')}
                binding['active_layer_id']=binding['layer_ids'][0]
                result=await bridge.execute(command,guard,frozen_target=binding if len(binding['layer_ids'])==1 else None)
                after=tree()
                creation=json.loads(result['result'])
                assert creation['placement_moves']==0,(case,command,'Native creation was moved')
                added=[row for row in after if row['id'] not in {row['id'] for row in before}]
                assert len(added)==1,(case,command,added)
                actual=signature(after,added[0]['id'])
                assert actual==expected,(case,command,actual,expected)
                assert [row for row in after if row['id']!=added[0]['id']]==before,(case,command,'original tree changed')
                js('var d=app.activeDocument;d.activeHistoryState=d.historyStates[d.historyStates.length-2];')
                assert tree()==before,(case,command,'single undo')
                checks.append({'case':case,'command':command,'native':expected,'actual':actual,
                               'native_reference_filled_anchor':case=='root-empty-pixel',
                               'placement_moves':creation['placement_moves'],'placeholder_used':creation['placeholder_used'],
                               'original_tree_preserved':True,'single_undo':True,'task_id':result['task_id']})
                print('Passed real PS:',case,command,actual,flush=True)
                doc.Close(2)
                docs.remove(doc)
        doc=create('stale target',ROOT_SETUP)
        frozen=await context()
        js('app.activeDocument.activeLayer=app.activeDocument.layers[0];')
        before=tree()
        try:
            async def guard(target):
                require_menu_target(frozen,'adjustment.curves',target)
            binding={key:frozen[key] for key in ('session','document_id','layer_ids')}
            binding['active_layer_id']=binding['layer_ids'][0]
            await bridge.execute('adjustment.curves',guard,frozen_target=binding)
        except RuntimeError:
            pass
        else:
            raise AssertionError('Stale target accepted')
        assert tree()==before
        checks.append({'stale_selection_rejected_without_write':True})
        report={'version':APP_VERSION,'uxp':VERSION,'checks':checks,
                'scope':'Installed executor vs native Photoshop commands in disposable documents; physical menu acceptance separate.'}
        (ROOT/f'.runtime/created-layers-{APP_VERSION}-live.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
        print('PASS',len(cases)*len(commands),'creation cases; native default names/placement, empty originals preserved, one undo; stale target rejected')
    finally:
        await bridge.close()
        await asyncio.sleep(.3)
        for doc in docs:
            app.ActiveDocument=doc
            assert doc.Name.startswith(prefix)
            doc.Close(2)
        if previous is not None:
            app.ActiveDocument=previous


if __name__=='__main__':
    asyncio.run(main())
