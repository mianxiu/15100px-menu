const assert=require('node:assert/strict'),create=require('../uxp/offline-probe/labels.js');
async function main(){
 let serial=100,history=0,rollbacks=0,sets=0,bad=false,rollbackFail=false;
 const pixel=id=>({id,kind:'pixel',parent:null});
 const doc={id:1,layers:[],activeLayers:[],mode:'rgb',bitsPerChannel:8};
 const ps={app:{documents:[doc],activeDocument:doc},constants:{LayerKind:{NORMAL:'pixel',GROUP:'group',SMARTOBJECT:'smart'},DocumentMode:{RGB:'rgb'},BitsPerChannelType:{EIGHT:8,SIXTEEN:16}},
 action:{batchPlay:async descriptors=>{
   if(descriptors[0]._obj==='get')return [{layerID:doc.activeLayers.at(-1).id}];
   assert.equal(descriptors.length,1);assert.equal(descriptors[0]._obj,'newPlacedLayer');sets++;
   const parent=doc.activeLayers[0].parent,list=parent?parent.layers:doc.layers,ids=doc.activeLayers.map(l=>l.id),index=list.findIndex(l=>ids.includes(l.id));
   const result={id:++serial,kind:bad?'pixel':'smart',parent};
   const remaining=list.filter(l=>!ids.includes(l.id));remaining.splice(index,0,result);
   if(parent)parent.layers=remaining;else doc.layers=remaining;doc.activeLayers=[result];return [{}];
 }},core:{executeAsModal:async fn=>{
   const before=doc.layers.slice(),selected=doc.activeLayers.slice(),groups=doc.layers.filter(l=>l.kind==='group').map(l=>[l,l.layers.slice()]);
   return fn({hostControl:{suspendHistory:async()=>{history++;return 1;},resumeHistory:async(id,commit)=>{
    if(!commit){rollbacks++;if(rollbackFail)throw Error('rollback uncertain');doc.layers=before;doc.activeLayers=selected;for(const [group,layers] of groups)group.layers=layers;}
   }}});
 }}};
 const api=create(ps,'s');
 const reset=()=>{doc.layers=[pixel(2),pixel(3),pixel(4)];doc.activeLayers=[doc.layers[1]];};
 const request=async()=>({command:'convertSmartObject',target:await api.capture(),expires_at_ms:Date.now()+5000});
 reset();let result=await api.setLabel(await request());assert.equal(result.verified,true);assert.equal(history,1);assert.equal(doc.activeLayers[0].kind,'smart');
 assert.deepEqual(doc.layers.filter(l=>l.kind!=='smart').map(l=>l.id),[2,4]);assert.deepEqual(result.selection_context.layer_ids,[doc.activeLayers[0].id]);
 const count=sets;result=await api.setLabel(await request());assert.equal(result.unchanged,true);assert.equal(sets,count);assert.equal(history,1);
 reset();doc.activeLayers=[doc.layers[0],doc.layers[2]];result=await api.setLabel(await request());assert.equal(result.count,2);assert.equal(doc.layers.length,2);assert.equal(doc.layers[1].id,3);
 reset();const group={id:8,kind:'group',parent:null,layers:[pixel(9),pixel(10)]};for(const child of group.layers)child.parent=group;
 doc.layers=[pixel(2),group,pixel(4)];doc.activeLayers=[group];await api.setLabel(await request());assert.deepEqual(doc.layers.filter(l=>l.kind!=='smart').map(l=>l.id),[2,4]);
 doc.layers=[group];doc.activeLayers=[group.layers[0]];await api.setLabel(await request());assert.equal(group.layers[0].kind,'smart');assert.equal(group.layers[1].id,10);
 reset();let r=await request();r.target.layer_ids=[999];let before=sets;await assert.rejects(api.setLabel(r),/target changed/);assert.equal(sets,before);
 reset();bad=true;await assert.rejects(api.setLabel(await request()),/回滚/);assert.equal(rollbacks,1);assert.equal(doc.activeLayers[0].id,3);
 rollbackFail=true;await assert.rejects(api.setLabel(await request()),e=>e.resultUnknown===true);assert.equal(rollbacks,2);
 console.log('PASS: single/multi/group/group-child Smart Object; unchanged smart; selection feedback; stale target; one history; rollback and unknown');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
