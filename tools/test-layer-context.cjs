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
  ps.app.documents=[];assert.equal(api.selectionContext().mask,0);
  console.log('PASS DOM type/selection/lock/parent/edge eligibility; rejected sorting has no write/history');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
