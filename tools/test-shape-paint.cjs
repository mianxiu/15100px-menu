const assert=require('node:assert/strict');
const create=require('../uxp/offline-probe/labels.js');
const copy=v=>JSON.parse(JSON.stringify(v));
async function main(){
 const layer={id:30,kind:'solid',parent:null,vectorMaskFeather:0,vectorMaskDensity:100},doc={id:12,activeLayers:[layer],layers:[layer],mode:'rgb',bitsPerChannel:8,resolution:144};
 let fill={_obj:'solidColorLayer',color:{_obj:'RGBColor',red:12,grain:34,blue:56}};
 let stroke={_obj:'strokeStyle',strokeStyleVersion:2,strokeEnabled:false,fillEnabled:true,
  strokeStyleLineWidth:{_unit:'pointsUnit',_value:1},strokeStyleLineCapType:{_enum:'strokeStyleLineCapType',_value:'strokeStyleRoundCap'},
  strokeStyleContent:{_obj:'solidColorLayer',color:{_obj:'RGBColor',red:0,grain:0,blue:0}}};
 let gets=0,sets=0,history=0,rollbacks=0,vector=true,mismatch=false,rollbackFailure=false,saved;
 let maskFeather=0,maskDensity=100,maskReads=0,maskSetFailure=false;
 Object.defineProperties(layer,{
  vectorMaskFeather:{get(){maskReads++;return maskFeather;},set(value){maskFeather=value;}},
  vectorMaskDensity:{get(){maskReads++;return maskDensity;},set(value){if(maskSetFailure)throw Error('mask setter refused');maskDensity=value;}}
 });
 const ps={constants:{LayerKind:{SOLIDFILL:'solid',NORMAL:'pixel'},DocumentMode:{RGB:'rgb'},BitsPerChannelType:{EIGHT:8,SIXTEEN:16}},
 app:{documents:[doc],activeDocument:doc},action:{batchPlay:async commands=>commands.map(c=>{
  if(c._obj==='set'){sets++;if(c.to._obj==='shapeStyle'){if(c.to.fillContents)fill=copy(c.to.fillContents);if(c.to.strokeStyle)stroke=copy(c.to.strokeStyle);}else fill=copy(c.to);if(mismatch==='armed')mismatch=true;return {};}
  gets++;const key=c._target[0]._property;
  if(key==='layerKind')return {layerKind:4};
  if(key==='hasVectorMask')return {hasVectorMask:vector};
  if(key==='adjustment')return {adjustment:[mismatch===true?{...fill,color:{_obj:'RGBColor',red:99,grain:99,blue:99}}:copy(fill)]};
  if(key==='AGMStrokeStyleInfo')return {AGMStrokeStyleInfo:copy(stroke)};
  if(key==='presetManager')return {presetManager:[{_obj:'PttR',name:['Loaded Pattern']}]};
  throw Error('Unexpected get '+key);
 })},core:{executeAsModal:async fn=>fn({hostControl:{suspendHistory:async()=>{history++;saved={fill:copy(fill),stroke:copy(stroke),maskFeather,maskDensity};return 1;},
 resumeHistory:async(id,commit)=>{if(!commit){rollbacks++;if(rollbackFailure)throw Error('rollback failure');fill=saved.fill;stroke=saved.stroke;maskFeather=saved.maskFeather;maskDensity=saved.maskDensity;}}}})}};
 const api=create(ps,'s'),target=await api.capture();
 const inspect=()=>api.observeShape(api.selectionContext(),true);
 let data=await inspect();assert.equal(data.stroke.width,2);assert.deepEqual(data.patterns,['Loaded Pattern']);assert.deepEqual(data.mask,{feather:0,density:100});
 const reads=gets;await api.observeShape(api.selectionContext());assert.equal(gets,reads);assert.equal(sets,0);assert.equal(history,0);
 const request=d=>({command:'shape.paint',target,expires_at_ms:Date.now()+10000,paint:{revision:d.revision,fill:copy(d.fill),stroke:copy(d.stroke)}});
 let r=request(data);r.paint.fill.rgb=[200,30,10];r.paint.stroke.enabled=true;
 assert.equal((await api.setLabel(r)).verified,true);assert.equal(sets,1);assert.equal(history,1);
 assert.equal(stroke.strokeStyleLineCapType._value,'strokeStyleRoundCap');
 await assert.rejects(api.setLabel(r),/已改变/);assert.equal(sets,1);assert.equal(history,1);
 data=await inspect();r=request(data);r.paint.mask={feather:8.5,density:62.5};
 // Parameter key order differs after backend normalization; mask-only edits
 // must not rewrite shapeStyle, colors, gradients or vector path data.
 r.paint.fill={kind:data.fill.kind,enabled:data.fill.enabled,rgb:copy(data.fill.rgb)};
 const maskOnlySets=sets;await api.setLabel(r);assert.equal(sets,maskOnlySets);
 assert.equal(layer.vectorMaskFeather,8.5);assert.equal(layer.vectorMaskDensity,62.5);
 data=await inspect();r=request(data);r.paint.mask={feather:10,density:20};layer.vectorMaskDensity=75;
 const maskHistory=history;await assert.rejects(api.setLabel(r),/已改变/);assert.equal(history,maskHistory);assert.equal(layer.vectorMaskDensity,75);
 data=await inspect();for(const invalid of [null,{feather:-1,density:100},{feather:2,density:101},{feather:NaN,density:100}]){
  r=request(data);r.paint.mask=invalid;await assert.rejects(api.setLabel(r),/Invalid vector mask/);
 }
 r=request(data);r.paint.mask={feather:25,density:20};const oldMask=copy(data.mask);maskSetFailure=true;
 await assert.rejects(api.setLabel(r),/mask setter refused/);maskSetFailure=false;
 assert.deepEqual((await inspect()).mask,oldMask);assert.equal(rollbacks,1);
 const finalMaskHistory=history;
 data=await inspect();r=request(data);r.target={...target,document_id:99};await assert.rejects(api.setLabel(r));assert.equal(history,finalMaskHistory);
 data=await inspect();r=request(data);r.paint.fill={kind:'gradient',enabled:true,stops:[{rgb:[0,0,0],location:0},{rgb:[255,255,255],location:4096}]};
 await api.setLabel(r);assert.equal(fill._obj,'gradientLayer');assert.equal(fill.gradient.transparency.length,2);
 fill.angle._value=40;fill.gradient.colors[0].midpoint=37;fill.gradient.transparency[0].opacity._value=80;
 data=await inspect();r=request(data);r.paint.fill.stops[0].rgb=[0,20,40];await api.setLabel(r);
 assert.equal(fill.angle._value,40);assert.equal(fill.gradient.colors[0].midpoint,37);assert.equal(fill.gradient.transparency[0].opacity._value,80);
 data=await inspect();r=request(data);r.paint.fill={kind:'pattern',enabled:true,name:'Loaded Pattern'};await api.setLabel(r);assert.equal(fill.pattern.name,'Loaded Pattern');
 data=await inspect();r=request(data);r.paint.fill.name='Removed Pattern';const before=history;await assert.rejects(api.setLabel(r),/图案预设/);assert.equal(history,before);
 layer.allLocked=true;assert.equal((await inspect()).available,false);layer.allLocked=false;
 const vectorFill=copy(fill),vectorStroke=copy(stroke);
 vector=false;fill={_obj:'solidColorLayer',color:{_obj:'RGBColor',red:12,grain:34,blue:56}};
 const maskReadsBeforeFill=maskReads;data=await inspect();assert.equal(data.available,true);assert.equal(data.vector,false);assert.equal(maskReads,maskReadsBeforeFill);
 assert.equal(data.mask,undefined);r=request(data);r.paint.mask={feather:0,density:100};await assert.rejects(api.setLabel(r),/不支持矢量蒙版/);
 r=request(data);r.paint.stroke={width:data.stroke.width,rgb:copy(data.stroke.rgb),enabled:data.stroke.enabled,kind:data.stroke.kind};
 r.paint.fill={kind:'solid',enabled:true,rgb:[30,60,90]};await api.setLabel(r);
 assert.deepEqual(fill.color,{_obj:'RGBColor',red:30,grain:60,blue:90});assert.deepEqual(stroke,vectorStroke);
 data=await inspect();r=request(data);r.paint.stroke.enabled=true;const fillSets=sets;
 await assert.rejects(api.setLabel(r),/普通填充层/);assert.equal(sets,fillSets);
 r=request(data);r.paint.fill.enabled=false;await assert.rejects(api.setLabel(r),/普通填充层/);assert.equal(sets,fillSets);
 r=request(data);r.paint.fill={kind:'pattern',enabled:true,name:'Loaded Pattern'};await assert.rejects(api.setLabel(r),/原生类型/);assert.equal(sets,fillSets);
 vector=true;fill=vectorFill;stroke=vectorStroke;
 doc.mode='cmyk';assert.equal((await inspect()).available,false);doc.mode='rgb';
 doc.activeLayers=[layer,{id:31,kind:'solid'}];assert.equal((await inspect()).available,false);doc.activeLayers=[layer];
 data=await inspect();r=request(data);r.paint.fill={kind:'solid',enabled:true,rgb:[20,40,60]};mismatch='armed';
 await assert.rejects(api.setLabel(r),/回滚/);assert.equal(rollbacks,2);assert.equal(fill._obj,'patternLayer');
 mismatch=false;data=await inspect();r=request(data);r.paint.fill={kind:'solid',enabled:true,rgb:[20,40,60]};mismatch='armed';rollbackFailure=true;
 await assert.rejects(api.setLabel(r),e=>e.resultUnknown===true);assert.equal(rollbacks,3);
 console.log('PASS shape: cached targeted gets; vector/RGB/lock/multi/revision identity; one history; solid/gradient/pattern; preserved stroke/alpha; rollback and unknown never replay');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
