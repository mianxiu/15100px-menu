const assert = require('node:assert/strict');
const create = require('../uxp/offline-probe/labels.js');
async function main() {
  let color = 'none', sets = 0, rollback = 0, cancelled = false, mismatch = false, historyStarts = 0;
  const doc = {id:12,activeLayers:[{id:30,kind:'pixel'},{id:31,kind:'pixel'}]};
  doc.layers=doc.activeLayers;
  const ps = {constants:{LayerKind:{NORMAL:'pixel',GROUP:'group'}},app:{documents:[doc],activeDocument:doc}, action:{batchPlay:async commands => commands.map(c=>{
    if(c._obj==='set') {sets++;color=c.to.color._value;return {};}
    if(c._target[0]._property==='layerID') return {layerID:30};
    return {color:{_value:mismatch?'none':color}};
  })},core:{executeAsModal:async fn=>fn({isCancelled:cancelled,hostControl:{
    suspendHistory:async()=>{historyStarts++;return 1;},resumeHistory:async(id,commit)=>{if(!commit)rollback++;}
  }})}};
  const api=create(ps,'session'); const target=await api.capture();
  const request={target,color:'red',expires_at_ms:Date.now()+10000};
  await assert.rejects(api.setLabel({...request,target:{...target,session:'old'}}));
  await assert.rejects(api.setLabel({...request,target:{...target,document_id:99}}));
  await assert.rejects(api.setLabel({...request,target:{...target,layer_ids:[30]}}));
  await assert.rejects(api.setLabel({...request,expires_at_ms:0}));
  cancelled=true; await assert.rejects(api.setLabel(request)); cancelled=false;
  assert.equal(sets,0);
  doc.activeLayers[1].isBackgroundLayer=true;
  for(const color of ['red','none']) await assert.rejects(api.setLabel({...request,color}),/背景图层.*先解锁/);
  assert.equal(sets,0);assert.equal(historyStarts,0);
  doc.activeLayers=[{id:30,isBackgroundLayer:true}];
  await assert.rejects(api.setLabel({...request,target:{...target,layer_ids:[30]}}),/背景图层.*先解锁/);
  assert.equal(sets,0);assert.equal(historyStarts,0);
  doc.activeLayers=[{id:30,kind:'pixel'},{id:31,kind:'pixel'}];
  assert.equal((await api.setLabel(request)).count,2);
  assert.equal((await api.setLabel({...request,color:'none'})).color,'none');
  // The menu receives UXP host metadata; the Photoshop DOM version may be absent.
  delete ps.app.version;
  const modern=create(ps,'session',{hostVersion:'25.2.0'});
  for(const color of ['seafoam','indigo','magenta','fuchsia'])assert.equal((await modern.setLabel({...request,color})).color,color);
  for(const version of ['24.0.1','25.0','25.1','25.1.9',undefined,'','unknown']) {
    const old=create(ps,'session',{hostVersion:version});const before=sets;
    for(const color of ['seafoam','indigo','magenta','fuchsia'])await assert.rejects(old.setLabel({...request,color}),/25.2/);
    assert.equal(sets,before,'Unsupported host must fail before writes');
  }
  ps.app.version='24.0.1';
  for(const version of ['25.2','25.10.0','26.0.0','27.0.0']) {
    const current=create(ps,'session',{hostVersion:version});
    assert.equal(current.extendedLabelColors,true);
    for(const color of ['seafoam','indigo','magenta','fuchsia'])assert.equal((await current.setLabel({...request,color})).color,color);
  }
  mismatch=true; await assert.rejects(api.setLabel(request)); assert.equal(rollback,1);
  ps.core.executeAsModal=async fn=>fn({hostControl:{suspendHistory:async()=>1,resumeHistory:async(id,commit)=>{if(!commit)throw Error('rollback failed');}}});
  await assert.rejects(api.setLabel(request),error=>error.resultUnknown===true);
  console.log('PASS: session/document/selection/expiry/cancel protections; multi-label/clear/readback rollback');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
