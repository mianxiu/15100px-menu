const assert=require('node:assert/strict');
const create=require('../uxp/offline-probe/labels.js');
const copy=v=>JSON.parse(JSON.stringify(v));
async function fixture(ordinary=false,gradient=false,coreRedraw=true,stripModalFields=false,legacyPreview=false){
 const layer={id:30,kind:'solid',parent:null,vectorMaskFeather:0,vectorMaskDensity:100};
 let siblingReads=0,catalogReads=0;
 const doc={id:12,activeLayers:[layer],get layers(){siblingReads++;return [layer];},mode:'rgb',bitsPerChannel:8,resolution:72};
 let fill={_obj:'solidColorLayer',color:{_obj:'RGBColor',red:12,grain:34,blue:56}};
 let stroke={_obj:'strokeStyle',strokeStyleVersion:2,strokeEnabled:false,fillEnabled:true,
  strokeStyleLineWidth:{_unit:'pixelsUnit',_value:1},strokeStyleContent:{_obj:'solidColorLayer',color:{_obj:'RGBColor',red:0,grain:0,blue:0}}};
 stroke.strokeStyleLineCapType={_enum:'strokeStyleLineCapType',_value:'strokeStyleRoundCap'};
 if(gradient)fill={_obj:'gradientLayer',angle:{_unit:'angleUnit',_value:37},scale:{_unit:'percentUnit',_value:82},
  type:{_enum:'gradientType',_value:'linear'},gradient:{_obj:'gradientClassEvent',name:'Owned gradient',
   colors:[0,4096].map(location=>({_obj:'colorStop',color:{_obj:'RGBColor',red:12,grain:34,blue:56},location,midpoint:37})),
   transparency:[0,4096].map(location=>({_obj:'transferSpec',location,midpoint:29,opacity:{_unit:'percentUnit',_value:73}}))}};
 let resumeCalls=0,failCommit=false,histories=0,commits=0,rollbacks=0,sets=0,redraws=0,saved,failRollback=false,failRedraw=false,redrawBlock=null;
 const ps={constants:{LayerKind:{SOLIDFILL:'solid'},DocumentMode:{RGB:'rgb'},BitsPerChannelType:{EIGHT:8,SIXTEEN:16}},
 app:{documents:[doc],activeDocument:doc},action:{batchPlay:async (cs,options)=>{
  if(options.immediateRedraw)redraws++;
  return cs.map(c=>{
  if(options.immediateRedraw){
   assert.equal(c._obj,'set');
   assert.equal(c._options.dialogOptions,'silent');
   if(failRedraw)return {_obj:'error',message:'redraw unavailable'};
  }
  if(c._obj==='set'){
   assert.equal(c._options.dialogOptions,'silent');
   if(c.to._obj==='layer'){
    assert.equal(Object.keys(c.to).length,2,'Photoshop mask setter only supports one property per descriptor');
    assert.equal(c._target[0]._id,layer.id);assert.equal(c._target[1]._id,doc.id);
    if(c.to.vectorMaskFeather){assert.equal(c.to.vectorMaskFeather._unit,'pixelsUnit');layer.vectorMaskFeather=c.to.vectorMaskFeather._value;}
    if(c.to.vectorMaskDensity){assert.equal(c.to.vectorMaskDensity._unit,'percentUnit');layer.vectorMaskDensity=c.to.vectorMaskDensity._value;}
    return {};
   }
   if(!ordinary && c.to._obj!=='shapeStyle')throw Error('Set unavailable: vector-backed fills require shapeStyle');
   assert.deepEqual(c._target,[{_ref:'contentLayer',_enum:'ordinal',_value:'targetEnum'}]);
   assert.equal(ps.app.activeDocument.id,12);assert.deepEqual(doc.activeLayers.map(l=>l.id),[30]);
   sets++;if(c.to._obj!=='shapeStyle')fill=copy(c.to);else {if(c.to.fillContents)fill=copy(c.to.fillContents);if(c.to.strokeStyle)stroke=copy(c.to.strokeStyle);}return {};
  }
  switch(c._target[0]._property){
   case 'layerID':return {layerID:layer.id};
   case 'layerKind':return {layerKind:4};case 'hasVectorMask':return {hasVectorMask:!ordinary};
   case 'adjustment':return {adjustment:[copy(fill)]};case 'AGMStrokeStyleInfo':return {AGMStrokeStyleInfo:copy(stroke)};
   case 'presetManager':catalogReads++;return {presetManager:[]};default:throw Error('Unexpected descriptor');
  }
 });}},core:{executeAsModal:async(fn,options)=>{
  assert.equal(options.interactive,options.commandName==='Menu paint preview'?true:undefined);
  try {return await fn({isCancelled:false,hostControl:{
   suspendHistory:async()=>{histories++;saved={fill:copy(fill),stroke:copy(stroke),feather:layer.vectorMaskFeather,density:layer.vectorMaskDensity};return 7;},
   resumeHistory:async(id,commit)=>{resumeCalls++;assert.equal(id,7);if(commit){if(failCommit)throw Error('native commit interrupted');commits++;return;}rollbacks++;
    if(failRollback)throw Error('rollback unavailable');
    fill=saved.fill;stroke=saved.stroke;layer.vectorMaskFeather=saved.feather;layer.vectorMaskDensity=saved.density;}
  }});} catch(error) {if(stripModalFields)throw Error(error.message);throw error;}
 }}};
 if(coreRedraw)ps.core.redrawDocument=async options=>{
  assert.deepEqual(options,{documentID:doc.id});redraws++;
  if(redrawBlock)await redrawBlock;
  if(failRedraw)throw Error('刷新 unavailable');return .01;
 };
 const rawApi=create(ps,'session',{legacyPreview});
 const api=rawApi;
 const target=await api.capture();
 const data=await api.observeShape(api.selectionContext(),true);
 const paint=Object.fromEntries(['revision','fill','stroke','mask'].filter(k=>data[k]!==undefined).map(k=>[k,copy(data[k])]));
 // Backend canonicalization reorders keys; equality must compare values.
 paint.stroke={kind:paint.stroke.kind,enabled:paint.stroke.enabled,...(paint.stroke.rgb?{rgb:paint.stroke.rgb}:{stops:paint.stroke.stops}),width:paint.stroke.width};
 const request={command:'shape.preview',id:'a'.repeat(32),session:'session',token:'local-test',target,
  expires_at_ms:Date.now()+10000,paint};
 const packet=(seq,phase='preview',mask={feather:seq,density:70})=>({id:request.id,session:request.session,token:request.token,
  seq,phase,lease_until_ms:Date.now()+4000,paint:{...copy(paint),mask}});
 const state=()=>({histories,commits,rollbacks,resumeCalls,sets,redraws,siblingReads,catalogReads,mask:{feather:layer.vectorMaskFeather,density:layer.vectorMaskDensity}});
 return {api,request,packet,layer,state,fail:()=>{failRollback=true;},color:()=>fill.color,
  failCommit:()=>{failCommit=true;},switchTarget:()=>{doc.activeLayers=[{...layer,id:31}];},
  blockRedraw:()=>{let release;redrawBlock=new Promise(resolve=>{release=resolve;});return ()=>{redrawBlock=null;release();};},
  raw:()=>copy({fill,stroke}),external:()=>{fill.color.red=213;},failRedraw:()=>{failRedraw=true;}};
}
async function main(){
 let count=0;
 {const f=await fixture(false,false,false,false,true),request={...f.request,command:'shape.legacy.preview'};
  const prepared=await f.api.prepareLegacyShape(request);assert.equal(prepared.before.preview_engine,'legacy-com');assert.equal(prepared.before.live_preview,true);
  assert.equal(f.state().histories,0);assert.equal(f.state().sets,0);
  f.switchTarget(); // A later user selection must not invalidate the native terminal proof.
  const result=await f.api.finishLegacyShape(request,prepared,{phase:'completed',result:{verified:true,count:1,placement_moves:0,paint:request.paint,preview:{engine:'standalone-extendscript',last_seq:2}}});
  assert.equal(result.verified,true);assert.equal(f.state().histories,0);assert.equal(f.state().sets,0);count++;}
 {const f=await fixture(false,false,false,false,true),request={...f.request,command:'shape.legacy.preview'};
  const prepared=await f.api.prepareLegacyShape(request);
  await assert.rejects(f.api.finishLegacyShape(request,prepared,{phase:'completed',result:{verified:true,count:1,placement_moves:0,paint:request.paint,preview:{engine:'forged',last_seq:2}}}),e=>e.resultUnknown===true);
  assert.equal(f.state().histories,0);count++;}
 {const f=await fixture(false,false,false,false,true),request={...f.request,command:'shape.legacy.preview'};
  const prepared=await f.api.prepareLegacyShape(request);
  await assert.rejects(f.api.finishLegacyShape(request,prepared,{phase:'failed',error:'native rollback unavailable',result_unknown:true}),e=>e.resultUnknown===true);
  assert.equal(f.state().histories,0);count++;}
 {const f=await fixture(false,false,false,false,true);f.request.paint.revision='stale';
  await assert.rejects(f.api.prepareLegacyShape(f.request),/已改变/);assert.equal(f.state().histories,0);assert.equal(f.state().sets,0);count++;}
 for(const change of ['fill','mask']) {
  const f=await fixture(false,false,false);f.request.command='shape.paint';
  if(change==='fill')f.request.paint.fill.rgb=[80,70,60];else f.request.paint.mask={feather:12.5,density:40};
  const result=await f.api.setLabel(f.request);assert.equal(result.verified,true);
  assert.equal(f.state().histories,1);assert.equal(f.state().commits,1);assert.equal(f.state().redraws,0);
  if(change==='fill')assert.equal(f.color().red,80);else assert.deepEqual(f.state().mask,{feather:12.5,density:40});
  count++;
 }

 for(const problem of ['rollback-fails','selection-changes']){
  const f=await fixture(false,false,true,true),frames=[f.packet(1),f.packet(2,'cancel')];
  if(problem==='rollback-fails')f.fail();
  await assert.rejects(f.api.setLabel(f.request,{read:async()=>frames.shift(),stage:async stage=>{
   if(problem==='selection-changes' && stage==='verify-rollback')f.switchTarget();
  }}),error=>error.resultUnknown===true,'Native error recreation must retain unknown rollback status');
  assert.equal(f.state().commits,0);assert.equal(f.state().resumeCalls,1,'Never repeat a resume with an uncertain outcome');count++;
 }
 for(const strip of [false,true]){
  const f=await fixture(false,false,true,strip),frames=[f.packet(1),f.packet(2,'commit')];f.failCommit();
  await assert.rejects(f.api.setLabel(f.request,{read:async()=>frames.shift()}),e=>e.resultUnknown===true);
  assert.equal(f.state().resumeCalls,1);assert.equal(f.state().rollbacks,0);count++;
 }

 {const f=await fixture(),p=f.packet(1);p.paint.fill.rgb=[99,88,77];
  await assert.rejects(f.api.setLabel(f.request,{read:async()=>p,stage:async value=>{
   if(value==='write-color')f.switchTarget();
  }}),/target changed/i);
  assert.equal(f.state().sets,0,'Changing selection across an await must not write to the new target');
  assert.equal(f.state().rollbacks,1);count++;
 }
 {const f=await fixture(),release=f.blockRedraw(),frames=[f.packet(1),f.packet(2,'cancel')];
  frames[0].paint.fill.rgb=[99,88,77];let ended=false,acknowledged=0,lastStage;
  const operation=f.api.setLabel(f.request,{read:async()=>frames.shift(),stage:async value=>{lastStage=value;},
   applied:async()=>{acknowledged++;}}).finally(()=>{ended=true;});
  await new Promise(resolve=>setTimeout(resolve,20));
  assert.equal(lastStage,'redraw-native');assert.equal(ended,false);assert.equal(acknowledged,0);
  assert.equal(f.state().sets,1);assert.equal(f.state().commits,0);
  release();const result=await operation;
  assert.equal(result.rollback_verified,true);assert.equal(f.state().histories,1);
  assert.equal(f.state().rollbacks,1);assert.equal(f.state().sets,1);count++;
 }
 // A long drag must not enumerate siblings or refresh the global preset
 // catalog. Target identity, ancestor locks and raw paint are still fresh.
 {const f=await fixture(),now=Date.now;let offset=0,frame=0,siblings;
  Date.now=()=>now()+offset;
  try {
   const result=await f.api.setLabel(f.request,{read:async()=>{
    const p=f.packet(++frame,frame===3?'cancel':'preview');p.paint.fill.rgb=[30+frame,70,120];return p;
   },applied:async()=>{
    if(siblings!==undefined)assert.equal(f.state().siblingReads,siblings,'Live frames must not reread sibling lists');
    siblings=f.state().siblingReads;offset=60000;
   }});
   assert.equal(result.rollback_verified,true);assert.equal(f.state().catalogReads,1,'Long transactions keep the frozen editor catalog');
   count++;
  }finally {Date.now=now;}
 }
 // Acknowledgement must follow an awaited UI flush, once per combined frame.
 for(const coreRedraw of [true,false])for(const channel of ['fill','stroke','mask','combined','unchanged']){
  const f=await fixture(false,false,coreRedraw),p=f.packet(1,'preview',{feather:0,density:100});
  if(!coreRedraw){await assert.rejects(f.api.setLabel(f.request,{read:async()=>p}),/实时预览需要PS24.1/);assert.equal(f.state().histories,0);assert.equal(f.state().sets,0);assert.equal(f.state().redraws,0);count++;continue;}
  if(channel==='fill'||channel==='combined')p.paint.fill.rgb=[100,80,60];
  if(channel==='stroke'||channel==='combined'){p.paint.stroke.enabled=true;p.paint.stroke.rgb=[20,40,60];}
  if(channel==='mask'||channel==='combined')p.paint.mask={feather:20,density:40};
  const frames=[p,{...copy(p),seq:2},{...copy(p),seq:3,phase:'cancel'}];let seen=0;
  await f.api.setLabel(f.request,{read:async()=>frames.shift(),applied:async v=>{
   assert.equal(f.state().redraws,channel==='unchanged'?0:1);
   assert.equal(v.redraw_completed,channel!=='unchanged' && seen===0);seen++;
   if(v.redraw_completed)assert.equal(v.redraw_method,coreRedraw?'core.redrawDocument':'legacy.app.refresh');
  }});
  assert.equal(seen,2);assert.equal(f.state().redraws,(channel==='unchanged'?0:1)+1);
  assert.equal(f.state().histories,1);assert.equal(f.state().rollbacks,1);count++;
 }
 for(const coreRedraw of [true,false]){const f=await fixture(false,false,coreRedraw),p=f.packet(1);f.failRedraw();let acknowledgements=0;
  await assert.rejects(f.api.setLabel(f.request,{read:async()=>p,applied:async()=>{acknowledgements++;}}),/刷新|实时预览/);
  assert.equal(acknowledgements,0);assert.equal(f.state().rollbacks,coreRedraw?1:0);count++;}
 {const f=await fixture(),frames=[f.packet(1),f.packet(2),f.packet(3,'commit')];
  for(const p of frames){p.paint.stroke.rgb=[81,72,63];p.paint.stroke.enabled=true;}
  frames[1].paint.fill.enabled=false;frames[2].paint.fill.enabled=false;
  const result=await f.api.setLabel(f.request,{read:async()=>frames.shift()});
  assert.equal(result.verified,true);assert.equal(f.raw().stroke.fillEnabled,false);
  assert.deepEqual(f.raw().stroke.strokeStyleContent.color,{_obj:'RGBColor',red:81,grain:72,blue:63});count++;}
 for(const ordinary of [false,true])for(const end of ['commit','cancel']){
  const f=await fixture(ordinary,true),original=f.raw(),frames=[f.packet(1),f.packet(2),f.packet(3,end)];
  for(const [i,p] of frames.entries()){
   if(ordinary)delete p.paint.mask;
   p.paint.fill.stops[0].rgb=[90+i,80,70];p.paint.fill.stops[0].location=100+i;
  }
  await f.api.setLabel(f.request,{read:async()=>frames.shift(),applied:async v=>{
   assert.equal(v.fill.kind,'gradient');const raw=f.raw();
   assert.deepEqual(raw.fill.angle,original.fill.angle);assert.deepEqual(raw.fill.scale,original.fill.scale);
   assert.deepEqual(raw.fill.gradient.transparency,original.fill.gradient.transparency);
   assert.equal(raw.fill.gradient.colors[0].midpoint,37);assert.deepEqual(raw.stroke,original.stroke);
  }});
  if(end==='cancel')assert.deepEqual(f.raw(),original);
  assert.equal(f.state().histories,1);count++;
 }
 for(const ordinary of [false,true])for(const end of ['commit','cancel'])for(const channel of ordinary?['fill']:['fill','stroke']){
  const f=await fixture(ordinary),original=f.raw(),frames=[1,50,51].map(seq=>f.packet(seq));
  for(const [i,p] of frames.entries()){
   if(ordinary)delete p.paint.mask;
   p.paint[channel].rgb=[100+i,70,190];if(channel==='stroke')p.paint.stroke.enabled=true;
  }
  frames[2].phase=end;let seen=0;
  const result=await f.api.setLabel(f.request,{read:async()=>frames.shift(),applied:async v=>{
   assert.deepEqual(v[channel].rgb,[100+seen,70,190]);assert.equal(f.state().commits,0);seen++;
  }});
  assert.equal(seen,2);assert.equal(f.state().histories,1);
  assert.equal(f.state().sets,end==='commit'?3:2);
  if(end==='cancel'){assert.equal(result.rollback_verified,true);assert.deepEqual(f.raw(),original);}
  else {assert.equal(result.verified,true);assert.equal(f.state().commits,1);}
  count++;
 }
 {const f=await fixture(),frames=[f.packet(1),f.packet(2),f.packet(3,'commit')];
  frames[0].paint.fill.rgb=[99,88,77]; // Return to original must really write back.
  await f.api.setLabel(f.request,{read:async()=>frames.shift()});
  assert.deepEqual(f.color(),{_obj:'RGBColor',red:12,grain:34,blue:56});assert.equal(f.state().sets,2);count++;}
 {const f=await fixture(),frames=[f.packet(1),f.packet(2,'commit')];
  for(const p of frames)p.paint.fill.rgb=[99,88,77];
  await f.api.setLabel(f.request,{read:async()=>frames.shift()});assert.equal(f.state().sets,1);count++;}
 {const f=await fixture(),frames=[f.packet(1),f.packet(2,'commit')];
  for(const p of frames)p.paint.fill.rgb=[99,88,77];
  await assert.rejects(f.api.setLabel(f.request,{read:async()=>frames.shift(),applied:async()=>f.external()}),/outside preview/);
  assert.equal(f.state().commits,0);assert.equal(f.state().rollbacks,1);count++;}
 {const f=await fixture(true),p=f.packet(1);delete p.paint.mask;
  p.paint.fill={kind:'gradient',enabled:true,stops:[{location:0,rgb:[0,0,0]},{location:4096,rgb:[255,255,255]}]};
  await assert.rejects(f.api.setLabel(f.request,{read:async()=>p}),/原生类型/);assert.equal(f.state().sets,0);count++;}
 for(const end of ['commit','cancel']){
  const f=await fixture(),frames=[f.packet(1),f.packet(90),f.packet(91,end,{feather:12.5,density:40})],seen=[];
  const result=await f.api.setLabel(f.request,{read:async()=>frames.shift(),applied:async v=>{
   seen.push(v.seq);assert.deepEqual(v.mask,f.state().mask);assert.equal(f.state().commits,0);
  }});
  assert.deepEqual(seen,[1,90]);assert.equal(f.state().histories,1);assert.equal(f.state().sets,0);
  if(end==='commit'){assert.equal(result.verified,true);assert.equal(f.state().commits,1);assert.deepEqual(f.state().mask,{feather:12.5,density:40});}
  else {assert.equal(result.rollback_verified,true);assert.equal(f.state().commits,0);assert.deepEqual(f.state().mask,{feather:0,density:100});}
  count++;
 }
 {const f=await fixture(),a=f.packet(1),last=f.packet(2,'commit',{feather:0,density:100});
  last.paint.fill.rgb=[99,88,77];const frames=[a,last];
  await f.api.setLabel(f.request,{read:async()=>frames.shift()});
  assert.deepEqual(f.state().mask,{feather:0,density:100});assert.equal(f.state().commits,1);
  assert.deepEqual(f.color(),{_obj:'RGBColor',red:99,grain:88,blue:77});count++;}
 for(const problem of ['identity','session','token','revision','sequence','lease','mask','target','rollback']){
  const f=await fixture(),first=f.packet(10),bad=f.packet(11),frames=[first,bad];
  if(problem==='identity')bad.id='b'.repeat(32);
  if(problem==='session')bad.session='new-session';
  if(problem==='token')bad.token='other';
  if(problem==='revision')bad.paint.revision='stale';
  if(problem==='sequence')bad.seq=9;
  if(problem==='lease')bad.lease_until_ms=Date.now()+60000;
  if(problem==='mask')bad.paint.mask.feather=1001;
  if(problem==='rollback'){bad.phase='cancel';f.fail();}
  await assert.rejects(f.api.setLabel(f.request,{read:async()=>frames.shift(),applied:async()=>{
   if(problem==='target')f.layer.id=31;
  }}),e=>problem==='rollback'?e.resultUnknown===true:true);
  assert.equal(f.state().commits,0);assert.ok(f.state().rollbacks>=1);count++;
 }
 {const f=await fixture(),p=f.packet(1);p.lease_until_ms=Date.now()-1;
  const result=await f.api.setLabel(f.request,{read:async()=>p});assert.equal(result.cancelled,true);
  assert.equal(f.state().commits,0);assert.equal(f.state().rollbacks,1);count++;}
 {const f=await fixture();f.request.paint.revision='stale';
  await assert.rejects(f.api.setLabel(f.request,{read:async()=>f.packet(1)}));assert.equal(f.state().histories,0);count++;}
 {const f=await fixture(),clock=Date.now;let offset=0,frame=0;
  Date.now=()=>clock()+offset;
  try {
   const result=await f.api.setLabel(f.request,{read:async()=>f.packet(++frame,frame===1?'preview':'commit'),
    applied:async()=>{offset=5000;}});
   assert.equal(result.verified,true);assert.equal(f.state().commits,1);count++;
  }finally{Date.now=clock;}}
 console.log(`PASS mask preview: ${count} transaction cases; live readback, skipped obsolete values, final value, rollback, one history, identity and unknown guards`);
}
main().catch(e=>{console.error(e);process.exitCode=1;});
