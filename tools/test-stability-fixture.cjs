const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('uxp/offline-probe/labels.js','utf8');
const start=source.indexOf('function createStabilityFixture('),end=source.indexOf('\n// Session-local native paint clipboard.',start);
const context={};vm.createContext(context);vm.runInContext(source.slice(start,end)+';this.create=createStabilityFixture;',context);
const original={id:1,activeHistoryState:{id:10},activeLayers:[{id:5}]},docs=[original];let active=original,next=100,closed=[],replaceStarter=false;
const ps={app:{documents:docs,get activeDocument(){return active;},set activeDocument(v){active=v;},async createDocument(){
 const doc={id:2,layers:[{id:++next}],activeHistoryState:{id:20},historyStates:[{id:20}],async closeWithoutSaving(){closed.push(this.id);docs.splice(docs.indexOf(this),1);active=docs[0];}};
 doc.activeLayers=[doc.layers[0]];docs.push(doc);active=doc;return doc;
}},core:{executeAsModal:async fn=>fn({})},action:{async batchPlay(commands){return commands.map(c=>{
 if(c._obj==='make'){const l={id:++next};
  if(replaceStarter && c._target[0]._ref==='contentLayer' && active.layers.length===1)active.layers[0]=l;
  else active.layers.unshift(l);
  active.activeLayers=[l];active.activeHistoryState={id:++next};active.historyStates.push(active.activeHistoryState);}
 if(c._obj==='select'){active.activeLayers=[active.layers.find(l=>l.id===c._target[0]._id)];}
 return {};
});}}};
const docTarget=()=>({session:'s',document_ids:docs.map(d=>d.id),active_document_id:active.id});
const capture=async()=>({session:'s',document_id:active.id,layer_ids:active.activeLayers.map(l=>l.id),active_layer_id:active.activeLayers[0].id});
const f=context.create(ps,'s',capture,docTarget),run='a'.repeat(32);
const req=step=>({stability_run:run,test_step:step,target:docTarget(),expires_at_ms:Date.now()+10000});
(async()=>{
 await assert.rejects(f.execute({...req('fixture'),test_layers:301}),/bounded fixture size/);assert.equal(docs.length,1);
 await f.execute(req('fixture'));assert.equal(docs.length,2);await f.read(run);
 await assert.rejects(f.execute({...req('select-root'),test_index:999}),/bounded root selection/);
 await f.execute({...req('select-root'),test_index:0});await f.read(run);
 await assert.rejects(f.execute({...req('undo'),restore_history:999}),/checkpoint/);
 await assert.rejects(f.execute(req('arbitrary')),/Unknown/);
 active=original;await assert.rejects(f.read(run),/document changed/);await assert.rejects(f.execute(req('finish')),/document changed/);assert.deepEqual(closed,[]);
 active=docs[1];original.activeHistoryState={id:11};await assert.rejects(f.execute(req('finish')),/Original documents changed/);original.activeHistoryState={id:10};
 const checkpoint=active.activeHistoryState;active.activeHistoryState={id:999};await assert.rejects(f.read(run),/selection\/history changed/);active.activeHistoryState=checkpoint;
 await assert.rejects(f.read('b'.repeat(32)),/ownership/);
 const restarted=context.create(ps,'new',capture,docTarget);await assert.rejects(restarted.execute(req('finish')),/ownership/);
 await f.execute(req('finish'));assert.deepEqual(closed,[2]);assert.equal(active,original);assert.equal(original.activeHistoryState.id,10);
 for(const replaces of [false,true])for(const count of [4,100,300]){
  replaceStarter=replaces;await f.execute({...req('fixture'),test_layers:count});
  assert.equal((await f.read(run)).layer_count,count,'Native replacement must not skew the requested actual size');
  await f.execute(req('finish'));assert.equal(active,original);
 }
 console.log('PASS owned fixture: changed original/selection/document/session rejected; exact one-undo checkpoint; only owned document closed');
})().catch(e=>{console.error(e);process.exitCode=1;});
