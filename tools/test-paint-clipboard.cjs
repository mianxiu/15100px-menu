const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('uxp/offline-probe/labels.js','utf8');
const code=source.slice(source.indexOf('function createPaintClipboard('),source.indexOf('// Cached vector-paint metadata'));
const copy=v=>JSON.parse(JSON.stringify(v));
function fixture(n=3){
 let ids=[1],active=1,store=new Map(),histories=0,rollbacks=0,writes=0,backup,failAt=0,cancel=false,failedRollback=false;
 for(let id=1;id<=n;id++)store.set(id,{layerID:id,layerKind:4,hasVectorMask:true,parentLayerID:-1,
  layerLocking:{protectAll:false,protectComposite:false,protectPosition:false,protectTransparency:false},name:'shape'+id,
  adjustment:[{_obj:'gradientLayer',angle:{_unit:'angleUnit',_value:27+id},gradient:{colors:[{color:{red:20*id}},{color:{red:250}}],transparency:[{opacity:43}]} }],
  AGMStrokeStyleInfo:{_obj:'strokeStyle',strokeStyleVersion:2,strokeEnabled:true,fillEnabled:true,strokeStyleLineWidth:{_unit:'pixelsUnit',_value:id},strokeStyleLineDashSet:[2,3],strokeStyleContent:{_obj:'solidColorLayer',color:{red:10*id}}},
  vectorMaskFeather:id+.1234,vectorMaskDensity:210-id,layerEffects:{shadow:id},hasUserMask:true,userMaskFeather:2});
 const doc={id:7,mode:'RGB',bitsPerChannel:8};
 const capture=async()=>({session:'s',document_id:doc.id,active_layer_id:active,layer_ids:ids.slice().sort((a,b)=>a-b)});
 const ps={constants:{DocumentMode:{RGB:'RGB'},BitsPerChannelType:{EIGHT:8,SIXTEEN:16}},app:{activeDocument:doc},
  core:{executeAsModal:async fn=>fn({get isCancelled(){return cancel;},hostControl:{
   suspendHistory:async()=>{histories++;backup={store:copy([...store]),ids:ids.slice(),active};return 1;},
   resumeHistory:async(h,commit)=>{if(!commit){rollbacks++;if(failedRollback)throw Error('rollback unavailable');store=new Map(copy(backup.store));ids=backup.ids;active=backup.active;}}
  }})},action:{batchPlay:async commands=>commands.map(c=>{
   const id=c._target?.find(v=>v._ref==='layer')?._id;
   if(c._obj==='get' && c._target[0]._property==='pathContents')return {pathContents:{shape:id,nodes:[1,2,3]}};
   if(c._obj==='get')return copy(store.get(id));
   if(c._obj==='select'){active=id;if(c.selectionModifier)ids.push(id);else ids=[id];return {};}
   if(c._obj==='set'){writes++;if(failAt===writes)return {_obj:'error',message:'injected failure'};const row=store.get(active);row.adjustment=[copy(c.to.fillContents)];row.AGMStrokeStyleInfo=copy(c.to.strokeStyle);return {};}
   throw Error(c._obj);
  })}};
 const box={};vm.runInNewContext(code+'this.create=createPaintClipboard;',box);
 const tree=async()=>({rows:[...store.keys()].map(id=>({layerID:id,parentLayerID:-1})),groups:new Map([...store.keys()].map(id=>[id,false]))});
 const api=box.create(ps,'s',capture,()=>({kind:'shape-fill'}),tree);
 async function run(command,extra={}){return api.execute({command,target:await capture(),expires_at_ms:Date.now()+10000,...extra});}
 return {api,run,select(v){ids=v.slice();active=v.at(-1);},row:id=>store.get(id),state:()=>({histories,rollbacks,writes,data:copy([...store]),ids:ids.slice(),active}),fail(n,rollback=false){failAt=n;failedRollback=rollback;},cancel(v){cancel=v;},doc};
}
async function main(){
 for(const n of [1,2,8,128]){
  const f=fixture(n);assert(!f.api.available());await assert.rejects(f.run('shape.pastePaint'),/先复制/);
  await f.run('shape.copyPaint');assert(f.api.available());assert.equal(f.state().histories,0);
  const original=f.state(),wanted=copy(f.row(1));f.select(Array.from({length:n},(_,i)=>i+1));
  const result=await f.run('shape.pastePaint');assert.equal(result.count,n);assert.equal(f.state().histories,1);assert.equal(f.state().rollbacks,0);
  for(let id=1;id<=n;id++){const row=f.row(id),old=original.data.find(([key])=>key===id)[1];assert.deepEqual(row.adjustment,wanted.adjustment);assert.deepEqual(row.AGMStrokeStyleInfo,wanted.AGMStrokeStyleInfo);for(const key of ['name','layerEffects','vectorMaskFeather','vectorMaskDensity','userMaskFeather'])assert.deepEqual(row[key],old[key]);}
 }
 for(const rollbackFails of [false,true]){
  const f=fixture();await f.run('shape.copyPaint');f.select([2,3]);const before=f.state();f.fail(2,rollbackFails);
  await assert.rejects(f.run('shape.pastePaint'),e=>rollbackFails?e.resultUnknown===true:!e.resultUnknown);
  assert.equal(f.state().writes,2);assert.equal(f.state().rollbacks,1);
  if(!rollbackFails){assert.deepEqual(f.state().data,before.data);assert.deepEqual(f.state().ids,before.ids);}
 }
 for(const change of ['locked','pixel','wrong-document','expired','cancelled','multi-copy','non-rgb']){
  const f=fixture();await f.run('shape.copyPaint');f.select([2,3]);
  if(change==='locked')f.row(2).layerLocking.protectAll=true;
  if(change==='pixel')f.row(2).hasVectorMask=false;
  if(change==='non-rgb')f.doc.mode='CMYK';
  if(change==='cancelled')f.cancel(true);
  let extra={};if(change==='wrong-document')extra.target={session:'s',document_id:99,active_layer_id:3,layer_ids:[2,3]};
  if(change==='expired')extra.expires_at_ms=0;
  await assert.rejects(f.run(change==='multi-copy'?'shape.copyPaint':'shape.pastePaint',extra));assert.equal(f.state().histories,0);assert.equal(f.state().writes,0);
 }
 const a=fixture(),b=fixture();await a.run('shape.copyPaint');assert(!b.api.available());
 console.log('PASS paint clipboard: native gradient/transparency/dashes, 1/2/8/128, one history, exact masks/effects/order, rollback and unknown without replay, locks/type/session/expiry/cancel fences');
}
main().catch(e=>{console.error(e);process.exit(1);});
