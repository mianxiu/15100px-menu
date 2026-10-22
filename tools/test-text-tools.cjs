const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('uxp/offline-probe/labels.js','utf8');
const clone=value=>JSON.parse(JSON.stringify(value));
const original={layerID:11,name:'mixed',layerKind:3,layerLocking:{protectAll:false},textKey:{_obj:'textLayer',textKey:'A猫😀\rBC猫',
 textStyleRange:[{_obj:'textStyleRange',from:0,to:2,textStyle:{fontPostScriptName:'Alpha',size:12,color:{red:1}}},{_obj:'textStyleRange',from:2,to:5,textStyle:{fontPostScriptName:'Beta',size:16}},{_obj:'textStyleRange',from:5,to:9,textStyle:{fontPostScriptName:'Gamma',size:20}}],
 paragraphStyleRange:[{_obj:'paragraphStyleRange',from:0,to:5,paragraphStyle:{align:'left'}},{_obj:'paragraphStyleRange',from:5,to:9,paragraphStyle:{align:'center'}}],
 antiAlias:{_value:'antiAliasCrisp'},textClickPoint:{x:1,y:2},orientation:'horizontal',textShape:[{char:{_value:'paint'},transform:{xx:1,yy:1}}],warp:{style:'none'},kerningRange:[]}};
let row=clone(original),target={session:'s',document_id:1,active_layer_id:11,layer_ids:[11]},before,history=0,commits=0,writes=0,failWrite=false,wrongStyle=false,rollbackFail=false,materializeParagraphs=false;
const ps={core:{executeAsModal:async fn=>fn({isCancelled:false,hostControl:{suspendHistory:async()=>{history++;before=clone(row);return 'h';},resumeHistory:async(_,commit)=>{if(commit)commits++;else{if(rollbackFail)throw Error('rollback');row=before;}}}})},action:{batchPlay:async commands=>commands.map(c=>{
 assert.equal(c._options.dialogOptions,'silent');
 if(c._obj==='multiGet')return clone(row);
 if(c._obj==='set'){
  assert.equal(c._target.length,1);assert.equal(c._target[0]._ref,'textLayer');assert.equal(c._target[0]._value,'targetEnum');
  writes++;if(failWrite)return {_obj:'error'};
  row.textKey={...row.textKey,antiAlias:{_value:'antiAliasSharp'},...clone(c.to)};
  if(!c.to.paragraphStyleRange)row.textKey.paragraphStyleRange=[{...clone(row.textKey.paragraphStyleRange[0]),from:0,to:row.textKey.textKey.length+1}];
  if(materializeParagraphs && c.to.paragraphStyleRange)for(const range of row.textKey.paragraphStyleRange)range.paragraphStyle={align:'left',hyphenate:false,...range.paragraphStyle};
  if(wrongStyle)row.textKey.textStyleRange[0].textStyle.fontPostScriptName='Wrong';
  return {};
 }
 throw Error(c._obj);
})}};
const context={ps,session:'s',capture:async()=>clone(target)};
vm.createContext(context);vm.runInContext(source.slice(source.lastIndexOf('function createTextTools('))+'\nthis.tools=createTextTools(ps,session,capture);',context);
const tools=context.tools;
async function request(find,replacement){const read=await tools.read();return {target:read.target,text:{revision:read.revision,find,replacement},expires_at_ms:Date.now()+5000};}
(async()=>{
 let req=await request('猫','XY');assert.equal(writes,0);
 const result=await tools.replace(req);assert.equal(result.count,2);assert.equal(row.textKey.textKey,'AXY😀\rBCXY');assert.equal(history,1);assert.equal(commits,1);
 assert.deepEqual(row.textKey.textStyleRange.map(r=>[r.from,r.to,r.textStyle.fontPostScriptName]),[[0,3,'Alpha'],[3,6,'Beta'],[6,11,'Gamma']]);
 assert.deepEqual(row.textKey.paragraphStyleRange.map(r=>[r.from,r.to]),[[0,6],[6,11]]);
 assert.deepEqual(row.textKey.antiAlias,original.textKey.antiAlias);
 await assert.rejects(tools.replace(req),/已过期/);
 row=clone(original);row.textKey.textStyleRange.splice(1,0,clone(row.textKey.textStyleRange[0]));req=await request('猫','x');await tools.replace(req);assert.equal(row.textKey.textKey,'Ax😀\rBCx');
 row=clone(original);row.textKey.textStyleRange.splice(1,0,{...clone(row.textKey.textStyleRange[0]),textStyle:{fontPostScriptName:'Wrong',size:12}});await assert.rejects(tools.read(),/样式范围/);
 row=clone(original);row.textKey.textStyleRange[0].textStyle.styleSheetHasParent=true;const differentParent=clone(row.textKey.textStyleRange[0]);differentParent.textStyle.styleSheetHasParent=false;row.textKey.textStyleRange.splice(1,0,differentParent);await assert.rejects(tools.read(),/样式范围/);
 row=clone(original);materializeParagraphs=true;for(const range of row.textKey.paragraphStyleRange)range.paragraphStyle={styleSheetHasParent:true,textComposerEngine:{_value:'textOptycaComposer'}};
 req=await request('猫','x');await tools.replace(req);assert.ok(row.textKey.paragraphStyleRange.every(r=>!('align' in r.paragraphStyle)));materializeParagraphs=false;
 row=clone(original);req=await request('A猫😀','');await tools.replace(req);assert.equal(row.textKey.textKey,'\rBC猫');assert.equal(row.textKey.textStyleRange[0].textStyle.fontPostScriptName,'Beta');
 row=clone(original);req=await request('\n',' ');await tools.replace(req);assert.equal(row.textKey.paragraphStyleRange.length,1);assert.equal(row.textKey.paragraphStyleRange[0].paragraphStyle.align,'left');
 row=clone(original);req=await request('BC猫','尾');await tools.replace(req);assert.equal(row.textKey.textStyleRange.at(-1).textStyle.fontPostScriptName,'Gamma');
 row=clone(original);req=await request('x','y');const oldHistory=history;await tools.replace(req);assert.equal(history,oldHistory);
 req=await request('猫','猫');await tools.replace(req);assert.equal(history,oldHistory);
 req=await request('猫','x');row.textKey.textStyleRange[0].textStyle.size=50;const oldWrites=writes;await assert.rejects(tools.replace(req),/样式已改变/);assert.equal(writes,oldWrites);
 row=clone(original);req=await request('猫','x');target.layer_ids=[22];await assert.rejects(tools.replace(req),/单选|改变/);target.layer_ids=[11];
 row=clone(original);req=await request('猫','x');failWrite=true;await assert.rejects(tools.replace(req),/写入失败/);assert.deepEqual(row,original);failWrite=false;
 row=clone(original);req=await request('猫','x');wrongStyle=true;await assert.rejects(tools.replace(req),/读回不一致/);assert.deepEqual(row,original);wrongStyle=false;
 req=await request('猫','x');failWrite=true;rollbackFail=true;await assert.rejects(tools.replace(req),error=>error.resultUnknown===true);failWrite=false;rollbackFail=false;
 row=clone(original);row.textKey.textStyleRange[0].textStyle.fontAvailable=false;await assert.rejects(tools.read(),/缺失字体/);
 row=clone(original);row.textKey.kerningRange=[{from:0,to:1}];await assert.rejects(tools.read(),/手动字距/);
 row=clone(original);row.textKey.textStyleRange[1].from=3;await assert.rejects(tools.read(),/样式范围/);
 row=clone(original);req=await request('猫','x');req.expires_at_ms=0;await assert.rejects(tools.replace(req),/已取消/);
 console.log('Text tools: mixed styles, UTF-16, paragraph ranges, no-op, stale target, missing fonts, rollback and unknown passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
