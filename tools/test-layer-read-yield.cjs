// Cold native-hint failure and long DOM loops must yield to newer work.
const assert=require('node:assert/strict');
const create=require('../uxp/offline-probe/labels.js');
async function scenario(selection){
  let reads=0,pending=false,atPending=0,native=0;
  const layers=Array.from({length:256},(_,i)=>({
    get id(){reads++;if(reads===20){pending=true;atPending=reads;}return i+1;},
    kind:'pixel',parent:null,allLocked:false,positionLocked:false,isBackgroundLayer:false
  }));
  const doc={id:10,layers,activeLayers:selection(layers)};
  const ps={app:{documents:[doc],activeDocument:doc},constants:{LayerKind:{NORMAL:'pixel',GROUP:'group'}},
    action:{batchPlay:async()=>{native++;throw Error('unsupported native hints');}}};
  const api=create(ps,'session'),stop=Error('new menu/command waiting');
  await assert.rejects(api.selectionContextFresh(async()=>{if(pending)throw stop;}),e=>e===stop);
  assert.ok(reads-atPending<=8,`old reader consumed ${reads-atPending} extra IDs before yielding`);
  // A fresh request must still return the exact original eligibility semantics.
  pending=false;const result=await api.selectionContextFresh(async()=>{});
  assert.deepEqual(result,api.selectionContext());
  return {reads,native};
}
(async()=>{
  await scenario(l=>[l[200]]);
  await scenario(l=>[l[120],l[200]]);
  await scenario(l=>l.slice(0,200));
  console.log('PASS cold fallback / multi-selection / majority selection interrupt within bounded reads; fresh eligibility unchanged');
})().catch(e=>{console.error(e);process.exitCode=1;});
