const assert=require('node:assert/strict'),create=require('../uxp/offline-probe/labels.js');
async function main(){
 let reads=[],bad=false,rollbacks=0,changed=false;
 const a={id:30,kind:'pixel'},b={id:31,kind:'pixel'},outer={id:90,kind:'group',layers:[]},inner={id:91,kind:'group',parent:outer,layers:[a,b]};
 outer.layers=[inner];a.parent=inner;b.parent=inner;
 const unrelated={id:92,kind:'group',get layers(){throw Error('Unrelated subtree must not be read');}};
 const doc={id:12,layers:[outer,unrelated],activeLayers:[a,b]},colors=new Map([[30,'blue'],[31,'blue'],[90,'red'],[91,'none']]);
 const ps={constants:{LayerKind:{NORMAL:'pixel',GROUP:'group'}},app:{documents:[doc],activeDocument:doc},action:{async batchPlay(commands){
  return commands.map(c=>{
   if(c._obj==='set'){for(const l of doc.activeLayers)colors.set(l.id,c.to.color._value);return {};}
   if(c._target[0]._property==='layerID')return {layerID:doc.activeLayers[0].id};
   const id=c._target[1]._id;
   if(id>=90 && c._options?.dialogOptions==='dontDisplay'){reads.push(id);assert.equal(c._target[2]._id,12);if(changed)doc.activeLayers=[b];if(bad)return {_obj:'error'};}
   return {color:{_value:colors.get(id)}};
  });
 }},core:{async executeAsModal(fn){return fn({hostControl:{suspendHistory:async()=>1,resumeHistory:async(id,commit)=>{if(!commit)rollbacks++;}}});}}};
 const api=create(ps,'session');
 async function clear(){return api.setLabel({target:await api.capture(),color:'none',expires_at_ms:Date.now()+10000});}
 assert.equal((await clear()).inherited,2);assert.deepEqual(reads,[91,90]);
 reads=[];assert.equal((await clear()).inherited,2);assert.deepEqual(reads,[91,90],'No cache across requests');
 colors.set(91,'blue');reads=[];assert.equal((await clear()).inherited,2);assert.deepEqual(reads,[91],'Stop at nearest colored ancestor');
 colors.set(91,'none');colors.set(90,'none');reads=[];assert.equal((await clear()).inherited,0);assert.deepEqual(reads,[91,90]);
 doc.activeLayers=[outer,a];reads=[];colors.set(90,'blue');colors.set(91,'none');assert.equal((await clear()).inherited,0);assert.deepEqual(reads,[91,90],'Selected parent is read after its own color was cleared');
 doc.activeLayers=[outer];reads=[];assert.equal((await clear()).inherited,0);assert.deepEqual(reads,[],'Root target reads no unrelated group');
 doc.activeLayers=[a];bad=true;await assert.rejects(clear(),/Parent label readback/);assert.equal(rollbacks,1);bad=false;
 changed=true;await assert.rejects(clear(),/target changed/);assert.equal(rollbacks,2);changed=false;
 doc.activeLayers=[a];outer.parent=inner;await assert.rejects(clear(),/parent chain/);assert.equal(rollbacks,3);delete outer.parent;
 doc.activeLayers=[a];const before=rollbacks;ps.core.executeAsModal=async fn=>fn({hostControl:{suspendHistory:async()=>1,resumeHistory:async(id,commit)=>{if(!commit)throw Error('rollback unknown');}}});
 bad=true;await assert.rejects(clear(),e=>e.resultUnknown===true);assert.equal(rollbacks,before);
 console.log('PASS label inheritance: selected ancestors only, shared cache, colored ancestor, parent+child clear, root, fresh reads, target change, error rollback and unknown');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
