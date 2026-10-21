const assert=require('node:assert/strict');
const create=require(process.argv[2] || '../uxp/offline-probe/labels.js');
async function main(){
 const layers=[1,2,3].map(id=>({id,kind:'pixel',parent:null,allLocked:false,positionLocked:false}));
 const original={_obj:'layerEffects',scale:{_unit:'percentUnit',_value:100},dropShadow:{enabled:true,distance:{_unit:'pixelsUnit',_value:7}}};
 let selected=[1],active=1,fault='',full=0,narrow=0,writes=0,rollbacks=0,clipboard=structuredClone(original),saved,rollbackFault=false;
 const styles=new Map([[1,structuredClone(original)]]);
 const doc={id:10,layers,mode:'RGB',bitsPerChannel:8,get activeLayers(){return layers.filter(l=>selected.includes(l.id));}};
 const ps={app:{documents:[doc],activeDocument:doc},constants:{LayerKind:{NORMAL:'pixel',GROUP:'group'},DocumentMode:{RGB:'RGB'},BitsPerChannelType:{EIGHT:8}},
 core:{async executeAsModal(fn){return fn({isCancelled:false,hostControl:{async suspendHistory(){saved=structuredClone(styles);return 1;},async resumeHistory(id,commit){if(!commit){rollbacks++;if(rollbackFault)throw Error('Rollback unavailable');styles.clear();for(const [key,value] of saved)styles.set(key,value);}}}});}},
 action:{async batchPlay(commands){return commands.map(command=>{
  if(command._obj==='multiGet'){
   narrow++;assert.deepEqual(command.extendedReference,[['layerID','layerEffects']]);
   assert.equal(command.options.failOnMissingProperty,false);assert.equal(command.options.failOnMissingElement,true);
   assert.equal(command._target._ref[1]._id,10);
   if(fault==='unsupported' || fault==='both')return {_obj:'error',result:-1};
   if(fault==='throw')throw Error('Unsupported narrow read');
   if(fault==='malformed')return {};
   if(fault==='invalid-style')return {layerID:command._target._ref[0]._id,layerEffects:'invalid'};
   const id=command._target._ref[0]._id;
   return {layerID:fault==='identity'?999:id,...(styles.has(id)?{layerEffects:structuredClone(styles.get(id))}:{})};
  }
  if(command._obj==='get'){
   if(command._target[0]._property==='layerID')return {layerID:active};
   full++;const id=command._target[0]._id;assert.equal(command._target[1]._id,10);
   if(fault==='both')return {_obj:'error',result:-1};
   return {layerID:id,...(styles.has(id)?{layerEffects:structuredClone(styles.get(id))}:{}),unrelated:'not needed'};
  }
  writes++;
  if(command._obj==='copyEffects'){clipboard=structuredClone(styles.get(active));return {};}
  if(command._obj==='pasteEffects'){for(const id of selected)styles.set(id,structuredClone(clipboard));if(fault==='post-write')styles.set(selected[0],'invalid');return {};}
  assert.equal(command._obj,'set');assert.equal(command._options.dialogOptions,'display');
  assert.deepEqual(command.to,styles.get(active)||{_obj:'layerEffects',scale:{_unit:'percentUnit',_value:100}});return {};
 });}}};
 const api=create(ps,'session');
 const run=async command=>api.setLabel({command,target:await api.capture(),expires_at_ms:Date.now()+10000});
 await run('copyStyle');assert.equal(full,0);assert.equal(narrow,1);assert.deepEqual(clipboard,original);
 await run('editStyle');assert.equal(full,0);assert.deepEqual(styles.get(1),original);
 selected=[2];active=2;await assert.rejects(run('copyStyle'),/没有可复制/);await run('editStyle');assert.equal(styles.has(2),false);
 selected=[2,3];active=3;await run('pasteStyle');assert.deepEqual(styles.get(2),original);assert.deepEqual(styles.get(3),original);assert.equal(full,0);
 selected=[1];active=1;
 for(const error of ['unsupported','throw']){fault=error;const before=full;await run('copyStyle');assert.equal(full,before+1);assert.deepEqual(clipboard,original);}
 for(const error of ['identity','malformed','invalid-style']){fault=error;const before=writes,reads=full;await assert.rejects(run('copyStyle'),/readback unavailable|target changed/);assert.equal(writes,before);assert.equal(full,reads,'Corrupt identities must not fall back');}
 fault='both';{const before=writes;await assert.rejects(run('copyStyle'),/readback unavailable/);assert.equal(writes,before);}
 fault='post-write';selected=[2,3];active=3;await assert.rejects(run('pasteStyle'),/readback unavailable/);assert.equal(rollbacks,1);assert.deepEqual(styles.get(2),original);
 rollbackFault=true;await assert.rejects(run('pasteStyle'),error=>error.resultUnknown===true);
 console.log('PASS style-only reads: absent effects, intact style dialog, multi-paste, read-only compatibility fallback, identity/corruption rejection, rollback and unknown');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
