const assert=require('node:assert/strict'),create=require('../uxp/offline-probe/labels.js');
async function main(){
 let serial=100,history=0,rollbacks=0,writes=0,failAt=0,rollbackFail=false,drift=false;
 const box={left:2,top:3,right:12,bottom:15};
 const pixel=id=>({id,kind:'pixel',boundsNoEffects:{...box}});
 const group=(id,children)=>({id,kind:'group',boundsNoEffects:{...box},layers:children});
 const doc={id:1,layers:[],activeLayers:[],mode:'rgb',bitsPerChannel:8};
 const tree=(layers,parent=null)=>layers.flatMap(l=>[{layer:l,parent},...(l.kind==='group'?tree(l.layers,l.id):[])]);
 const ps={app:{documents:[doc],activeDocument:doc},constants:{LayerKind:{NORMAL:'pixel',GROUP:'group',SMARTOBJECT:'smart'},DocumentMode:{RGB:'rgb'},BitsPerChannelType:{EIGHT:8,SIXTEEN:16}},
 action:{batchPlay:async descriptors=>{
  const results=[];
  for(const d of descriptors){
   if(d._obj==='get'){results.push({layerID:doc.activeLayers.at(-1).id});continue;}
   if(d._obj==='select'){
    assert.equal(d.makeVisible,false);assert.equal(d._target[1]._id,doc.id);
    const layer=tree(doc.layers).find(l=>l.layer.id===d._target[0]._id)?.layer;assert.ok(layer);
    doc.activeLayers=d.selectionModifier?[...doc.activeLayers.filter(l=>l.id!==layer.id),layer]:[layer];results.push({});continue;
   }
   assert.equal(d._obj,'newPlacedLayer');assert.equal(doc.activeLayers.length,1);writes++;
   if(writes===failAt){results.push({_obj:'error'});continue;}
   const old=doc.activeLayers[0],item=tree(doc.layers).find(l=>l.layer.id===old.id);
   const list=item.parent===null?doc.layers:tree(doc.layers).find(l=>l.layer.id===item.parent).layer.layers;
   const made={id:++serial,kind:'smart',boundsNoEffects:{...old.boundsNoEffects}};
   if(drift)made.boundsNoEffects.left+=3;
   list.splice(list.indexOf(old),1,made);doc.activeLayers=[made];results.push({});
  }
  return results;
 }},core:{executeAsModal:async fn=>{
  const saved=structuredClone({layers:doc.layers,active:doc.activeLayers});
  return fn({hostControl:{suspendHistory:async()=>{history++;return 1;},resumeHistory:async(id,commit)=>{
   if(!commit){rollbacks++;if(rollbackFail)throw Error('uncertain');doc.layers=saved.layers;doc.activeLayers=saved.active;}
  }}});
 }}};
 const api=create(ps,'s'),run=async target=>api.setLabel({command:'convertSmartObjectsIndividually',target:target??await api.capture(),expires_at_ms:Date.now()+5000});
 const reset=()=>{doc.layers=[pixel(2),pixel(3),pixel(4)];doc.activeLayers=[doc.layers[0],doc.layers[2]];failAt=0;drift=false;};
 reset();let result=await run();assert.equal(result.converted_count,2);assert.equal(history,1);assert.equal(doc.layers.length,3);assert.equal(doc.layers[1].id,3);assert.equal(doc.activeLayers.length,2);assert.equal(doc.activeLayers[1],doc.layers[2]);
 const n=writes,h=history;result=await run();assert.equal(result.unchanged,true);assert.equal(writes,n);assert.equal(history,h);
 reset();doc.layers[0].kind='smart';const kept=doc.layers[0].id;result=await run();assert.equal(result.converted_count,1);assert.equal(result.unchanged_count,1);assert.equal(doc.layers[0].id,kept);
 reset();let g=group(8,[pixel(9),pixel(10)]);doc.layers=[g,pixel(11)];doc.activeLayers=[g.layers[0],doc.layers[1]];result=await run();assert.equal(g.layers.length,2);assert.equal(g.layers[1].id,10);assert.equal(doc.activeLayers[0].kind,'smart');assert.equal(doc.activeLayers[1],doc.layers[1]);
 reset();g=group(8,[pixel(9),group(10,[pixel(12)])]);doc.layers=[g,pixel(11)];doc.activeLayers=[g,doc.layers[1]];await run();assert.equal(tree(doc.layers).length,2);
 reset();g=group(8,[pixel(9)]);doc.layers=[g];doc.activeLayers=[g,g.layers[0]];let old=writes;await assert.rejects(run(),/父组.*子图层/);assert.equal(writes,old);
 for(const key of ['allLocked','positionLocked','isBackgroundLayer']){reset();doc.layers[0][key]=true;old=writes;await assert.rejects(run(),/解锁/);assert.equal(writes,old);}
 reset();g=group(8,[pixel(9)]);g.allLocked=true;doc.layers=[g];doc.activeLayers=[g.layers[0]];await assert.rejects(run(),/解锁/);
 reset();const target=await api.capture();await assert.rejects(run({...target,active_layer_id:999}),/target changed/);await assert.rejects(run({...target,session:'old'}),/session/);
 await assert.rejects(api.setLabel({command:'convertSmartObjectsIndividually',target,expires_at_ms:0}),/expired/);
 reset();old=writes;failAt=writes+2;let b=rollbacks;await assert.rejects(run(),/拒绝/);assert.equal(rollbacks,b+1);assert.deepEqual(doc.layers.map(l=>l.id),[2,3,4]);assert.deepEqual(doc.activeLayers.map(l=>l.id),[2,4]);assert.equal(writes,old+2);
 reset();drift=true;b=rollbacks;await assert.rejects(run(),/位置/);assert.equal(rollbacks,b+1);assert.deepEqual(doc.layers.map(l=>l.id),[2,3,4]);
 reset();failAt=writes+2;rollbackFail=true;await assert.rejects(run(),e=>e.resultUnknown===true);
 console.log('PASS: independent Smart Objects; same/cross parent, whole group, already smart, active selection, position/order, one history, locked/ancestor/stale/expiry guards, batch rollback and unknown');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
