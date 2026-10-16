import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const create=require('../../uxp/offline-probe/labels.js');
const reference=require('../../tools/fixtures/selection-context-0.3.20.cjs');
const constants={LayerKind:{NORMAL:'pixel',GROUP:'group',TEXT:'text',SMARTOBJECT:'smart'},
 DocumentMode:{RGB:'RGB',CMYK:'CMYK'},BitsPerChannelType:{EIGHT:8,SIXTEEN:16}};
function host(count=100) {
 const layers=Array.from({length:count},(_,i)=>({id:100+i,kind:'pixel',parent:null}));
 const control={calls:[],materialized:0},doc={id:10,activeLayers:[layers[Math.floor(count/2)]],mode:'RGB',bitsPerChannel:8};
 control.layers=layers;
 Object.defineProperty(doc,'layers',{get(){return new Proxy(control.layers,{get(t,key){
  if(typeof key==='string' && /^\d+$/.test(key))control.materialized++;
  return Reflect.get(t,key);
 }});}});
 function rows(){
  const out=[];
  function walk(ls,parent=-1){for(const l of ls){
   if(l.isBackgroundLayer)continue;
   out.push({layerID:l.id,parentLayerID:parent,layerSection:{_value:l.kind==='group'?'layerSectionStart':'layerSectionContent'}});
   if(l.kind==='group'){walk(l.layers,l.id);out.push({layerSection:{_value:'layerSectionEnd'}});}
  }}
  walk(control.layers);return out.map((r,i)=>({...r,itemIndex:out.length-i}));
 }
 const ps={constants,app:{documents:[doc],activeDocument:doc},action:{async batchPlay([d]){
  control.calls.push(d);assert.ok(['get','multiGet'].includes(d._obj),'Native optimization stays read-only');
  assert.equal(d._options.dialogOptions,'dontDisplay');
  const list=rows();
  if(d._obj==='get'){
   assert.equal(d._target[0]._property,'numberOfLayers');
   if(control.fail)throw Error('Unavailable');
   return [{numberOfLayers:control.size??list.length}];
  }
  assert.deepEqual(d.extendedReference[0],['layerID','parentLayerID','layerSection','itemIndex']);
  assert.ok(d.extendedReference[1].count<=4096 && d.extendedReference[1].count>0);
  const result=control.result?control.result(list):list;
  if(control.after)control.after();
  return [{list:result}];
 }}};
 return {layers,doc,ps,control,api:create(ps,'s'),expected:()=>reference(ps,'s').selectionContext()};
}
test('cold middle native lookup avoids prefix object construction; warm lookup adds no native query',async()=>{
 for(const selected of [[50],[48,50,52]]) {
  const h=host();h.doc.activeLayers=selected.map(i=>h.layers[i]);const expected=h.expected();h.control.materialized=0;
  assert.deepEqual(await h.api.selectionContextFresh(),expected);
  assert.equal(h.control.calls.length,2);assert.ok(h.control.materialized<20,h.control.materialized);
  h.control.materialized=0;assert.deepEqual(await h.api.selectionContextFresh(),expected);
  assert.equal(h.control.calls.length,2);assert.ok(h.control.materialized<10,h.control.materialized);
 }
});
test('small lists, endpoint hits, known positions and majority selections preserve the DOM-only path',async()=>{
 for(const [count,indices] of [[4,[2]],[31,[15]],[100,[0]],[100,[99]],[100,Array.from({length:60},(_,i)=>i+10)]]) {
  const h=host(count);h.doc.activeLayers=indices.map(i=>h.layers[i]);
  assert.deepEqual(await h.api.selectionContextFresh(),h.expected());assert.equal(h.control.calls.length,0);
 }
 const h=host();h.api.selectionContext();assert.deepEqual(await h.api.selectionContextFresh(),h.expected());assert.equal(h.control.calls.length,0);
});
test('native parent and group-end indices never become unverified sibling positions',async()=>{
 const h=host(80),group={id:900,kind:'group',parent:null,layers:[]};
 const nested={id:901,kind:'group',parent:group,layers:[{id:902,kind:'text'}]};nested.layers[0].parent=nested;
 group.layers=h.layers.slice(10,70);for(const l of group.layers)l.parent=group;group.layers.splice(5,0,nested);
 h.control.layers=[...h.layers.slice(0,10),group,...h.layers.slice(70)];h.doc.activeLayers=[group.layers[30]];
 assert.deepEqual(await h.api.selectionContextFresh(),h.expected());assert.equal(h.control.calls.length,2);
 group.layers.reverse();group.allLocked=true;
 assert.deepEqual(await h.api.selectionContextFresh(),h.expected());
});
test('fresh DOM identity validates incorrect native positions and mutations made while awaiting native IDs',async()=>{
 for(const mode of ['wrong-order','wrong-parent','missing-field','changed-order','changed-lock-and-type','duplicate-id']) {
  const h=host();
  if(mode==='wrong-order')h.control.result=rows=>rows.reverse().map((r,i)=>({...r,itemIndex:100-i}));
  if(mode==='wrong-parent')h.control.result=rows=>rows.map(r=>({...r,parentLayerID:800}));
  if(mode==='missing-field')h.control.result=rows=>rows.map(({parentLayerID,...r})=>r);
  if(mode==='duplicate-id')h.control.result=rows=>[rows[0],...rows];
  if(mode==='changed-order')h.control.after=()=>h.control.layers.reverse();
  if(mode==='changed-lock-and-type')h.control.after=()=>{h.doc.activeLayers[0].positionLocked=true;h.doc.activeLayers[0].kind='text';};
  const value=await h.api.selectionContextFresh();assert.deepEqual(value,h.expected(),mode);
 }
});
test('native failures and oversized documents fall back with bounded queries and no cached capabilities',async()=>{
 for(const mode of ['fail','oversized']) {
  const h=host();h.control.fail=mode==='fail';if(mode==='oversized')h.control.size=4097;
  assert.deepEqual(await h.api.selectionContextFresh(),h.expected());assert.equal(h.control.calls.length,1);
  h.doc.activeLayers[0].positionLocked=true;
  assert.deepEqual(await h.api.selectionContextFresh(),h.expected());assert.equal(h.control.calls.length,1);
 }
});
test('document or selection change during native await rejects instead of enabling old capabilities',async()=>{
 for(const documentChange of [false,true]) {
  const h=host();h.control.after=()=>{if(documentChange)h.ps.app.activeDocument={...h.doc,id:20};else h.doc.activeLayers=[h.layers[60]];};
  await assert.rejects(h.api.selectionContextFresh(),/changed during read/);
 }
});
test('mixed types, locks, native background omission and reorder keep all capability fields equal',async()=>{
 for(let run=0;run<100;run++) {
  const h=host(40);h.layers[39].isBackgroundLayer=true;
  h.layers[20].kind=run%2?'smart':'text';h.layers[20].allLocked=run%3===0;
  if(run%4===0)h.control.layers.reverse();
  h.doc.activeLayers=run%2?[h.layers[20]]:[h.layers[19],h.layers[20]];
  h.doc.mode=run%5?'RGB':'CMYK';h.doc.bitsPerChannel=run%7?8:32;
  assert.deepEqual(await h.api.selectionContextFresh(),h.expected());
 }
});
