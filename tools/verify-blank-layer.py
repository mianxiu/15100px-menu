"""Installed UXP blank creation, with native naming and independent COM readback.

Only disposable documents are written. No physical keys/clicks are simulated.
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
from backend.uxp_bridge import UxpBridge
from backend.layer_context import require_menu_target
from backend.version import APP_VERSION

BASE = 'http://127.0.0.1:15151'
NATIVE = "var r=new ActionReference();r.putClass(charIDToTypeID('Lyr '));var d=new ActionDescriptor();d.putReference(charIDToTypeID('null'),r);executeAction(charIDToTypeID('Mk  '),d,DialogModes.NO);app.activeDocument.activeLayer.name;"
READ = r"""(function(){var out=[];function walk(ls,parent){for(var i=0;i<ls.length;i++){var l=ls[i];out.push([parent,l.id,l.name].join('\t'));if(l.typename==='LayerSet')walk(l.layers,l.id);}}walk(app.activeDocument.layers,0);return out.join('\n');})();"""
SETUP_ROOT = "var d=app.activeDocument;var low=d.artLayers.add();low.name='Lower';var mid=d.artLayers.add();mid.name='Middle';var high=d.artLayers.add();high.name='Upper';d.activeLayer=mid;"
SETUP_GROUP = "var d=app.activeDocument;var low=d.artLayers.add();low.name='Root lower';var outer=d.layerSets.add();outer.name='Outer';var g=outer.layerSets.add();g.name='Target group';var a=g.artLayers.add();a.name='Child lower';var b=g.artLayers.add();b.name='Child middle';var c=g.artLayers.add();c.name='Child upper';var high=d.artLayers.add();high.name='Root upper';"
MULTI = "var s=stringIDToTypeID,r=new ActionReference();r.putIdentifier(s('layer'),low.id);var desc=new ActionDescriptor();desc.putReference(s('null'),r);desc.putEnumerated(s('selectionModifier'),s('selectionModifierType'),s('addToSelection'));desc.putBoolean(s('makeVisible'),false);executeAction(s('select'),desc,DialogModes.NO);"

def status():
    return json.load(urlopen(BASE + '/api/status', timeout=5))

async def main():
    current = status()
    assert current['version'] == APP_VERSION and not current['photoshop']['busy']
    assert current['uxp']['version'] == '0.3.6' and current['photoshop']['uxp_ready']
    app = win32com.client.GetActiveObject('Photoshop.Application')
    previous = app.ActiveDocument if app.Documents.Count else None
    prefix = 'Menu blank verification ' + str(time.time_ns())
    docs, checks = [], []
    bridge = UxpBridge(task_history=ROOT / '.runtime/blank-live-tasks.json',
                       config=Path(current['data_dir']) / 'uxp-config.json')

    def js(code):
        return app.DoJavaScript(code)

    def tree():
        return [{'parent': int(p), 'id': int(i), 'name': n}
                for p, i, n in (line.split('\t', 2) for line in js(READ).splitlines())]

    def create(case, setup):
        js('app.documents.add(32,32,72,' + json.dumps(prefix + ' ' + case) +
           ',NewDocumentMode.RGB,DocumentFill.WHITE);' + setup)
        doc = app.ActiveDocument
        docs.append(doc)
        return doc

    async def context():
        doc_id = int(js('app.activeDocument.id'))
        active_id = int(js('app.activeDocument.activeLayer.id'))
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            value = status()['photoshop']['layer_context']
            if value.get('document_id') == doc_id and active_id in value.get('layer_ids', []):
                return value
            await asyncio.sleep(.02)
        raise AssertionError(value)

    cases = [('root-middle', SETUP_ROOT),
             ('root-bottom', SETUP_ROOT + 'd.activeLayer=low;'),
             ('root-top', SETUP_ROOT + 'd.activeLayer=high;'),
             ('default-name-counter', SETUP_ROOT + "high.name='Layer 7';mid.name='Layer 3';low.name='Layer 2';"),
             ('group-child', SETUP_GROUP + 'd.activeLayer=b;'),
             ('group-itself', SETUP_GROUP + 'd.activeLayer=g;'),
             ('multi-focus-lower', SETUP_ROOT + MULTI),
             ('background', '')]
    try:
        for case, setup in cases:
            reference = create(case + ' native', setup)
            expected_name = js(NATIVE)
            reference.Close(2)
            docs.remove(reference)
            doc = create(case, setup)
            frozen = await context()
            before = tree()
            # Independently identify the exact active anchor, including the
            # focused member of a multi-selection rather than its sorted IDs.
            anchor_id = int(js('app.activeDocument.activeLayer.id'))
            anchor = next(row for row in before if row['id'] == anchor_id)
            async def guard(target):
                require_menu_target(frozen, 'layer.new', target)
            result = await bridge.execute('layer.new', guard)
            after = tree()
            new = [row for row in after if row['id'] not in {r['id'] for r in before}]
            assert len(new) == 1, (case, new)
            made = new[0]
            assert made['name'] == expected_name, (case, made, expected_name)
            assert made['parent'] == anchor['parent'], (case, made, anchor)
            siblings = [row['id'] for row in after if row['parent'] == anchor['parent']]
            assert siblings.index(made['id']) + 1 == siblings.index(anchor_id), (case, siblings)
            assert [row for row in after if row['id'] != made['id']] == before, case
            assert int(js('app.activeDocument.activeLayer.id')) == made['id']
            # One undo must remove the creation and any corrective placement.
            js('var d=app.activeDocument;d.activeHistoryState=d.historyStates[d.historyStates.length-2];')
            assert tree() == before, ('single undo', case)
            checks.append({'case': case, 'name': made['name'], 'native_name': expected_name,
                           'anchor': anchor, 'created': made, 'same_parent_above': True,
                           'original_layers_preserved': True, 'single_undo': True,
                           'task_id': result['task_id']})
            print('Passed real PS case:',case,'name:',made['name'],flush=True)
            doc.Close(2)
            docs.remove(doc)
        doc = create('frozen target', SETUP_ROOT)
        frozen = await context()
        js('app.activeDocument.activeLayer=app.activeDocument.layers[0];')
        before = tree()
        try:
            async def guard(target):
                require_menu_target(frozen, 'layer.new', target)
            await bridge.execute('layer.new', guard)
        except RuntimeError:
            pass
        else:
            raise AssertionError('Stale target accepted')
        assert tree() == before
        checks.append({'frozen_target_rejected_without_creation': True})
        report = {'version': APP_VERSION, 'uxp': '0.3.6', 'checks': checks,
                  'scope': 'Real PS disposable documents and installed UXP executor; physical menu clicks remain separate.'}
        (ROOT / f'.runtime/blank-layer-{APP_VERSION}-live.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
        print('PASS 8 real PS cases: native naming, exact active anchor, same parent, prior layers preserved, single undo; stale target rejected')
    finally:
        await bridge.close()
        await asyncio.sleep(.3)
        for doc in docs:
            app.ActiveDocument = doc
            assert doc.Name.startswith(prefix)
            doc.Close(2)
        if previous is not None:
            app.ActiveDocument = previous

if __name__ == '__main__':
    asyncio.run(main())
