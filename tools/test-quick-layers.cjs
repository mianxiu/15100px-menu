const assert=require('node:assert/strict');
const create=require('../uxp/offline-probe/labels.js');
const k={NORMAL:'pixel',GROUP:'group',SOLIDFILL:'fill',CURVES:'curves',HUESATURATION:'hue',COLORBALANCE:'balance',BLACKANDWHITE:'bw'};
const doc={id:1,mode:'RGB',bitsPerChannel:8,layers:[{id:1,kind:'pixel'},{id:2,kind:'pixel'}]};
doc.activeLayers=[doc.layers[0]];let next=3,writes=0,histories=0,rollbacks=0,wrongKind=false,consumeEmpty=true;
let nativeReads=0,nativeFault=null,modalContext=null;
function nativeRows() {
  const rows=[];
  function walk(layers,parent=0) {for(const layer of layers) {
    rows.push({layerID:layer.id,parentLayerID:parent,layerSection:{_value:layer.kind==='group'?'layerSectionStart':'layerSectionContent'}});
    if(layer.kind==='group'){walk(layer.layers,layer.id);rows.push({layerSection:{_value:'layerSectionEnd'}});}
  }}walk(doc.layers);
  rows.forEach((row,i)=>row.itemIndex=rows.length-i);return rows;
}
const ps={constants:{LayerKind:k,DocumentMode:{RGB:'RGB',GRAYSCALE:'gray'},BitsPerChannelType:{EIGHT:8,SIXTEEN:16},ElementPlacement:{PLACEBEFORE:'before',PLACEINSIDE:'inside'}},
app:{documents:[doc],activeDocument:doc,foregroundColor:{rgb:{red:12,green:34,blue:56}}},
action:{batchPlay:async list=>list.map(d=>{
  if(d._obj==='get' && d._target[0]._property==='numberOfLayers') {
    nativeReads++;return {numberOfLayers:nativeFault==='oversize'?4097:nativeRows().length-(doc.layers.at(-1).isBackgroundLayer?1:0)};
  }
  if(d._obj==='multiGet') {
    nativeReads++;const rows=nativeRows();
    assert.deepEqual(d.extendedReference[0],['layerID','parentLayerID','layerSection','itemIndex']);
    assert.equal(d.extendedReference[1].index,doc.layers.at(-1).isBackgroundLayer?0:1);
    assert.equal(d.extendedReference[1].count,rows.length);
    if(nativeFault==='unsupported')throw Error('Host unsupported');
    if(nativeFault==='incomplete')rows.pop();
    if(nativeFault==='duplicate')rows[1].layerID=rows[0].layerID;
    if(nativeFault==='parent')rows[1].parentLayerID=987;
    if(nativeFault==='index')rows[1].itemIndex=rows[0].itemIndex;
    if(nativeFault==='index-base')rows.forEach(row=>row.itemIndex--);
    if(nativeFault==='section')rows[1].layerSection._value='unknown';
    if(nativeFault==='unbalanced')rows[1].layerSection._value='layerSectionEnd';
    if(nativeFault==='prefix') [rows[0].layerID,rows[1].layerID]=[rows[1].layerID,rows[0].layerID];
    if(nativeFault==='stale')doc.activeLayers=[doc.layers[0]];
    if(nativeFault==='cancelled')modalContext.isCancelled=true;
    return {list:rows};
  }
  if(d._obj==='get') {
    const key=d._target[0]._property;
    return {[key]:{numberOfDocuments:1,documentID:doc.id,targetLayersIDs:doc.activeLayers.map(l=>({_ref:'layer',_id:l.id})),layerID:doc.activeLayers[0].id}[key]};
  }
  writes++;
  if(d._target[0]._ref==='layer') {
    assert.equal(d.using,undefined);assert.equal(d._options.dialogOptions,'dontDisplay');
    const layer=attach({id:next++,kind:'pixel',name:'Layer '+(next-1)});
    const anchor=doc.activeLayers[0],parent=anchor.kind==='group'?anchor:anchor.parent;
    const siblings=parent?parent.layers:doc.layers;
    layer.parent=parent;
    if(badMove){doc.layers.unshift(layer);layer.parent=null;}
    else siblings.splice(anchor.kind==='group'?0:siblings.indexOf(anchor),0,layer);
    doc.activeLayers=[layer];return {};
  }
  assert.equal(d.using.name,undefined);
  const type=d.using.type._obj;
  const kind={solidColorLayer:'fill',curves:'curves',hueSaturation:'hue',colorBalance:'balance',blackAndWhite:'bw'}[type];
  assert.equal(d._options.dialogOptions,'dontDisplay');
  if(type==='solidColorLayer')assert.deepEqual(d.using.type.color,{_obj:'RGBColor',red:12,grain:34,blue:56});
  const anchor=doc.activeLayers[0],bounds=anchor.boundsNoEffects;
  const parent=anchor.kind==='group'?anchor:anchor.parent,siblings=parent?parent.layers:doc.layers;
  const index=anchor.kind==='group'?0:siblings.indexOf(anchor);
  if(consumeEmpty && anchor.kind==='pixel' && !anchor.isBackgroundLayer && !(bounds && bounds.right>bounds.left && bounds.bottom>bounds.top))remove(anchor);
  const layer=attach({id:next++,kind:wrongKind?'pixel':kind,name:type+' '+next,parent});
  if(badMove){doc.layers.unshift(layer);layer.parent=null;}else siblings.splice(index,0,layer);
  doc.activeLayers=[layer];return {};
})},core:{executeAsModal:async f=>{
  const snapshot=structuredClone({layers:doc.layers,active:doc.activeLayers});
  modalContext={isCancelled:false,hostControl:{suspendHistory:async()=>{histories++;return 1;},resumeHistory:async(id,commit)=>{
    if(!commit){rollbacks++;doc.layers=snapshot.layers;doc.activeLayers=snapshot.active;}
  }}};return f(modalContext);
}}};
let badMove=false;
function remove(layer) {const layers=layer.parent?layer.parent.layers:doc.layers;const i=layers.indexOf(layer);assert.ok(i>=0);layers.splice(i,1);}
function attach(layer) {
  Object.defineProperty(layer,'move',{value:async(anchor,placement)=>{
    throw Error('Creation must use native insertion, never move');
  }});
  Object.defineProperty(layer,'delete',{value:async()=>remove(layer)});
  return layer;
}
doc.createLayer=async()=>{throw Error('DOM top-then-move creation must not be used');};
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
  assert.deepEqual(blank.selection_context.layer_ids,[created.id]);
  assert.equal(api.selectionMatches(blank.selection_context),true);
  assert.equal(api.selectionMatches({...blank.selection_context,session:'other'}),false);
  assert.equal(api.selectionMatches({...blank.selection_context,document_id:999}),false);
  doc.activeLayers=[anchor];assert.equal(api.selectionMatches(blank.selection_context),false);
  doc.activeLayers=[created];
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
      assert.equal(api.selectionContext(true).quick_mask,api.selectionContext().quick_mask,'Creation-only capability must match full fresh eligibility');
      const inside=anchor.kind==='group';
      const parent=inside?anchor:anchor.parent;
      const originalSiblings=(parent?parent.layers:doc.layers).map(l=>l.id);
      const result=await run(command),made=doc.activeLayers[0];
      assert.equal(result.placement_moves,0,'Native creation must not be repositioned');
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
  const filled=fixture('root-middle');filled.boundsNoEffects={left:0,top:0,right:32,bottom:32};
  const w0=writes;await run('adjustment.curves');assert.equal(writes-w0,1,'Filled layer must avoid placeholder creation');
  const uncertain=fixture('root-middle');uncertain.boundsNoEffects={left:0,top:0,right:NaN,bottom:32};
  const w1=writes;await run('adjustment.curves');assert.equal(writes-w1,2,'Uncertain pixel layer keeps placeholder');
  const empty=fixture('root-middle');empty.boundsNoEffects={left:0,top:0,right:0,bottom:0};
  const w2=writes;await run('adjustment.curves');assert.equal(writes-w2,2,'Empty pixel layer keeps placeholder');
  fixture('root-middle');const originalMode=Object.getOwnPropertyDescriptor(doc,'mode'),writesBefore=writes;
  Object.defineProperty(doc,'mode',{configurable:true,get(){
    if(writes>writesBefore)throw Error('post-creation metadata unavailable');return 'RGB';
  }});
  const metadataFailed=await run('layer.new');
  assert.equal(metadataFailed.verified,true);assert.equal(metadataFailed.selection_context,undefined);
  Object.defineProperty(doc,'mode',originalMode);
  // Native strategy feedback is freshly read after modal exit by main.js.
  // It must not repeat the optional full DOM read inside each creation, nor
  // remove eligibility, placement, membership, rollback or identity checks.
  const nativeApi=create(ps,'s',{nativeSelection:true});
  let discardedReads=0;
  for(const command of ['layer.new','layer.solid','layer.group','adjustment.curves','adjustment.hueSaturation','adjustment.colorBalance','adjustment.blackWhite']) {
    fixture('root-middle');const beforeWrites=writes;
    Object.defineProperty(doc,'mode',{configurable:true,get(){if(writes>beforeWrites)discardedReads++;return 'RGB';}});
    const result=await nativeApi.setLabel({command,target:await nativeApi.capture(),expires_at_ms:Date.now()+5000});
    assert.equal(result.verified,true);assert.equal(result.selection_context,undefined);
    assert.equal(result.selection_feedback,'fresh-native-after-modal');
    Object.defineProperty(doc,'mode',originalMode);
  }
  assert.equal(discardedReads,0,'Native creation must not build discarded DOM feedback');
  fixture('root-middle');const nativeTarget=await nativeApi.capture(),nativeWrites=writes;
  doc.activeLayers=[doc.layers[0]];
  await assert.rejects(nativeApi.setLabel({command:'layer.new',target:nativeTarget,expires_at_ms:Date.now()+5000}),/target changed/);
  assert.equal(writes,nativeWrites,'Deferred feedback must never defer write authorization');
  function largeFixture(count,nested=false,background=false) {
    const layers=Array.from({length:count},(_,i)=>attach({id:10000+i,kind:'pixel',boundsNoEffects:{left:0,top:0,right:3,bottom:3}}));
    if(background)layers.at(-1).isBackgroundLayer=true;
    if(nested) {
      const group={id:9000,kind:'group',layers};for(const layer of layers)layer.parent=group;
      doc.layers=[group];
    } else doc.layers=layers;
    doc.activeLayers=[layers[Math.floor(count/2)]];next=20000;
  }
  for(const count of [4,31,32]) {
    largeFixture(count);const reads=nativeReads;
    assert.equal((await run('layer.new')).tree_reader,'dom');assert.equal(nativeReads,reads);
  }
  for(const nested of [false,true])for(const background of [false,true]) {
    if(nested && background)continue;
    largeFixture(100,nested,background);
    assert.equal((await run('adjustment.curves')).tree_reader,'batch');
  }
  for(const fault of ['unsupported','incomplete','duplicate','parent','index','index-base','section','unbalanced','prefix','oversize']) {
    largeFixture(100);nativeFault=fault;
    assert.equal((await run('layer.new')).tree_reader,'dom-fallback',fault);
  }
  largeFixture(100);nativeFault='stale';const writesAt=writes;
  await assert.rejects(run('layer.new'),/target changed/);assert.equal(writes,writesAt);nativeFault=null;
  largeFixture(100);nativeFault='cancelled';const cancelWrites=writes;
  await assert.rejects(run('layer.new'),/expired/);assert.equal(writes,cancelWrites);nativeFault=null;
  largeFixture(100);wrongKind=true;const failedBatchRollbacks=rollbacks;
  await assert.rejects(run('adjustment.curves'),/核验失败/);assert.equal(rollbacks,failedBatchRollbacks+1);assert.equal(doc.layers.length,100);wrongKind=false;
  console.log('PASS small DOM boundary, large root/nested/background batch, malformed/unsupported/oversize fallback, fresh target after await');
  console.log('PASS '+placementChecks+' creation placements, native group-inside, zero moves, multi-focus, consumed/retained placeholder, native naming descriptors, wrong insertion rollback');
  console.log('PASS seven commands, RGB foreground, exact group membership, target/eligibility before history, failed readback rollback');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
