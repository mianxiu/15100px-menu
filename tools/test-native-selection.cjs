const assert=require('node:assert/strict');
const create=require('../uxp/offline-probe/labels.js');
const K={NORMAL:'pixel',GROUP:'group',TEXT:'text',SMARTOBJECT:'smart',SOLIDFILL:'fill',GRADIENTFILL:'gradient',PATTERNFILL:'pattern',CURVES:'adjustment',VIDEO:'video',LAYER3D:'3d'};
const M={RGB:'rgb',CMYK:'cmyk',LAB:'lab',GRAYSCALE:'gray'},B={EIGHT:8,SIXTEEN:16,THIRTYTWO:32};
let selected=[2],changed=false,malformed=false,reads=0,modals=0,documentCount=1,closedDuringRead=false;
const raw=[{layerID:1,parentLayerID:-1,itemIndex:3,layerKind:1},{layerID:2,parentLayerID:-1,itemIndex:2,layerKind:3},{layerID:3,parentLayerID:-1,itemIndex:1,layerKind:5}].map(x=>({...x,background:false,layerSection:{_value:'layerSectionContent'},layerLocking:{protectAll:false,protectPosition:false}}));
const ps={constants:{LayerKind:K,DocumentMode:M,BitsPerChannelType:B},app:new Proxy({},{get(){throw Error('Host DOM must not be read');}}),core:{executeAsModal:async()=>{modals++;throw Error('Idle read must not enter modal');}},action:{batchPlay:async commands=>commands.map(c=>{
 reads++;assert.equal(c._options.dialogOptions,'silent');
 if(c._target?.[0]?._property==='numberOfDocuments')return {numberOfDocuments:documentCount};
 if(documentCount===0 || closedDuringRead)return {_obj:'error',message:'current document unavailable'};
 if(c._obj==='multiGet'){
  if(c.extendedReference.length===1){
   const ref=c._target._ref[0];
   return raw.find(x=>ref._id?x.layerID===ref._id:ref._index!==undefined?x.itemIndex===ref._index+(raw.some(x=>x.background)?1:0):x.layerID===selected[0]) || {_obj:'error'};
  }
  return {list:malformed?raw.slice(1):raw};
 }
 assert.equal(c._obj,'get');
 const key=c._target[0]._property;
 const values={layerID:selected[0],documentID:9,targetLayersIDs:(changed?[1]:selected).map(_id=>({_ref:'layer',_id})),numberOfLayers:raw.length-(raw.some(x=>x.background)?1:0),hasBackgroundLayer:raw.some(x=>x.background),mode:{_value:'RGBColor'},depth:8};
 return {[key]:values[key]};
})}};
async function main(){
 const api=create(ps,'s',{nativeSelection:true});
 documentCount=0;const noDocReads=reads;
 for(let i=0;i<20;i++)assert.deepEqual(await api.selectionContextFresh(),{session:'s',document_id:null,layer_ids:[],kind:'none',mask:0});
 assert.equal(reads-noDocReads,20);await assert.rejects(api.capture(),/No active document/);
 documentCount=1;closedDuringRead=true;await assert.rejects(api.selectionContextFresh(),/Native selection unavailable/);closedDuringRead=false;
 assert.equal((await api.capture()).active_layer_id,2);
 const first=await api.selectionContextFresh();assert.equal(first.kind,'text');assert.equal(first.mask,15);assert.equal(first.quick_mask,127);assert.equal(first.read_scope,'bounded-tree');assert.equal(modals,0);
 raw[1].layerLocking.protectPosition=true;assert.equal((await api.selectionContextFresh()).locked,true);raw[1].layerLocking.protectPosition=false;
 selected=[1,2];assert.equal((await api.selectionContextFresh()).mask,10);
 malformed=true;await assert.rejects(api.selectionContextNative(null,true),/Incomplete/);malformed=false;
 selected=[2];let ticks=0;await assert.rejects(api.selectionContextFresh(async()=>{if(++ticks===6)changed=true;}),/changed|membership/);changed=false;
 // Compare the native scalar adapter with the unchanged DOM algorithm.
 let comparisons=0;
 for(let bg=-1;bg<6;bg++){
  raw.splice(0,raw.length,...Array.from({length:6},(_,i)=>({layerID:100+i,parentLayerID:-1,itemIndex:6-i,layerKind:1,background:i===bg,
    layerSection:{_value:'layerSectionContent'},layerLocking:{protectAll:false,protectPosition:false}})));
  // A native Background is required at the bottom; malformed positions fail closed.
  if(bg>=0 && bg!==5){await assert.rejects(api.selectionContextFresh(),/background/);continue;}
  const dom=raw.map(x=>({id:x.layerID,kind:K.NORMAL,isBackgroundLayer:x.background}));
  const doc={id:9,layers:dom,mode:M.RGB,bitsPerChannel:8};
  const reference=create({...ps,app:{documents:[doc],activeDocument:doc}},'s');
  for(let bits=1;bits<64;bits++){
   selected=raw.filter((_,i)=>bits&(1<<i)).map(x=>x.layerID);doc.activeLayers=dom.filter(x=>selected.includes(x.id));
   const native=await api.selectionContextFresh(),expected=reference.selectionContext();for(const key of ['read_path','read_scope','read_fallback'])delete native[key];assert.deepEqual(native,expected);comparisons++;
  }
 }
 // Full parent structure and ancestor lock checks survive native adaptation.
 raw.splice(0,raw.length,
  {layerID:20,parentLayerID:-1,itemIndex:4,layerKind:7,layerSection:{_value:'layerSectionStart'},layerLocking:{protectAll:true,protectPosition:false}},
  {layerID:21,parentLayerID:20,itemIndex:3,layerKind:1,layerSection:{_value:'layerSectionContent'},layerLocking:{protectAll:false,protectPosition:false}},
  {itemIndex:2,layerSection:{_value:'layerSectionEnd'}},
  {layerID:22,parentLayerID:-1,itemIndex:1,layerKind:1,layerSection:{_value:'layerSectionContent'},layerLocking:{protectAll:false,protectPosition:false}});
 selected=[21];assert.equal((await api.selectionContextFresh()).locked,true);assert.equal((await api.selectionContextFresh()).quick_mask,0);
 raw[1].parentLayerID=-1;await assert.rejects(api.selectionContextFresh(),/membership/);
 const sentinel=Error('new menu');await assert.rejects(api.selectionContextFresh(async()=>{throw sentinel;}),e=>e===sentinel);
 assert.equal(modals,0);assert.ok(reads>0);assert.equal(comparisons,126);console.log('PASS native 24.2 scalar selection: no host DOM/modal, locks, types, sorting, fresh identity and cancellation; malformed data rejected');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
