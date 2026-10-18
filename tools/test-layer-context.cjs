const assert=require('node:assert/strict');
const create=require('../uxp/offline-probe/labels.js');
const LayerKind={NORMAL:'pixel',GROUP:'group',TEXT:'text',SMARTOBJECT:'smart',SOLIDFILL:'fill',CURVES:'curves'};
const a={id:1,kind:'pixel'},b={id:2,kind:'text'},c={id:3,kind:'smart'};
const doc={id:10,layers:[a,b,c],activeLayers:[b]};
let writes=0,history=0;
const ps={constants:{LayerKind},app:{documents:[doc],activeDocument:doc},action:{batchPlay:async commands=>commands.map(d=>{
  if(d._obj!=='get'){writes++;return {};}
  return {layerID:doc.activeLayers[0].id};
})},core:{executeAsModal:async f=>f({isCancelled:false,hostControl:{suspendHistory:async()=>{history++;return 1;},resumeHistory:async()=>{}}})}};
const api=create(ps,'session');
async function main(){
  let value=api.selectionContext();assert.equal(value.kind,'text');assert.equal(value.mask,15);
  doc.activeLayers=[a];assert.equal(api.selectionContext().mask,11); // already top
  doc.activeLayers=[c];assert.equal(api.selectionContext().mask,7); // already bottom
  b.positionLocked=true;doc.activeLayers=[b];assert.equal(api.selectionContext().mask,3);
  const target=await api.capture();
  await assert.rejects(api.setLabel({target,command:'moveToTop',expires_at_ms:Date.now()+10000}),/不可排序/);
  assert.equal(writes,0);assert.equal(history,0);b.positionLocked=false;
  const bg={id:4,kind:'pixel',isBackgroundLayer:true};doc.layers.push(bg);doc.activeLayers=[bg];
  assert.equal(api.selectionContext().kind,'background');assert.equal(api.selectionContext().mask,1);
  doc.activeLayers=[b,bg];assert.equal(api.selectionContext().kind,'mixed');assert.equal(api.selectionContext().mask,0);
  doc.activeLayers=[a,b];assert.equal(api.selectionContext().mask,10); // common label and bottom, no selection rewrite
  const group={id:5,kind:'group',layers:[],parent:null};doc.layers.unshift(group);doc.activeLayers=[group];
  assert.equal(api.selectionContext().mask,10); // empty group at top
  group.layers=[a,b];a.parent=b.parent=group;group.allLocked=true;
  doc.activeLayers=[a];assert.equal(api.selectionContext().mask,3);assert.equal(api.selectionContext().locked,true);
  doc.activeLayers=[a,c];assert.equal(api.selectionContext().same_parent,false);assert.equal(api.selectionContext().mask,2);
  doc.activeLayers=[{id:9,kind:'future-unknown'}];assert.equal(api.selectionContext().mask,0);
  doc.activeLayers=[{id:8,kind:'fill'}];assert.equal(api.selectionContext().kind,'shape-fill');
  doc.activeLayers=[{id:7,kind:'curves'}];assert.equal(api.selectionContext().kind,'adjustment');
  // Shared ancestors and sibling metadata are read once per snapshot, while
  // a later snapshot must see a newly changed lock (no cross-request cache).
  const reads=new Map();
  function watched(name,raw) {return new Proxy(raw,{get(target,key){
    const id=name+'.'+String(key);reads.set(id,(reads.get(id)||0)+1);
    return Reflect.get(target,key);
  }});}
  const parentRaw={id:30,kind:'group',allLocked:false},parent=watched('parent',parentRaw);
  const first=watched('first',{id:31,kind:'pixel',parent}),second=watched('second',{id:32,kind:'pixel',parent});
  parentRaw.layers=[first,second];doc.layers=[parent];doc.activeLayers=[first];
  api.selectionContext();
  for(const [key,n] of reads)if(!key.endsWith('.id'))assert.equal(n,1,key+' should be read once');
  parentRaw.allLocked=true;
  assert.equal(api.selectionContext().locked,true);
  parentRaw.allLocked=false;doc.activeLayers=[first,second];reads.clear();
  assert.equal(api.selectionContext().locked,false);
  assert.equal(reads.get('parent.allLocked'),1);
  // Compare lazy edge checks against the original complete background filter,
  // including discontinuous multi-selection and backgrounds at every position.
  let edgeChecks=0;
  for(let bg=0;bg<6;bg++) {
    const layers=Array.from({length:6},(_,i)=>({id:100+i,kind:'pixel',isBackgroundLayer:i===bg}));
    doc.layers=layers;
    for(let bits=1;bits<64;bits++) {
      doc.activeLayers=layers.filter((_,i)=>bits&(1<<i));
      const ids=doc.activeLayers.map(l=>l.id),order=layers.filter(l=>!l.isBackgroundLayer).map(l=>l.id);
      const chosen=order.filter(id=>ids.includes(id));
      let expected=0;
      if(!(bits&(1<<bg))) {
        if(order.slice(0,ids.length).join(',')!==chosen.join(','))expected|=4;
        if(order.slice(-ids.length).join(',')!==chosen.join(','))expected|=8;
      }
      assert.equal(api.selectionContext().mask&12,expected,'background '+bg+' selection '+bits);
      assert.deepEqual(await api.selectionContextFresh(async()=>{}),api.selectionContext());
      edgeChecks++;
    }
  }
  doc.layers=Array.from({length:128},(_,i)=>({id:1000+i,kind:'fill',allLocked:i===73}));
  doc.activeLayers=doc.layers.slice();
  let checkpoints=0;
  const full=await api.selectionContextFresh(async()=>{checkpoints++;});
  assert.deepEqual(full,api.selectionContext());assert.ok(checkpoints>=96);
  const sentinel=Error('command waiting');let stopped=0;
  await assert.rejects(api.selectionContextFresh(async()=>{if(++stopped===3)throw sentinel;}),e=>e===sentinel);
  assert.equal(stopped,3);assert.equal(writes,0);assert.equal(history,0);
  let changed=false;
  await assert.rejects(api.selectionContextFresh(async()=>{if(!changed){changed=true;return;}doc.activeLayers=[doc.layers[0]];}),/context changed/);
  doc.activeLayers=doc.layers.slice();assert.deepEqual(await api.selectionContextFresh(async()=>{}),full);
  ps.app.documents=[];assert.equal(api.selectionContext().mask,0);
  console.log('PASS DOM type/selection/lock/parent; '+edgeChecks+' original/lazy edge comparisons; rejected sorting has no write/history');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
