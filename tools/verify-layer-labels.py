"""Verify label commands in a disposable Photoshop document; preserve user docs."""
import json
import sys
from pathlib import Path
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.layer_labels import LABEL_COLORS, label_script


def main():
    import win32com.client
    status = json.load(urlopen('http://127.0.0.1:15151/api/status', timeout=3))
    if status['photoshop']['busy']:
        raise RuntimeError('Wait for the current Photoshop action to finish')
    blocks = []
    # Clear only after setting a color: clearing an already-unlabelled layer
    # does not prove that a real label can be removed.
    for item in LABEL_COLORS[1:] + LABEL_COLORS[:1]:
        blocks.append("""
            %s
            if (readColor(first) !== %s || readColor(second) !== %s)
                throw new Error('Multi-selection label mismatch: ' + %s);
            if (readColor(untouched) !== 'none') throw new Error('Unselected layer was changed');
            passed.push(%s);
        """ % (label_script('label.' + item['id']), *([json.dumps(item['id'])] * 4)))
    script = """(function () {
        var previous = app.documents.length ? app.activeDocument : null;
        var scratch = null;
        var s = stringIDToTypeID, passed = [];
        function currentId() {
            var r = new ActionReference();
            r.putEnumerated(s('layer'), s('ordinal'), s('targetEnum'));
            return executeActionGet(r).getInteger(s('layerID'));
        }
        function select(id, add) {
            var r = new ActionReference(); r.putIdentifier(s('layer'), id);
            var d = new ActionDescriptor(); d.putReference(s('null'), r);
            if (add) d.putEnumerated(s('selectionModifier'), s('selectionModifierType'), s('addToSelection'));
            d.putBoolean(s('makeVisible'), false); executeAction(s('select'), d, DialogModes.NO);
        }
        function readColor(id) {
            var r = new ActionReference(); r.putIdentifier(s('layer'), id);
            return typeIDToStringID(executeActionGet(r).getEnumerationValue(s('color')));
        }
        try {
            scratch = app.documents.add(64, 64, 72, 'PhotoshopMenu disposable label test', NewDocumentMode.RGB, DocumentFill.TRANSPARENT);
            var untouched = currentId();
            scratch.artLayers.add(); var first = currentId();
            scratch.artLayers.add(); var second = currentId();
            select(first, false); select(second, true);
            %s
            select(first, false);
            %s
            if (readColor(first) !== 'red' || readColor(second) !== 'none') throw new Error('Single-selection label mismatch');
            %s
            if (readColor(first) !== 'none') throw new Error('Single-selection clear failed');
            var group = scratch.layerSets.add(), groupId = currentId();
            %s
            var child = group.artLayers.add(), childId = currentId();
            %s
            %s
            var groupResult = 'child=' + readColor(childId) + ', parent=' + readColor(groupId);
            if (readColor(childId) !== 'none' || readColor(groupId) !== 'orange') throw new Error('Group clear mismatch: '+groupResult);
            return 'Photoshop ' + app.version + ': ' + passed.join(',') + '; multi-selection, single-selection, colored-to-none, untouched layer passed; '+groupResult;
        } finally {
            if (scratch) scratch.close(SaveOptions.DONOTSAVECHANGES);
            if (previous) app.activeDocument = previous;
        }
    }());""" % ('\n'.join(blocks), label_script('label.red'), label_script('label.none'),
               label_script('label.orange'), label_script('label.red'), label_script('label.none'))
    app = win32com.client.GetActiveObject('Photoshop.Application')
    print(app.DoJavaScript(script))


if __name__ == '__main__':
    main()
