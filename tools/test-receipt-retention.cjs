const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const code=process.argv.includes('--baseline')?require('node:child_process').execFileSync('git',['show','HEAD:uxp/offline-probe/main.js'],{encoding:'utf8'}):fs.readFileSync('uxp/offline-probe/main.js','utf8');
const body=code.slice(code.indexOf('async function finishResponse('),code.indexOf('async function updateLayerContext('));
const files=new Map(),deleted=[];
const prefixes=['result-','mask-preview-','mask-preview-status-','preview-progress-','execution-','legacy-prepared-','legacy-result-','legacy-exited-'];
const folder={async getEntry(name){if(!files.has(name))throw Error('missing');return {async delete(){deleted.push(name);files.delete(name);}};}};
const ctx={record:async(f,n,v)=>{files.set(n,v);},completedReceipts:[],pendingResponse:null,activeExecution:null};
vm.createContext(ctx);vm.runInContext(body+';this.finish=finishResponse;',ctx);
async function complete(id,unknown=false){
  for(const prefix of prefixes)files.set(prefix+id+'.json',{id});
  await ctx.finish(folder,{id,session:'s',phase:unknown?'failed':'completed',result_unknown:unknown});
}
(async()=>{
  // Original unknown/accepted and previous-session evidence must stay intact.
  await complete('unknown',true);
  for(const prefix of prefixes)files.set(prefix+'previous-session.json',{phase:'accepted'});
  for(let i=0;i<160;i++)await complete(String(i));
  for(let i=0;i<160;i++)for(const prefix of prefixes)
    assert.equal(files.has(prefix+i+'.json'),i>=96,`${prefix}${i} retention`);
  for(const id of ['unknown','previous-session'])for(const prefix of prefixes)
    assert.ok(files.has(prefix+id+'.json'),`preserve ${id} ${prefix}`);
  assert.equal(ctx.completedReceipts.length,64);
  console.log('PASS 160 completions keep 64 receipt families, including progress/exit; unknown/previous-session proof preserved');
})().catch(e=>{console.error(e);process.exitCode=1;});
