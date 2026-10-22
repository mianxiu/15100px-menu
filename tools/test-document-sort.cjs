const assert=require('node:assert/strict'),create=require('../uxp/offline-probe/labels.js');
async function main(){
 let histories=0,rollbacks=0,bad=false,unknown=false;
 const doc={id:1,layers:[],activeLayers:[],mode:'rgb',bitsPerChannel:8};
 const walk=ls=>ls.flatMap(l=>[l,...(l.layers?walk(l.layers):[])]);
 const pixel=id=>({id,kind:'pixel',parent:null,async move(anchor,placement){
  if(bad)return;
  const from=this.parent?.layers??doc.layers;from.splice(from.indexOf(this),1);
  const to=anchor.parent?.layers??doc.layers;to.splice(to.indexOf(anchor)+(placement==='after'?1:0),0,this);this.parent=anchor.parent;
 }});
 const ps={app:{documents:[doc],activeDocument:doc},constants:{LayerKind:{NORMAL:'pixel',GROUP:'group'},ElementPlacement:{PLACEBEFORE:'before',PLACEAFTER:'after'},DocumentMode:{RGB:'rgb'},BitsPerChannelType:{EIGHT:8,SIXTEEN:16}},action:{batchPlay:async ds=>ds.map(()=>({layerID:doc.activeLayers.at(-1).id}))},core:{executeAsModal:async fn=>{
  const layers=walk(doc.layers),before=doc.layers.slice(),groups=layers.filter(l=>l.layers).map(l=>[l,l.layers.slice()]),parents=layers.map(l=>[l,l.parent]);
  return fn({hostControl:{suspendHistory:async()=>++histories,resumeHistory:async(id,commit)=>{if(!commit){rollbacks++;if(unknown)throw Error('unknown');doc.layers=before;for(const [l,list] of groups)l.layers=list;for(const [l,p] of parents)l.parent=p;}}}});
 }}};
 const api=create(ps,'s');
 const reset=()=>{const group=pixel(8);group.kind='group';group.layers=[pixel(9),pixel(10),pixel(11)];for(const l of group.layers)l.parent=group;doc.layers=[pixel(2),group,pixel(3),pixel(4)];doc.activeLayers=[group.layers[1]];return group;};
 const run=async(command='moveDocumentTop',target)=>api.setLabel({command,target:target??await api.capture(),expires_at_ms:Date.now()+5000});
 let g=reset();await run();assert.deepEqual(doc.layers.map(l=>l.id),[10,2,8,3,4]);assert.deepEqual(g.layers.map(l=>l.id),[9,11]);assert.equal(doc.activeLayers[0].parent,null);assert.equal(histories,1);
 g=reset();doc.activeLayers=[g.layers[0],g.layers[2]];await run('moveDocumentBottom');assert.deepEqual(doc.layers.map(l=>l.id),[2,8,3,4,9,11]);assert.deepEqual(g.layers.map(l=>l.id),[10]);
 g=reset();doc.layers.at(-1).isBackgroundLayer=true;await run('moveDocumentBottom');assert.deepEqual(doc.layers.map(l=>l.id),[2,8,3,10,4]);
 g=reset();doc.activeLayers=[doc.layers[2]];await run();assert.deepEqual(doc.layers.map(l=>l.id),[3,2,8,4]);
 g=reset();doc.activeLayers=[g];await run('moveDocumentBottom');assert.deepEqual(doc.layers.map(l=>l.id),[2,3,4,8]);assert.deepEqual(g.layers.map(l=>l.id),[9,10,11]);
 g=reset();let n=histories;doc.activeLayers[0].positionLocked=true;await assert.rejects(run(),/解锁/);assert.equal(histories,n);
 g=reset();g.allLocked=true;await assert.rejects(run(),/解锁/);
 g=reset();doc.activeLayers=[g.layers[0],doc.layers[0]];await assert.rejects(run(),/父组/);
 g=reset();await assert.rejects(run('moveDocumentTop',{session:'s',document_id:1,active_layer_id:999,layer_ids:[999]}),/target changed/);
 g=reset();bad=true;let rb=rollbacks;await assert.rejects(run(),/回滚/);assert.equal(rollbacks,rb+1);assert.equal(g.layers[1].id,10);
 unknown=true;await assert.rejects(run(),e=>e.resultUnknown===true);
 console.log('PASS document top/bottom: nested single/multi, order, background, root, locks, cross-parent, stale, rollback and unknown');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
