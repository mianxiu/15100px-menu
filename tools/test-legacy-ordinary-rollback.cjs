const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('jsx/legacy_shape_preview.jsx','utf8');
const helper=source.slice(source.indexOf('    function vectorMaskChanged('),source.indexOf('    function maskClose('));
const rollback=source.slice(source.indexOf('    function restoreSingleSelection()'),source.indexOf('    function batchRun()'));
function fixture(vector){
 let style='preview',active=4;const events=[];
 const doc={id:153,set activeHistoryState(v){assert.equal(v,'original');style='original';events.push('history');}};
 const box={doc,request:{target:{document_id:153,active_layer_id:4}},prepared:{raw:{vector}},
  originalHistory:'original',originalMask:vector?{feather:0,density:100}:null,changed:true,
  baseline:{style:'original'},raw:v=>v.style,same:(a,b)=>a===b,layerDescriptor:()=>({style}),
  target(){assert.equal(active,4);},invariants:()=>({style}),mask:()=>({feather:0,density:100}),
  maskClose(a,b){assert.ok(a && b,'ordinary fill must never evaluate a null vector mask');events.push('mask');return a.feather===b.feather && a.density===b.density;},
  app:{activeDocument:doc,refresh(){events.push('refresh');}},progress(){},redraws:0,c:v=>v,s:v=>v,
  DialogModes:{NO:0},ActionReference:class{putIdentifier(){}},ActionDescriptor:class{putReference(){}putBoolean(){}},executeAction(){active=4;events.push('select');}};
 vm.createContext(box);vm.runInContext(helper+rollback+'this.run=rollback;',box);return {box,events};
}
{
 const f=fixture(false);f.box.run();assert.deepEqual(f.events,['history','select','refresh']);
 assert.equal(f.box.redraws,1);
}
{
 const f=fixture(true);f.box.run();assert.deepEqual(f.events,['history','select','refresh','mask']);
}
// The old mixed expression under the precedence documented for ExtendScript
// reaches maskClose(null) despite vector=false. This emulates grouping only;
// actual Photoshop-engine verification is separately recorded.
{
 const f=fixture(false);const oldGrouping=()=>((true || false || false) && f.box.maskClose({},null));
 assert.throws(oldGrouping,/ordinary fill/);
}
assert.ok(!source.includes('|| prepared.raw.vector &&'));
console.log('PASS ordinary rollback avoids vector-only state; real vector verification and one redraw remain');
