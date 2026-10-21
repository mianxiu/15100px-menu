const assert=require('node:assert/strict');
const create=require('../uxp/offline-probe/labels.js');
let selectionReads=0,selectionFault=null,selectError=null,ordinalErrorOnly=false,throwOrdinal=false,restoreError=false,onSelectError=null;
let selected=[3],active=3,writes=0,nativeReads=0,nativeFault=null,kindReads=0,afterWrite=null,modalContext;
const nodes=[1,2,3,4,5].map(id=>({id,kind:'pixel',allLocked:false,positionLocked:false,parent:null}));
const doc={id:1,layers:nodes,mode:'RGB',bitsPerChannel:8,get activeLayers(){return nodes.filter(l=>selected.includes(l.id));}};
const ps={app:{documents:[doc],activeDocument:doc},constants:{LayerKind:{NORMAL:'pixel',GROUP:'group'},DocumentMode:{RGB:'RGB'},BitsPerChannelType:{EIGHT:8}},
 core:{executeAsModal:async fn=>fn(modalContext={isCancelled:false,hostControl:{suspendHistory:()=>{throw Error('Selection must not create history');}}})},
 action:{batchPlay:async list=>list.map(d=>{
  if(d._obj==='get' && d._target[0]._property==='targetLayersIDs'){
   selectionReads++;if(selectionFault==='unsupported')throw Error('unsupported');
   let refs=selected.map(id=>({_ref:'layer',_id:id}));
   if(selectionFault==='missing')refs.pop();
   if(selectionFault==='duplicate')refs[1]=refs[0];
   if(selectionFault==='wrong-active')refs[0]={_ref:'layer',_id:99999};
   return {targetLayersIDs:refs};
  }
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
  if(d._obj==='select' && restoreError && d.selectionModifier && d._target[0]._id)return {_obj:'error',result:-1,message:'Restore rejected'};
  if(d._obj==='select' && selectError && (!ordinalErrorOnly || !d._target[0]._id)){
   if(onSelectError)onSelectError();
   if(throwOrdinal)throw Error('Rejected');
   return {_obj:'error',result:selectError,message:'Rejected'};
  }
  assert.equal(d._obj,'select');assert.equal(d.makeVisible,false);assert.equal(d._options.dialogOptions,'dontDisplay');writes++;
  if(d._target[0]._id){active=d._target[0]._id;selected=d.selectionModifier?[...new Set([...selected,active])]:[active];return {};}
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
 // The dedicated selector keeps small documents on DOM and batches medium
 // trees too; it must preserve full before/after validation and fresh feedback.
 nodes.push(...[6,7,8].map(id=>({id,kind:'pixel',allLocked:false,positionLocked:false,parent:null})));
 selected=[3];active=3;nativeReads=0;
 const medium=await run('selectAbove');assert.deepEqual(selected,[2]);assert.equal(nativeReads,2);
 assert.equal(medium.selection_context.layer_ids.join(','),'2');
 for(const key of ['modal_wait_ms','target_ms','before_tree_ms','select_ms','after_tree_ms','feedback_ms'])assert.ok(Number.isFinite(medium.selection_timings_ms[key]),key);
 const expiredWrites=writes;
 await assert.rejects(labels.setLabel({command:'selectAbove',target:await labels.capture(),expires_at_ms:Date.now()-1}),/expired/);assert.equal(writes,expiredWrites);
 for(const background of [false,true]){
  large(background);await run('selectAbove');assert.deepEqual(selected,[49]);await run('extendBelow');assert.deepEqual(selected.sort((a,b)=>a-b),[49,50]);
  assert.equal(nativeReads,4,'Native tree must validate before and after each write');
  assert.ok(kindReads<40,'Scalar path must not materialize every layer kind');
 }
 for(const fault of ['oversize','unsupported','incomplete','duplicate','parent','index']){
  large();nativeFault=fault;await run('selectAbove');assert.deepEqual(selected,[49]);assert.ok(kindReads>=200,'Malformed/unsupported scalar trees fall back to complete DOM reads');
 }
 large();selected=nodes.map(l=>l.id);active=50;
 const bulk=await labels.captureSelection();assert.equal(bulk.layer_ids.length,100);assert.equal(bulk.active_layer_id,50);assert.ok(selectionReads>0);
 await run('selectAbove');assert.deepEqual(selected,[49]);
 for(const fault of ['unsupported','missing','duplicate','wrong-active']){
  selected=nodes.map(l=>l.id);active=1;selectionFault=fault;
  const fallback=await labels.captureSelection();assert.equal(fallback.layer_ids.length,100);assert.equal(fallback.active_layer_id,1);
 }
 selectionFault=null;
 large();selectError=-128;const cancelledWrites=writes;
 const cancel=await run('selectAbove');assert.equal(cancel.cancelled,true);assert.equal(writes,cancelledWrites);
 selectError=-1;await assert.rejects(run('selectAbove'),/Rejected/);assert.equal(writes,cancelledWrites);selectError=null;
 for(const failure of [-128,-1,'throw']){
  large();selected=[20,50];active=50;ordinalErrorOnly=true;selectError=failure;throwOrdinal=failure==='throw';
  if(failure===-128){const value=await run('selectAbove');assert.equal(value.cancelled,true);assert.equal(value.rollback_verified,true);}
  else await assert.rejects(run('selectAbove'),/Rejected/);
  assert.deepEqual(selected.sort((a,b)=>a-b),[20,50]);assert.equal(active,50);
 }
 large();selected=[20,50];active=50;selectError=-128;throwOrdinal=false;restoreError=true;
 await assert.rejects(run('selectAbove'),error=>error.resultUnknown===true);restoreError=false;
 large();selected=[20,50];active=50;const beforeChanged=writes;
 onSelectError=()=>{selected=[11];active=11;};
 await assert.rejects(run('selectAbove'),error=>error.resultUnknown===true);
 assert.deepEqual(selected,[11]);assert.equal(writes,beforeChanged+1,'Never restore over a changed target');onSelectError=null;
 selectError=null;ordinalErrorOnly=false;
 nativeFault='cancelled';large();const writesBefore=writes;await assert.rejects(run('selectAbove'),/Cancelled/);assert.equal(writes,writesBefore);nativeFault=null;
 for(const corrupt of [()=>{[nodes[0],nodes[1]]=[nodes[1],nodes[0]];},()=>{nodes.pop();},()=>{selected=[1,2];active=1;}]){
  large();afterWrite=corrupt;await assert.rejects(run('selectAbove'),/order changed|identity changed|readback mismatch/);afterWrite=null;
 }
 // Native feedback is prepared by main.js after modal exit, never twice.
 const source=require('node:fs').readFileSync('uxp/offline-probe/labels.js','utf8'),box={};
 require('node:vm').runInNewContext(source.slice(source.indexOf('function createCapsActions('),source.indexOf('// Selected vector masks only.'))+'this.make=createCapsActions;',box);
 nodes.splice(0,nodes.length,...[1,2,3,4].map(id=>({id,kind:'pixel',parent:null,allLocked:false,positionLocked:false})));selected=[2];active=2;
 let feedbackCalls=0;
 const make=native=>box.make(ps,'test',labels.capture,()=>{feedbackCalls++;return labels.selectionContext();},async()=>({order:nodes.map(l=>l.id)}),labels.captureSelection,native);
 const nativeCaps=make(true);
 for(const command of ['selectAbove','selectBelow','extendAbove','extendBelow']){
  selected=[2];active=2;
  const value=await nativeCaps.execute({command,target:await labels.capture(),expires_at_ms:Date.now()+1000});
  assert.equal(value.selection_context,null);assert.equal(feedbackCalls,0);
 }
 selectError=-128;const nativeCancel=await nativeCaps.execute({command:'selectAbove',target:await labels.capture(),expires_at_ms:Date.now()+1000});
 assert.equal(nativeCancel.rollback_verified,true);assert.equal(nativeCancel.selection_context,null);assert.equal(feedbackCalls,0);selectError=null;
 selected=[2];active=2;const dom=await make(false).execute({command:'selectAbove',target:await labels.capture(),expires_at_ms:Date.now()+1000});
 assert.ok(dom.selection_context);assert.equal(feedbackCalls,1);
 console.log('Caps single selection, additive Shift selection, reverse direction, multi-to-single and stale-target tests passed');
 console.log('PASS: large/background scalar path, malformed fallback, cancellation, order/count/selection corruption detection');
})().catch(e=>{console.error(e);process.exitCode=1;});
