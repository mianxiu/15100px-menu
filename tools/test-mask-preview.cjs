const assert=require('node:assert/strict');
const create=require('../uxp/offline-probe/labels.js');
const copy=v=>JSON.parse(JSON.stringify(v));
async function fixture(ordinary=false,gradient=false){
 const layer={id:30,kind:'solid',parent:null,vectorMaskFeather:0,vectorMaskDensity:100};
 const doc={id:12,activeLayers:[layer],layers:[layer],mode:'rgb',bitsPerChannel:8,resolution:72};
 let fill={_obj:'solidColorLayer',color:{_obj:'RGBColor',red:12,grain:34,blue:56}};
 let stroke={_obj:'strokeStyle',strokeStyleVersion:2,strokeEnabled:false,fillEnabled:true,
  strokeStyleLineWidth:{_unit:'pixelsUnit',_value:1},strokeStyleContent:{_obj:'solidColorLayer',color:{_obj:'RGBColor',red:0,grain:0,blue:0}}};
 stroke.strokeStyleLineCapType={_enum:'strokeStyleLineCapType',_value:'strokeStyleRoundCap'};
 if(gradient)fill={_obj:'gradientLayer',angle:{_unit:'angleUnit',_value:37},scale:{_unit:'percentUnit',_value:82},
  type:{_enum:'gradientType',_value:'linear'},gradient:{_obj:'gradientClassEvent',name:'Owned gradient',
   colors:[0,4096].map(location=>({_obj:'colorStop',color:{_obj:'RGBColor',red:12,grain:34,blue:56},location,midpoint:37})),
   transparency:[0,4096].map(location=>({_obj:'transferSpec',location,midpoint:29,opacity:{_unit:'percentUnit',_value:73}}))}};
 let histories=0,commits=0,rollbacks=0,sets=0,redraws=0,saved,failRollback=false,failRedraw=false;
 const ps={constants:{LayerKind:{SOLIDFILL:'solid'},DocumentMode:{RGB:'rgb'},BitsPerChannelType:{EIGHT:8,SIXTEEN:16}},
 app:{documents:[doc],activeDocument:doc},action:{batchPlay:async (cs,options)=>cs.map(c=>{
  if(options.immediateRedraw){
   assert.equal(c._obj,'get');assert.equal(c._target[0]._property,'layerID');
   assert.equal(c._target[1]._id,layer.id);assert.equal(c._target[2]._id,doc.id);
   assert.equal(c._options.dialogOptions,'silent');redraws++;
   return failRedraw?{_obj:'error',message:'redraw unavailable'}:{layerID:layer.id};
  }
  if(c._obj==='set'){
   assert.equal(c._options.dialogOptions,'silent');
   if(!ordinary && c.to._obj!=='shapeStyle')throw Error('Set unavailable: vector-backed fills require shapeStyle');
   sets++;if(c.to._obj!=='shapeStyle')fill=copy(c.to);else {if(c.to.fillContents)fill=copy(c.to.fillContents);if(c.to.strokeStyle)stroke=copy(c.to.strokeStyle);}return {};
  }
  switch(c._target[0]._property){
   case 'layerKind':return {layerKind:4};case 'hasVectorMask':return {hasVectorMask:!ordinary};
   case 'adjustment':return {adjustment:[copy(fill)]};case 'AGMStrokeStyleInfo':return {AGMStrokeStyleInfo:copy(stroke)};
   case 'presetManager':return {presetManager:[]};default:throw Error('Unexpected descriptor');
  }
 })},core:{executeAsModal:async(fn,options)=>{
  assert.equal(options.interactive,true);
  return fn({isCancelled:false,hostControl:{
   suspendHistory:async()=>{histories++;saved={fill:copy(fill),stroke:copy(stroke),feather:layer.vectorMaskFeather,density:layer.vectorMaskDensity};return 7;},
   resumeHistory:async(id,commit)=>{assert.equal(id,7);if(commit){commits++;return;}rollbacks++;
    if(failRollback)throw Error('rollback unavailable');
    fill=saved.fill;stroke=saved.stroke;layer.vectorMaskFeather=saved.feather;layer.vectorMaskDensity=saved.density;}
  }});
 }}};
 const api=create(ps,'session'),target=await api.capture();
 const data=await api.observeShape(api.selectionContext(),true);
 const paint=Object.fromEntries(['revision','fill','stroke','mask'].filter(k=>data[k]!==undefined).map(k=>[k,copy(data[k])]));
 // Backend canonicalization reorders keys; equality must compare values.
 paint.stroke={kind:paint.stroke.kind,enabled:paint.stroke.enabled,...(paint.stroke.rgb?{rgb:paint.stroke.rgb}:{stops:paint.stroke.stops}),width:paint.stroke.width};
 const request={command:'shape.preview',id:'a'.repeat(32),session:'session',token:'local-test',target,
  expires_at_ms:Date.now()+10000,paint};
 const packet=(seq,phase='preview',mask={feather:seq,density:70})=>({id:request.id,session:request.session,token:request.token,
  seq,phase,lease_until_ms:Date.now()+4000,paint:{...copy(paint),mask}});
 const state=()=>({histories,commits,rollbacks,sets,redraws,mask:{feather:layer.vectorMaskFeather,density:layer.vectorMaskDensity}});
 return {api,request,packet,layer,state,fail:()=>{failRollback=true;},color:()=>fill.color,
  raw:()=>copy({fill,stroke}),external:()=>{fill.color.red=213;},failRedraw:()=>{failRedraw=true;}};
}
async function main(){
 let count=0;
 // Acknowledgement must follow an awaited UI flush, once per combined frame.
 for(const channel of ['fill','stroke','mask','combined','unchanged']){
  const f=await fixture(),p=f.packet(1,'preview',{feather:0,density:100});
  if(channel==='fill'||channel==='combined')p.paint.fill.rgb=[100,80,60];
  if(channel==='stroke'||channel==='combined'){p.paint.stroke.enabled=true;p.paint.stroke.rgb=[20,40,60];}
  if(channel==='mask'||channel==='combined')p.paint.mask={feather:20,density:40};
  const frames=[p,{...copy(p),seq:2},{...copy(p),seq:3,phase:'cancel'}];let seen=0;
  await f.api.setLabel(f.request,{read:async()=>frames.shift(),applied:async v=>{
   assert.equal(f.state().redraws,channel==='unchanged'?0:1);
   assert.equal(v.redraw_completed,channel!=='unchanged' && seen===0);seen++;
  }});
  assert.equal(seen,2);assert.equal(f.state().redraws,channel==='unchanged'?1:2);
  assert.equal(f.state().histories,1);assert.equal(f.state().rollbacks,1);count++;
 }
 {const f=await fixture(),p=f.packet(1);f.failRedraw();let acknowledgements=0;
  await assert.rejects(f.api.setLabel(f.request,{read:async()=>p,applied:async()=>{acknowledgements++;}}),/刷新/);
  assert.equal(acknowledgements,0);assert.equal(f.state().rollbacks,1);count++;}
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
