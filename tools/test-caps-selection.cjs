const assert=require('node:assert/strict');
const create=require('../uxp/offline-probe/labels.js');
let selected=[3],active=3,writes=0;
const nodes=[1,2,3,4,5].map(id=>({id,kind:'pixel',allLocked:false,positionLocked:false,parent:null}));
const doc={id:1,layers:nodes,mode:'RGB',bitsPerChannel:8,get activeLayers(){return nodes.filter(l=>selected.includes(l.id));}};
const ps={app:{documents:[doc],activeDocument:doc},constants:{LayerKind:{NORMAL:'pixel',GROUP:'group'},DocumentMode:{RGB:'RGB'},BitsPerChannelType:{EIGHT:8}},
 core:{executeAsModal:async fn=>fn({isCancelled:false,hostControl:{suspendHistory:()=>{throw Error('Selection must not create history');}}})},
 action:{batchPlay:async list=>list.map(d=>{
  if(d._obj==='get')return {layerID:active};
  assert.equal(d._obj,'select');assert.equal(d.makeVisible,false);assert.equal(d._options.dialogOptions,'dontDisplay');writes++;
  if(d._target[0]._id){active=d._target[0]._id;selected=[active];return {};}
  const up=d._target[0]._value==='forwardEnum',indices=selected.map(id=>nodes.findIndex(l=>l.id===id));
  const i=up?Math.min(...indices):Math.max(...indices),next=nodes[(i+(up?-1:1)+nodes.length)%nodes.length];
  if(next){active=next.id;selected=d.selectionModifier?[...new Set([...selected,active])]:[active];}
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
 console.log('Caps single selection, additive Shift selection, reverse direction, multi-to-single and stale-target tests passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
