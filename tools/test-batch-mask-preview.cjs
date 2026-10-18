const assert=require('node:assert/strict'),create=require('../uxp/offline-probe/labels.js');
const copy=v=>JSON.parse(JSON.stringify(v));
async function fixture(n=2,legacy=false){
 const layers=Array.from({length:n},(_,i)=>({id:30+i,kind:'solid',parent:null,vectorMaskFeather:i+1,vectorMaskDensity:80-i%50,
  content:{layerKind:4,adjustment:[{_obj:'solidColorLayer',color:{red:i*7,grain:34,blue:56}}],AGMStrokeStyleInfo:{strokeEnabled:!!i},hasVectorMask:true,hasUserMask:!!i,userMaskFeather:2,userMaskDensity:190},path:{_obj:'pathClass',points:[i,2,4]}}));
 const doc={id:12,activeLayers:layers,layers,mode:'rgb',bitsPerChannel:8,resolution:72};let active=layers[n-1].id,saved,sets=0,histories=0,commits=0,rollbacks=0,redraws=0,failSet=0,failRollback=false,failCommit=false,historyResetsSelection=false,fullReads=0;
 const ps={constants:{LayerKind:{SOLIDFILL:'solid'},DocumentMode:{RGB:'rgb'},BitsPerChannelType:{EIGHT:8,SIXTEEN:16}},app:{documents:[doc],activeDocument:doc},
 action:{batchPlay:async commands=>commands.map(c=>{
  if(c._target[0]._property==='layerID')return {layerID:active};
  const id=c._target.find(x=>x._ref==='layer')._id,l=layers.find(x=>x.id===id);assert(l);
  if(c._obj==='select'){assert.equal(c.makeVisible,false);if(!c.selectionModifier)doc.activeLayers=[];doc.activeLayers.push(l);active=id;return {};}
  if(c._obj==='set'){
   sets++;assert.equal(Object.keys(c.to).length,2);assert.equal(c._target[1]._id,12);assert.equal(c._options.dialogOptions,'silent');
   if(failSet===sets)return {_obj:'error',message:'partial setter failure'};
   if(c.to.vectorMaskFeather)l.vectorMaskFeather=c.to.vectorMaskFeather._value;
   else if(c.to.vectorMaskDensity)l.vectorMaskDensity=c.to.vectorMaskDensity._value;
   else throw Error('Unexpected non-mask write');return {};
  }
  if(c._target[0]._property==='pathContents')return {pathContents:copy(l.path)};
  fullReads++;return {layerID:l.id,...copy(l.content)};
 })},core:{executeAsModal:async fn=>{try{return await fn({isCancelled:false,hostControl:{
  suspendHistory:async()=>{histories++;saved=layers.map(l=>({feather:l.vectorMaskFeather,density:l.vectorMaskDensity}));return 1;},
  resumeHistory:async(id,commit)=>{assert.equal(id,1);if(commit){if(failCommit)throw Error('commit unknown');commits++;}else {rollbacks++;if(failRollback)throw Error('rollback unknown');layers.forEach((l,i)=>{l.vectorMaskFeather=saved[i].feather;l.vectorMaskDensity=saved[i].density;});if(historyResetsSelection){doc.activeLayers=[layers[0]];active=layers[0].id;}}}
 } });}catch(e){throw Error(e.message);}}}};
 if(!legacy)ps.core.redrawDocument=async()=>{redraws++;};
 const api=create(ps,'session',{legacyPreview:legacy});const context=api.selectionContext(),data=await api.observeShape(context,true);assert.equal(data.available,true,JSON.stringify(data));
 const target=await api.capture(),paint={revision:data.revision,mask_batch:true,mask:{feather:12.5}},request={command:legacy?'shape.legacy.preview':'shape.preview',id:'a'.repeat(32),session:'session',...(legacy?{native_batch_validation:2}:{}),token:'test',expires_at_ms:Date.now()+10000,target,paint};
 const packet=(seq,phase='preview',mask={feather:12.5})=>({id:request.id,session:'session',token:'test',seq,phase,lease_until_ms:Date.now()+4000,paint:{...paint,mask}});
 const progress=[];const run=async packets=>api.setLabel(request,{read:async()=>packets.shift()||null,progress:async(stage,done,total,frame)=>{assert(done>=0&&done<=total);progress.push({stage,done,total,frame});}});
 return {api,data,layers,doc,request,packet,run,progress,resetSelectionOnRollback:()=>{historyResetsSelection=true;},state:()=>({sets,histories,commits,rollbacks,redraws,fullReads}),fail:(where)=>{if(where==='set')failSet=2;else if(where==='rollback'){failSet=2;failRollback=true;}else failCommit=true;},select:ids=>{doc.activeLayers=layers.filter(l=>ids.includes(l.id));active=ids.at(-1);}};
}
(async()=>{
 let cases=0;
 for(const n of [2,8,128]){
  const f=await fixture(n),original=f.layers.map(l=>[l.vectorMaskDensity,copy(l.content),copy(l.path)]);
  assert.equal(f.data.mixed.feather,true);assert.equal(f.data.active_layer_id,29+n);
  const result=await f.run([f.packet(1),f.packet(2,'preview',{feather:27}),f.packet(3,'commit',{feather:33})]);
  assert.equal(result.count,n);assert.equal(f.state().histories,1);assert.equal(f.state().commits,1);assert.equal(f.state().rollbacks,0);
  f.layers.forEach((l,i)=>{assert.equal(l.vectorMaskFeather,33);assert.equal(l.vectorMaskDensity,original[i][0]);assert.deepEqual(l.content,original[i][1]);assert.deepEqual(l.path,original[i][2]);});cases++;
 }
 {const f=await fixture();await f.run([f.packet(1,'preview',{density:20}),f.packet(2,'commit',{density:55})]);assert.deepEqual(f.layers.map(l=>l.vectorMaskFeather),[1,2]);assert.deepEqual(f.layers.map(l=>l.vectorMaskDensity),[55,55]);cases++;}
 {const f=await fixture();await f.run([f.packet(1,'preview',{feather:8}),f.packet(2,'commit',{feather:9,density:50})]);assert.deepEqual(f.layers.map(l=>[l.vectorMaskFeather,l.vectorMaskDensity]),[[9,50],[9,50]]);assert.equal(f.state().histories,1);cases++;}
 {const f=await fixture();const result=await f.run([f.packet(1),f.packet(2,'cancel')]);assert.equal(result.rollback_verified,true);assert.deepEqual(f.layers.map(l=>[l.vectorMaskFeather,l.vectorMaskDensity]),[[1,80],[2,79]]);assert.equal(f.state().commits,0);cases++;}
 for(const fail of [false,true]){const f=await fixture(8);f.resetSelectionOnRollback();if(fail)f.fail('set');
  if(fail)await assert.rejects(f.run([f.packet(1,'commit')]),e=>!e.resultUnknown);else assert.equal((await f.run([f.packet(1),f.packet(2,'cancel')])).rollback_verified,true);
  assert.deepEqual(await f.api.capture(),f.request.target);assert.deepEqual(f.layers.map(l=>l.vectorMaskFeather),[1,2,3,4,5,6,7,8]);assert.equal(f.state().rollbacks,1);cases++;
 }
 for(const kind of ['set','rollback','commit']){const f=await fixture();f.fail(kind);await assert.rejects(f.run([f.packet(1,'commit')]),e=>kind==='set'?!e.resultUnknown:e.resultUnknown===true);if(kind==='set')assert.deepEqual(f.layers.map(l=>l.vectorMaskFeather),[1,2]);cases++;}
 for(const kind of ['selection','locked','parent','mask','content','path','revision','session','expired']){
  const f=await fixture();
  if(kind==='selection')f.select([30]);if(kind==='locked')f.layers[0].allLocked=true;if(kind==='parent')f.layers[0].parent={id:99,allLocked:true,layers:f.layers,parent:null};
  if(kind==='mask')f.layers[0].content.hasVectorMask=false;if(kind==='content')f.layers[0].content.adjustment[0].color.red=255;if(kind==='path')f.layers[0].path.points=[8];
  if(kind==='revision')f.request.paint.revision='stale';if(kind==='session')f.request.target.session='stale';if(kind==='expired')f.request.expires_at_ms=0;
  await assert.rejects(f.run([f.packet(1,'commit')]));assert.equal(f.state().sets,0);cases++;
 }
 for(const mask of [{},{feather:-1},{density:101},{feather:NaN},{feather:true},{opacity:1}]){const f=await fixture();f.request.paint.mask=mask;await assert.rejects(f.run([]));assert.equal(f.state().sets,0);cases++;}
 {const f=await fixture();const p=f.packet(1);p.token='wrong';await assert.rejects(f.run([p]));assert.equal(f.state().rollbacks,1);cases++;}
 {const f=await fixture(2,true);const prepared=await f.api.prepareLegacyShape(f.request);assert.equal(f.state().histories,0);assert.equal(prepared.members.length,2);
  const result={verified:true,mask_batch:true,count:2,placement_moves:0,layer_ids:[30,31],paint:f.request.paint,masks:prepared.members.map(m=>({id:m.id,mask:{...m.mask,...f.request.paint.mask}})),preview:{engine:'standalone-extendscript',last_seq:1}};
  assert.equal((await f.api.finishLegacyShape(f.request,prepared,{phase:'completed',result})).count,2);
  result.masks[0].mask.density=0;await assert.rejects(f.api.finishLegacyShape(f.request,prepared,{phase:'completed',result}),e=>e.resultUnknown===true);cases++;
 }
 for(const cancel of [false,true]){const f=await fixture(8);await f.run([f.packet(1),f.packet(2,cancel?'cancel':'commit')]);
  assert(f.progress.some(p=>p.stage==='redraw'&&p.total===0));assert(f.progress.some(p=>p.stage==='verify'&&p.done===8));
  assert(f.progress.some(p=>p.stage===(cancel?'restore':'commit')));assert.equal(f.state().histories,1);cases++;}
 // Legacy handoff reads fresh identity, freezes the observed expected values,
 // and leaves the complete fresh content check to the native pre-write guard.
 for(const n of [2,128]){const f=await fixture(n,true),reads=f.state().fullReads;
  const observed=copy(f.layers.map(l=>l.content));f.layers[0].content.adjustment[0].color.red=234;
  const prepared=await f.api.prepareLegacyShape(f.request);
  assert.equal(prepared.native_batch_validation,2);assert.match(prepared.members[0].mask_exact.feather,/^[a-f0-9]{16}$/);assert.equal(prepared.members[0].mask_exact.density,Math.round(prepared.members[0].mask.density*255/100));
  assert.equal(f.state().fullReads,reads);assert.equal(f.state().histories,0);assert.equal(f.state().sets,0);
  assert.deepEqual(prepared.members[0].content,observed[0]);
  prepared.members[0].content.adjustment[0].color.red=123;
  assert.deepEqual((await f.api.prepareLegacyShape(f.request)).members[0].content,observed[0]);cases++;
 }
 for(const change of ['selection','document','revision','expired','session']){const f=await fixture(8,true);
  if(change==='selection')f.select([30,31]);if(change==='document')f.doc.id=99;
  if(change==='revision')f.request.paint.revision='old';if(change==='expired')f.request.expires_at_ms=0;
  if(change==='session')f.request.target.session='other';
  await assert.rejects(f.api.prepareLegacyShape(f.request));assert.equal(f.state().sets,0);assert.equal(f.state().histories,0);cases++;
 }
 for(const marker of [undefined,1,'2']){const f=await fixture(8,true);f.request.native_batch_validation=marker;const reads=f.state().fullReads;
  await f.api.prepareLegacyShape(f.request);assert(f.state().fullReads>reads);
  f.layers[0].vectorMaskFeather+=.001;await assert.rejects(f.api.prepareLegacyShape(f.request));assert.equal(f.state().sets,0);cases++;
 }
 console.log('PASS batch masks: '+cases+' cases, 2/8/128 layers, independent values, one history, cancel/rollback, path/content/order, stale and unknown guards');
})().catch(e=>{console.error(e);process.exit(1);});
