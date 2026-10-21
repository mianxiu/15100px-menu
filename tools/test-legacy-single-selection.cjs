// Run the production single-layer rollback with PS history's selection side effect.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('jsx/legacy_shape_preview.jsx','utf8');
const target=source.slice(source.indexOf('    function target()'),source.indexOf('    function order()'));
const vectorMask=source.slice(source.indexOf('    function vectorMaskChanged('),source.indexOf('    function maskClose('));
const rollback=source.slice(source.indexOf('    function restoreSingleSelection()')>=0?source.indexOf('    function restoreSingleSelection()'):source.indexOf('    function rollback()'),source.indexOf('    function batchRun()'));
function fixture(){
 let active=26,document=59,style='preview';const events=[];
 const doc={id:59,get activeLayer(){return {id:active};},set activeHistoryState(v){
  assert.equal(v,'original');events.push('history');active=24;style='original';f.onHistory?.();
 }};
 const f={events,onHistory:null,onRefresh:null,setActive(v){active=v;},setDocument(v){document=v;}};
 const context={doc,request:{target:{document_id:59,active_layer_id:26}},anchor:{id:26,typename:'Document'},
  app:{get activeDocument(){return {id:document};},refresh(){events.push('refresh');f.onRefresh?.();}},
  selected:()=>[active],originalHistory:'original',originalMask:{},prepared:{raw:{vector:false}},
  restoring:false,changed:true,redraws:0,baseline:{style:'original'},layerDescriptor:()=>({style}),
  raw:v=>v.style,same:(a,b)=>a===b,mask:()=>({}),maskClose:()=>true,progress(){},
  c:v=>v,s:v=>v,DialogModes:{NO:0},ActionReference:class{
   constructor(){this.parts=[];}putIdentifier(k,v){this.parts.push([k,v]);}},
  ActionDescriptor:class{constructor(){this.values={};}putReference(k,v){this.values[k]=v;}putBoolean(k,v){this.values[k]=v;}},
  executeAction(k,d){assert.equal(k,'slct');assert.deepEqual(d.values.null.parts,[['Lyr ',26],['document',59]]);
   assert.equal(d.values.MkVs,false);events.push('select');active=26;},
 };
 vm.createContext(context);vm.runInContext(vectorMask+target+rollback+'this.rollbackTest=rollback;',context);
 context.invariants=()=>{context.target();events.push('verify');return {style};};
 f.run=context.rollbackTest;f.context=context;return f;
}
if(process.argv.includes('--expect-old-failure')){
 const f=fixture();assert.throws(f.run,/Preview target changed/);assert.deepEqual(f.events,['history','refresh']);
 console.log('REPRODUCED: history rollback alone changes selection 26 -> 24; old code misreports target changed');
 process.exit(0);
}
{
 const f=fixture();f.run();assert.deepEqual(f.events,['history','select','refresh','verify']);assert.equal(f.context.redraws,1);
}
{
 const f=fixture();f.setActive(24);assert.throws(f.run,/Preview target changed/);assert.deepEqual(f.events,[]);
}
{
 const f=fixture();f.onHistory=()=>f.setDocument(60);assert.throws(f.run,/document changed/);assert.deepEqual(f.events,['history']);
}
{
 const f=fixture();f.onRefresh=()=>f.setActive(24);assert.throws(f.run,/Preview target changed/);
 assert.deepEqual(f.events,['history','select','refresh']);
}
{
 const f=fixture();f.context.executeAction=()=>{throw Error('Selection failed');};
 assert.throws(f.run,/Selection failed/);assert.deepEqual(f.events,['history']);
}
console.log('PASS single rollback: history-induced selection restored, document-qualified no-visibility select, external target change/read/write failures still reject');
