const assert=require('node:assert/strict');
const create=require('../uxp/offline-probe/labels.js');
const k={NORMAL:'pixel',GROUP:'group',SOLIDFILL:'fill',CURVES:'curves',HUESATURATION:'hue',COLORBALANCE:'balance',BLACKANDWHITE:'bw'};
const doc={id:1,mode:'RGB',bitsPerChannel:8,layers:[{id:1,kind:'pixel'},{id:2,kind:'pixel'}]};
doc.activeLayers=[doc.layers[0]];let next=3,writes=0,histories=0,rollbacks=0,wrongKind=false,consumeEmpty=true;
const ps={constants:{LayerKind:k,DocumentMode:{RGB:'RGB',GRAYSCALE:'gray'},BitsPerChannelType:{EIGHT:8,SIXTEEN:16},ElementPlacement:{PLACEBEFORE:'before',PLACEINSIDE:'inside'}},
app:{documents:[doc],activeDocument:doc,foregroundColor:{rgb:{red:12,green:34,blue:56}}},
action:{batchPlay:async list=>list.map(d=>{
  if(d._obj==='get')return {layerID:doc.activeLayers[0].id};
  writes++;
  if(d._target[0]._ref==='layer') {
    assert.equal(d.using,undefined);assert.equal(d._options.dialogOptions,'dontDisplay');
    const layer=attach({id:next++,kind:'pixel',name:'Layer '+(next-1)});
    doc.layers.unshift(layer);doc.activeLayers=[layer];return {};
  }
  assert.equal(d.using.name,undefined);
  const type=d.using.type._obj;
  const kind={solidColorLayer:'fill',curves:'curves',hueSaturation:'hue',colorBalance:'balance',blackAndWhite:'bw'}[type];
  assert.equal(d._options.dialogOptions,'dontDisplay');
  if(type==='solidColorLayer')assert.deepEqual(d.using.type.color,{_obj:'RGBColor',red:12,grain:34,blue:56});
  if(consumeEmpty)remove(doc.activeLayers[0]);
  const layer=attach({id:next++,kind:wrongKind?'pixel':kind,name:type+' '+next});doc.layers.unshift(layer);doc.activeLayers=[layer];return {};
})},core:{executeAsModal:async f=>{
  const snapshot=structuredClone({layers:doc.layers,active:doc.activeLayers});
  return f({isCancelled:false,hostControl:{suspendHistory:async()=>{histories++;return 1;},resumeHistory:async(id,commit)=>{
    if(!commit){rollbacks++;doc.layers=snapshot.layers;doc.activeLayers=snapshot.active;}
  }}});
}}};
let badMove=false;
function remove(layer) {const layers=layer.parent?layer.parent.layers:doc.layers;const i=layers.indexOf(layer);assert.ok(i>=0);layers.splice(i,1);}
function attach(layer) {
  Object.defineProperty(layer,'move',{value:async(anchor,placement)=>{
    if(badMove)return;
    assert.ok(['before','inside'].includes(placement));remove(layer);
    layer.parent=placement==='inside'?anchor:anchor.parent;
    const layers=layer.parent?layer.parent.layers:doc.layers;
    layers.splice(placement==='inside'?0:layers.indexOf(anchor),0,layer);
  }});
  Object.defineProperty(layer,'delete',{value:async()=>remove(layer)});
  return layer;
}
doc.createLayer=async()=>{writes++;const l=attach({id:next++,kind:'pixel'});doc.layers.unshift(l);doc.activeLayers=[l];return l;};
doc.createLayerGroup=async({name,fromLayers})=>{assert.equal(name,undefined);writes++;for(const layer of fromLayers)remove(layer);const l={id:next++,kind:'group',layers:[...fromLayers]};for(const child of l.layers)child.parent=l;doc.layers.unshift(l);doc.activeLayers=[l];return l;};
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
  wrongKind=false;
  function fixture(caseName) {
    const upper=attach({id:200,kind:'pixel'}),middle=attach({id:201,kind:'pixel'}),lower=attach({id:202,kind:'pixel'});
    doc.layers=[upper,middle,lower];doc.activeLayers=caseName==='multi-focus-lower'?[lower,middle]:[middle];
    if(caseName.startsWith('group')) {
      const group={id:210,kind:'group',layers:caseName==='group-empty'?[]:[upper,middle,lower]};
      for(const child of group.layers)child.parent=group;
      doc.layers=[attach({id:220,kind:'pixel'}),group,attach({id:221,kind:'pixel'})];
      doc.activeLayers=[caseName==='group-child'?middle:group];
    }
    return doc.activeLayers[0];
  }
  const flatten=layers=>layers.flatMap(layer=>[layer.id,...(layer.kind==='group'?flatten(layer.layers):[])]);
  let placementChecks=0;
  for(const caseName of ['root-middle','group-child','group-itself','group-empty','multi-focus-lower']) {
    for(const command of ['layer.new','layer.solid','adjustment.curves','adjustment.hueSaturation','adjustment.colorBalance','adjustment.blackWhite']) {
      const anchor=fixture(caseName),ids=flatten(doc.layers);
      const inside=command!=='layer.new' && anchor.kind==='group';
      const parent=inside?anchor:anchor.parent;
      const originalSiblings=(parent?parent.layers:doc.layers).map(l=>l.id);
      const result=await run(command),made=doc.activeLayers[0];
      assert.equal(result.layer_id,made.id);assert.equal(made.parent,parent);
      const siblings=(parent?parent.layers:doc.layers).map(l=>l.id);
      if(inside)assert.equal(siblings[0],made.id);
      else assert.equal(siblings.indexOf(made.id)+1,siblings.indexOf(anchor.id));
      assert.deepEqual(siblings.filter(id=>id!==made.id),originalSiblings);
      assert.deepEqual(flatten(doc.layers).filter(id=>id!==made.id),ids);
      placementChecks++;
    }
  }
  consumeEmpty=false;const retainedAnchor=fixture('group-child'),retainedTree=flatten(doc.layers);
  await run('adjustment.curves');assert.equal(doc.activeLayers[0].parent,retainedAnchor.parent);
  assert.deepEqual(flatten(doc.layers).filter(id=>id!==doc.activeLayers[0].id),retainedTree);
  const failedAnchor=fixture('root-middle'),originalTree=flatten(doc.layers),r0=rollbacks;
  badMove=true;await assert.rejects(run('adjustment.curves'),/位置核验失败/);badMove=false;
  assert.deepEqual(flatten(doc.layers),originalTree);assert.equal(rollbacks,r0+1);
  console.log('PASS '+placementChecks+' creation placements, native group-inside/blank-outside, multi-focus, consumed/retained placeholder, native naming descriptors, failed move rollback');
  console.log('PASS seven commands, RGB foreground, exact group membership, target/eligibility before history, failed readback rollback');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
