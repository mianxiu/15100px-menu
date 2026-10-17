const assert=require('node:assert/strict');
const create=require('../uxp/offline-probe/labels.js');
let selected=[3],active=3,writes=0,nativeReads=0,nativeFault=null,kindReads=0,afterWrite=null,modalContext;
const nodes=[1,2,3,4,5].map(id=>({id,kind:'pixel',allLocked:false,positionLocked:false,parent:null}));
const doc={id:1,layers:nodes,mode:'RGB',bitsPerChannel:8,get activeLayers(){return nodes.filter(l=>selected.includes(l.id));}};
const ps={app:{documents:[doc],activeDocument:doc},constants:{LayerKind:{NORMAL:'pixel',GROUP:'group'},DocumentMode:{RGB:'RGB'},BitsPerChannelType:{EIGHT:8}},
 core:{executeAsModal:async fn=>fn(modalContext={isCancelled:false,hostControl:{suspendHistory:()=>{throw Error('Selection must not create history');}}})},
 action:{batchPlay:async list=>list.map(d=>{
  if(d._obj==='get' && d._target[0]._property==='numberOfLayers')return {numberOfLayers:nativeFault==='oversize'?4097:nodes.length-(nodes.at(-1).isBackgroundLayer?1:0)};
  if(d._obj==='multiGet'){
   nativeReads++;
   assert.equal(d.extendedReference[1].index,nodes.at(-1).isBackgroundLayer?0:1);
   assert.equal(d.extendedReference[1].count,nodes.length);
   if(nativeFault==='unsupported')throw Error('Unsupported');
   if(nativeFault==='cancelled')modalContext.isCancelled=true;
   const rows=nodes.map((l,i)=>({layerID:l.id,parentLayerID:0,layerSection:{_value:'layerSectionContent'},itemIndex:nodes.length-i}));
   if(nativeFault==='incomplete')rows.pop();
   if(nativeFault==='duplicate')rows[1].layerID=rows[0].layerID;
   if(nativeFault==='parent')rows[1].parentLayerID=999;
   if(nativeFault==='index')rows[1].itemIndex=0;
   return {list:rows};
  }
  if(d._obj==='get')return {layerID:active};
  assert.equal(d._obj,'select');assert.equal(d.makeVisible,false);assert.equal(d._options.dialogOptions,'dontDisplay');writes++;
  if(d._target[0]._id){active=d._target[0]._id;selected=[active];return {};}
  const up=d._target[0]._value==='forwardEnum',indices=selected.map(id=>nodes.findIndex(l=>l.id===id));
  const i=up?Math.min(...indices):Math.max(...indices),next=nodes[(i+(up?-1:1)+nodes.length)%nodes.length];
  if(next){active=next.id;selected=d.selectionModifier?[...new Set([...selected,active])]:[active];}
  if(afterWrite)afterWrite();
  return {};
 })}};
const labels=create(ps,'test');
async function run(command){return labels.setLabel({command,target:await labels.capture(),expires_at_ms:Date.now()+1000});}
(async()=>{
 await run('extendAbove');assert.deepEqual(selected.sort(),[2,3]);
 await run('extendAbove');assert.deepEqual(selected.sort(),[1,2,3]);
 await run('extendBelow');assert.deepEqual(selected.sort(),[1,2,3,4]);assert.equal(active,4);
 await run('selectBelow');assert.deepEqual(selected,[5]);
 selected=[2,4];active=4;await run('selectAbove');assert.deepEqual(selected,[3]);
 selected=[1,2,3,4,5];active=1;await run('selectBelow');assert.deepEqual(selected,[2]);
 const frozen=await labels.capture(),before=writes;selected=[5];active=5;
 await assert.rejects(labels.setLabel({command:'extendAbove',target:frozen,expires_at_ms:Date.now()+1000}),/target changed/);assert.equal(writes,before);
 assert.deepEqual(nodes.map(l=>l.id),[1,2,3,4,5]);
 assert.equal(nativeReads,0,'Small lists retain DOM path');
 function large(background=false){nodes.splice(0,nodes.length,...Array.from({length:100},(_,i)=>({id:i+1,get kind(){kindReads++;return 'pixel';},parent:null,allLocked:false,positionLocked:false,isBackgroundLayer:background&&i===99})));selected=[50];active=50;kindReads=0;nativeReads=0;}
 for(const background of [false,true]){
  large(background);await run('selectAbove');assert.deepEqual(selected,[49]);await run('extendBelow');assert.deepEqual(selected.sort((a,b)=>a-b),[49,50]);
  assert.equal(nativeReads,4,'Native tree must validate before and after each write');
  assert.ok(kindReads<40,'Scalar path must not materialize every layer kind');
 }
 for(const fault of ['oversize','unsupported','incomplete','duplicate','parent','index']){
  large();nativeFault=fault;await run('selectAbove');assert.deepEqual(selected,[49]);assert.ok(kindReads>=200,'Malformed/unsupported scalar trees fall back to complete DOM reads');
 }
 nativeFault='cancelled';large();const writesBefore=writes;await assert.rejects(run('selectAbove'),/Cancelled/);assert.equal(writes,writesBefore);nativeFault=null;
 for(const corrupt of [()=>{[nodes[0],nodes[1]]=[nodes[1],nodes[0]];},()=>{nodes.pop();},()=>{selected=[1,2];active=1;}]){
  large();afterWrite=corrupt;await assert.rejects(run('selectAbove'),/order changed|identity changed|readback mismatch/);afterWrite=null;
 }
 console.log('Caps single selection, additive Shift selection, reverse direction, multi-to-single and stale-target tests passed');
 console.log('PASS: large/background scalar path, malformed fallback, cancellation, order/count/selection corruption detection');
})().catch(e=>{console.error(e);process.exitCode=1;});
