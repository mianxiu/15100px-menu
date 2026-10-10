import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../../jsx/move_to_top_or_bottom.jsx', import.meta.url), 'utf8');
function run(top) {
  const history = [];
  class Reference {
    putIndex(_, index) { this.index = index; }
    putIdentifier(_, index) { this.index = index; }
    putProperty(_, property) { this.property = property; }
    putEnumerated() {}
  }
  class Descriptor { putReference() {} putBoolean() {} }
  const document = {
    activeLayer: {itemIndex: 4, typename: 'ArtLayer', parent: {itemIndex: 5, name: 'group'}},
    get backgroundLayer() { throw new Error('no background'); },
    suspendHistory(label, expression) { history.push({label, expression}); },
  };
  vm.runInNewContext(source.replace(/=.*\/\*%Bool%\*\//, `= ${top}`), {
    activeDocument: document, app: {activeDocument: document},
    ActionReference: Reference, ActionDescriptor: Descriptor, DialogModes: {NO: 0},
    charIDToTypeID: x => x, stringIDToTypeID: x => x, $: {writeln() {}},
    executeAction() {}, executeActionGet(ref) {
      return {getInteger(key) {
        if (key === 'NmbL') return 5;
        if (key === 'layerID') return ref.index;
        if (key === 'layerKind') return ref.index === 1 ? 13 : 1;
        return ref.index;
      }, getString() { return 'layer'; }};
    },
  });
  return history;
}
test('topmost layer can move down, and moving up is a no-op', () => {
  assert.equal(run(true).length, 0);
  const down = run(false);
  assert.equal(down.length, 1);
  assert.equal(down[0].expression, 'move(BottomLayerIndex)');
});
