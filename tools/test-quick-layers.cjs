const assert=require('node:assert/strict');
const create=require('../uxp/offline-probe/labels.js');
const k={NORMAL:'pixel',GROUP:'group',SOLIDFILL:'fill',CURVES:'curves',HUESATURATION:'hue',COLORBALANCE:'balance',BLACKANDWHITE:'bw'};
const doc={id:1,mode:'RGB',bitsPerChannel:8,layers:[{id:1,kind:'pixel'},{id:2,kind:'pixel'}]};
doc.activeLayers=[doc.layers[0]];let next=3,writes=0,histories=0,rollbacks=0,wrongKind=false,consumeEmpty=true;
const ps={constants:{LayerKind:k,DocumentMode:{RGB:'RGB',GRAYSCALE:'gray'},BitsPerChannelType:{EIGHT:8,SIXTEEN:16},ElementPlacement:{PLACEBEFORE:'before'}},
app:{documents:[doc],activeDocument:doc,foregroundColor:{rgb:{red:12,green:34,blue:56}}},
action:{batchPlay:async list=>list.map(d=>{
  if(d._obj==='get')return {layerID:doc.activeLayers[0].id};
  writes++;
  if(d._target[0]._ref==='layer') {
    assert.equal(d.using,undefined);assert.equal(d._options.dialogOptions,'dontDisplay');
    const layer={id:next++,kind:'pixel',name:'Layer '+(next-1)};
    Object.defineProperty(layer,'move',{value:async(anchor,placement)=>{
      assert.equal(placement,'before');doc.layers=doc.layers.filter(x=>x.id!==layer.id);
      doc.layers.splice(doc.layers.indexOf(anchor),0,layer);
    }});
    doc.layers.unshift(layer);doc.activeLayers=[layer];return {};
  }
  const type=d.using.type._obj;
  const kind={solidColorLayer:'fill',curves:'curves',hueSaturation:'hue',colorBalance:'balance',blackAndWhite:'bw'}[type];
  assert.equal(d._options.dialogOptions,'dontDisplay');
  if(type==='solidColorLayer')assert.deepEqual(d.using.type.color,{_obj:'RGBColor',red:12,grain:34,blue:56});
  if(consumeEmpty)doc.layers=doc.layers.filter(x=>x.id!==doc.activeLayers[0].id);
  const layer={id:next++,kind:wrongKind?'pixel':kind};doc.layers.unshift(layer);doc.activeLayers=[layer];return {};
})},core:{executeAsModal:async f=>{
  const snapshot=structuredClone({layers:doc.layers,active:doc.activeLayers});
  return f({isCancelled:false,hostControl:{suspendHistory:async()=>{histories++;return 1;},resumeHistory:async(id,commit)=>{
    if(!commit){rollbacks++;doc.layers=snapshot.layers;doc.activeLayers=snapshot.active;}
  }}});
}}};
doc.createLayer=async()=>{writes++;const l={id:next++,kind:'pixel'};Object.defineProperty(l,'delete',{value:async()=>{doc.layers=doc.layers.filter(x=>x.id!==l.id);}});doc.layers.unshift(l);doc.activeLayers=[l];return l;};
doc.createLayerGroup=async({fromLayers})=>{writes++;const l={id:next++,kind:'group',layers:[...fromLayers]};doc.layers=doc.layers.filter(x=>!fromLayers.includes(x));doc.layers.unshift(l);doc.activeLayers=[l];return l;};
const api=create(ps,'s');
async function run(command,target=null){return api.setLabel({command,target:target || await api.capture(),expires_at_ms:Date.now()+5000});}
async function main(){
  assert.equal(api.selectionContext().quick_mask,127);
  // A middle/bottom anchor must not turn into a new topmost layer; retain
  // Photoshop's generated name instead of a fixed plugin translation.
  const anchor=doc.layers[1],originalIds=doc.layers.map(x=>x.id);doc.activeLayers=[anchor];
  const blank=await run('layer.new'),created=doc.activeLayers[0];
  assert.equal(blank.layer_id,created.id);assert.equal(created.name,'Layer 3');
  assert.equal(doc.layers.indexOf(created)+1,doc.layers.indexOf(anchor));
  assert.deepEqual(doc.layers.filter(x=>x!==created).map(x=>x.id),originalIds);
  for(const command of ['layer.new','layer.solid','adjustment.curves','adjustment.hueSaturation','adjustment.colorBalance','adjustment.blackWhite']){
    const ids=doc.layers.map(x=>x.id);
    assert.equal((await run(command)).verified,true);
    assert.equal(doc.layers.length,ids.length+1);assert.ok(ids.every(id=>doc.layers.some(x=>x.id===id)));
  }
  consumeEmpty=false;const retainedIds=doc.layers.map(x=>x.id);await run('layer.solid');
  assert.equal(doc.layers.length,retainedIds.length+1);assert.ok(retainedIds.every(id=>doc.layers.some(x=>x.id===id)));
  doc.activeLayers=[doc.layers[0],doc.layers[1]];const chosen=doc.activeLayers.map(x=>x.id).sort((a,b)=>a-b);
  const group=await run('layer.group');assert.equal(group.count,2);assert.deepEqual(doc.activeLayers[0].layers.map(x=>x.id).sort((a,b)=>a-b),chosen);
  const target=await api.capture(),before=writes;doc.activeLayers=[doc.layers[1]];
  await assert.rejects(run('layer.new',target),/target changed/);assert.equal(writes,before);
  doc.activeLayers[0].isBackgroundLayer=true;assert.equal(api.selectionContext().quick_mask & 4,0);
  const h=histories;await assert.rejects(run('layer.group'),/当前文档/);assert.equal(histories,h);assert.equal(writes,before);
  doc.mode='gray';assert.equal(api.selectionContext().quick_mask,11);await assert.rejects(run('adjustment.blackWhite'),/当前文档/);
  doc.mode='RGB';doc.bitsPerChannel=32;assert.equal(api.selectionContext().quick_mask,3);
  doc.bitsPerChannel=8;wrongKind=true;const count=doc.layers.length;
  await assert.rejects(run('adjustment.curves'),/核验失败/);assert.equal(doc.layers.length,count);assert.equal(rollbacks,1);
  console.log('PASS seven commands, RGB foreground, exact group membership, target/eligibility before history, failed readback rollback');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
