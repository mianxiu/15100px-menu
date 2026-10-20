// Compare production scalar reads against the independent DOM topology walk.
const assert=require('node:assert/strict'),create=require('../uxp/offline-probe/labels.js');
const K={NORMAL:'pixel',GROUP:'group',TEXT:'text',SMARTOBJECT:'smart',SOLIDFILL:'fill',GRADIENTFILL:'gradient',PATTERNFILL:'pattern',CURVES:'curves',VIDEO:'video',LAYER3D:'3d'};
const C={LayerKind:K,DocumentMode:{RGB:'rgb',CMYK:'cmyk',LAB:'lab',GRAYSCALE:'gray',BITMAP:'bitmap',INDEXEDCOLOR:'indexed',MULTICHANNEL:'multi',DUOTONE:'duotone'},BitsPerChannelType:{EIGHT:8,SIXTEEN:16,THIRTYTWO:32}};
const am={pixel:1,curves:2,text:3,fill:11,smart:5,video:6,group:7,'3d':8,gradient:9,pattern:10};
let nextID=100;
function layer(kind='pixel',children=null){return {id:nextID++,kind,parent:null,layers:children||[],allLocked:false,positionLocked:false,isBackgroundLayer:false};}
function model(roots,bg=false){
  if(bg){const background=layer();background.isBackgroundLayer=true;roots.push(background);}
  const doc={id:9,layers:roots,mode:'rgb',bitsPerChannel:8,activeLayers:[roots[0]]};
  const control={trees:0,rows:0,commands:0,bytes:0,mode:'RGBColor'};
  function rows(){
    const result=[];
    function walk(list,parent=null){for(const l of list){l.parent=parent;
      result.push({layerID:l.id,parentLayerID:parent?parent.id:-1,layerKind:l.amKind??am[l.kind],background:l.isBackgroundLayer,
        layerSection:{_value:l.kind==='group'?'layerSectionStart':'layerSectionContent'},layerLocking:{protectAll:l.allLocked,protectPosition:l.positionLocked}});
      if(l.kind==='group'){walk(l.layers,l);result.push({layerID:-l.id,layerSection:{_value:'layerSectionEnd'}});}
    }}
    walk(roots);result.forEach((r,i)=>r.itemIndex=result.length-i);return result;
  }
  rows();
  const ps={constants:C,app:new Proxy({},{get(){throw Error('Native path must not touch host DOM');}}),core:{executeAsModal(){throw Error('Read must not enter modal');}},
    action:{async batchPlay(commands){return commands.map(command=>{
      control.commands++;assert.equal(command._options.dialogOptions,'silent');
      const raw=rows();let result;
      if(command._obj==='multiGet'){
        if(command.extendedReference.length===2){control.trees++;result={list:raw};}
        else{
          const ref=command._target._ref[0];assert.ok(command.extendedReference[0].every(x=>['layerID','parentLayerID','itemIndex','layerSection','layerKind','background','layerLocking'].includes(x)));
          let row=raw.find(x=>ref._id!==undefined?x.layerID===ref._id:ref._index!==undefined?x.itemIndex===ref._index+(bg?1:0):x.layerID===doc.activeLayers[0].id);
          result=row?structuredClone(row):{_obj:'error'};control.rows++;
          if(control.omitSelected && ref._enum)delete result.layerLocking;
          if(control.badNeighbour && ref._index!==undefined)result.parentLayerID=98765;
          if(control.onScalar)control.onScalar(ref,result);
        }
      }else{
        const key=command._target[0]._property;
        const data={numberOfDocuments:1,documentID:doc.id,targetLayersIDs:doc.activeLayers.map(l=>({_ref:'layer',_id:l.id})),
          numberOfLayers:raw.length-(bg?1:0),hasBackgroundLayer:bg,mode:{_value:control.mode},depth:doc.bitsPerChannel};
        result={[key]:data[key]};
      }
      control.bytes+=JSON.stringify(result).length;return structuredClone(result);
    });}}
  };
  const api=create(ps,'s',{nativeSelection:true}),reference=create({...ps,app:{documents:[doc],activeDocument:doc}},'s');
  return {doc,control,api,reference,roots,ps};
}
function clean(value){value={...value};for(const key of ['read_path','read_scope','read_fallback'])delete value[key];return value;}
async function parity(m,targeted=true){const got=await m.api.selectionContextNative(null,!targeted);assert.deepEqual(clean(got),m.reference.selectionContext());return got;}
(async()=>{
  let comparisons=0;
  for(const count of [1,4,100,300,5000])for(const bg of [false,true]){
    const m=model(Array.from({length:count},()=>layer()),bg);
    for(const index of new Set([0,Math.floor(count/2),count-1]))for(const kind of ['pixel','text','smart','fill','gradient','pattern','curves','video','3d'])for(const lock of ['none','position','all']){
      const l=m.roots[index];l.kind=kind;l.positionLocked=lock==='position';l.allLocked=lock==='all';m.doc.activeLayers=[l];
      const beforeRows=m.control.rows,got=await parity(m);
      if(count>8){assert.equal(got.read_path,'native-root-scalars');assert.equal(m.control.trees,0);}
      else assert.equal(got.read_scope,'bounded-tree');
      assert.ok(m.control.rows-beforeRows<=6,'Unrelated layer count must not increase returned records');comparisons++;
    }
  }
  for(const mode of ['RGBColor','CMYKColor','labColor','grayscale','bitmap','indexedColor','multichannel','duotone'])for(const depth of [8,16,32]){
    const m=model(Array.from({length:16},()=>layer()));m.doc.activeLayers=[m.roots[8]];m.control.mode=mode;
    m.doc.mode={RGBColor:'rgb',CMYKColor:'cmyk',labColor:'lab',grayscale:'gray',bitmap:'bitmap',indexedColor:'indexed',multichannel:'multi',duotone:'duotone'}[mode];
    m.doc.bitsPerChannel=depth;await parity(m);comparisons++;
  }
  // Siblings can be groups of arbitrary depth/size; AM ends are not layers.
  for(const bg of [false,true])for(const placement of ['top','middle','bottom']){
    const leaf=layer(),groupA=layer('group',[layer(),layer('group',[layer()])]),groupB=layer('group',[layer()]);
    const roots=placement==='top'?[leaf,groupA,groupB]:placement==='middle'?[groupA,leaf,groupB]:[groupA,groupB,leaf];
    // Keep enough unrelated root siblings to exercise scalar group adjacency.
    const padding=Array.from({length:12},()=>layer());
    if(placement==='bottom')roots.unshift(...padding);else roots.push(...padding);
    const m=model(roots,bg);m.doc.activeLayers=[leaf];assert.equal((await parity(m)).read_path,'native-root-scalars');comparisons++;
    m.doc.activeLayers=[groupA.layers[1].layers[0]];groupA.allLocked=true;
    assert.equal((await parity(m)).read_path,'native-24.2');comparisons++;
    groupA.allLocked=false;m.doc.activeLayers=[groupA];assert.equal((await parity(m)).read_path,'native-24.2');comparisons++;
    m.doc.activeLayers=[leaf,groupA.layers[0]];await parity(m);comparisons++;
  }
  // A far unknown kind is irrelevant to a proven ordinary root selection.
  let backgroundModel=model([layer(),layer()],true);
  backgroundModel.roots.at(-1).amKind=12;backgroundModel.doc.activeLayers=[backgroundModel.roots.at(-1)];
  await parity(backgroundModel);await parity(backgroundModel,false);
  let m=model(Array.from({length:100},()=>layer()));m.roots[50].amKind=999;m.roots[50].kind='unrecognized';
  m.doc.activeLayers=[m.roots[1]];assert.equal((await parity(m)).read_path,'native-root-scalars');
  await assert.rejects(m.api.selectionContextNative(null,true),/Unsupported/);
  // Missing properties or uncertain adjacency get exactly one full-tree read.
  for(const field of ['omitSelected','badNeighbour']){
    m=model(Array.from({length:16},()=>layer()));m.doc.activeLayers=[m.roots[8]];m.control[field]=true;
    assert.equal((await parity(m)).read_path,'native-24.2');assert.equal(m.control.trees,1);
  }
  // An identity change is never a reason to fall back, nor to select anew.
  m=model(Array.from({length:16},()=>layer()));m.doc.activeLayers=[m.roots[8]];m.control.omitSelected=true;
  m.control.onScalar=ref=>{if(ref._enum)m.doc.activeLayers=[m.roots[0]];};
  await assert.rejects(m.api.selectionContextFresh(),/changed/);assert.equal(m.control.trees,0);
  for(const change of ['lock','order','selection','mode']){
    m=model(Array.from({length:16},()=>layer()));m.doc.activeLayers=[m.roots[8]];let changed=false;
    m.control.onScalar=ref=>{if(ref._index!==undefined && !changed){changed=true;
      if(change==='lock')m.roots[8].allLocked=true;
      if(change==='order')m.roots.reverse();
      if(change==='selection')m.doc.activeLayers=[m.roots[0]];
      if(change==='mode')m.control.mode='CMYKColor';
    }};
    await assert.rejects(m.api.selectionContextFresh(),/changed/);assert.equal(m.control.trees,0);
  }
  m=model([layer(),layer()]);const stop=Error('new menu');
  await assert.rejects(m.api.selectionContextFresh(async()=>{throw stop;}),e=>e===stop);assert.equal(m.control.trees,0);
  m=model(Array.from({length:5000},()=>layer()));m.doc.activeLayers=[m.roots[2500]];let checkpoints=0;
  assert.equal((await m.api.selectionContextFresh(async()=>{checkpoints++;})).read_path,'native-root-scalars');
  assert.ok(checkpoints<=8,'Host checkpoints/local mailbox work must also stay bounded');
  // Work hints affect prefetch only: a fresh count always overrides them.
  m=model([layer(),layer(),layer(),layer()]);m.doc.activeLayers=[m.roots[1]];
  await parity(m);const warmRows=m.control.rows;await parity(m);
  assert.equal(m.control.rows,warmRows,'Warm tiny snapshots must not prefetch an unused scalar');
  m.roots.push(...Array.from({length:96},()=>layer()));
  assert.equal((await parity(m)).read_path,'native-root-scalars');
  m.roots.splice(4);assert.equal((await parity(m)).read_scope,'bounded-tree');
  // The comparison endpoint must require ownership, and when requested it
  // must measure the same cooperative checkpoints as production reads.
  m=model(Array.from({length:32},()=>layer()));m.doc.activeLayers=[m.roots[15]];
  const commandsBefore=m.control.commands;
  await assert.rejects(m.api.nativeReadComparison('unowned'),/ownership/);
  await assert.rejects(m.api.feedbackReadComparison('unowned'),/ownership/);
  assert.equal(m.control.commands,commandsBefore);
  let comparisonModal=false,comparisonModals=0;
  const benchmark=create({...m.ps,app:{documents:[m.doc],activeDocument:m.doc},core:{executeAsModal:async fn=>{
    comparisonModals++;comparisonModal=true;try{return await fn({isCancelled:false});}finally{comparisonModal=false;}
  }}},'s',{nativeSelection:true});
  benchmark.stability.guard=()=>{};let yields=0;
  const measurement=await benchmark.nativeReadComparison('owned',0,async()=>{yields++;});
  assert.equal(measurement.equivalent,true);assert.ok(yields>0);
  assert.equal(measurement.samples.targeted.checkpoints,8);
  assert.ok(measurement.samples.full.checkpoints>measurement.samples.targeted.checkpoints);
  Object.defineProperty(m.doc,'mode',{get(){assert.equal(comparisonModal,true,'Baseline DOM preparation must retain its original modal context');return 'rgb';}});
  for(const order of [0,1]) {
    const feedback=await benchmark.feedbackReadComparison('owned',order,async()=>{yields++;});
    assert.equal(feedback.equivalent,true);assert.equal(feedback.scope,'native-feedback-reads-only');
    assert.equal(feedback.samples.before.prepared_snapshots,1);assert.equal(feedback.samples.after.prepared_snapshots,0);
    assert.equal(feedback.samples.before.calls,feedback.samples.after.calls);
    assert.equal(feedback.samples.before.response_bytes,feedback.samples.after.response_bytes);
    assert.equal(feedback.samples.after.checkpoints,8);
    assert.equal(feedback.samples.after.discarded_dom_ms,0);
    assert.equal(feedback.samples.after.diagnostic_modal_overhead_ms,0);
  }
  assert.equal(comparisonModals,2);assert.equal(comparisonModal,false);
  await assert.rejects(benchmark.feedbackReadComparison('owned',2),/Invalid/);
  await assert.rejects(benchmark.feedbackReadComparison('owned',0,async()=>{throw stop;}),e=>e===stop);
  await assert.rejects(benchmark.nativeReadComparison('owned',2,async()=>{throw stop;}),e=>e===stop);
  console.log('PASS '+comparisons+' scalar/DOM capability comparisons, 1/4/100/300/5000 records, backgrounds/groups/modes/locks; bounded reads, one safe fallback, identity/cancel never downgrade');
})().catch(error=>{console.error(error);process.exitCode=1;});
