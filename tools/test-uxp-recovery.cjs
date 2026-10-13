const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const code=fs.readFileSync(require('node:path').join(__dirname,'../uxp/offline-probe/main.js'),'utf8');
const immediate=()=>new Promise(resolve=>setImmediate(resolve));
async function settle(){for(let i=0;i<25;i++)await immediate();}
function host(files,control) {
  let interval;
  const folder={
    async getEntry(name){if(!files.has(name))throw Error('missing');return entry(name);},
    async createFile(name){if(!files.has(name))files.set(name,'');return entry(name);}
  };
  function entry(name){return {
    async read(){return files.get(name);},
    async write(raw){
      const data=JSON.parse(raw);
      if(name.startsWith('result-') && data.phase!=='accepted' && control.failFinal>0){control.failFinal--;throw Error('storage offline');}
      if(name.startsWith('result-') && data.phase==='accepted' && control.failAccepted){throw Error('disk full');}
      files.set(name,raw);
    },
    async delete(){files.delete(name);}
  };}
  const labels={selectionContext:()=>{control.contextReads=(control.contextReads||0)+1;return {kind:control.executed?'pixel':'none',layer_ids:control.executed?[99]:[]};},documentTarget:()=>({document_ids:[]}),capture:async()=>({}),
    setLabel:async request=>{
      const saved=JSON.parse(files.get('result-'+request.id+'.json'));
      assert.equal(saved.phase,'accepted');control.executed++;
      if(control.unknown){const e=Error('rollback uncertain');e.resultUnknown=true;throw e;}
      return {count:1,verified:true};
    },createDocument:async()=>{control.created++;return {document_id:99};}};
  const context={console:{log(){}},setInterval(fn){interval=fn;},module:{exports:{}},require(name){
    if(name==='./probe-config.js')return 'secret';
    if(name==='./labels.js')return ()=>labels;
    if(name==='photoshop')return {app:{documents:[]},action:{addNotificationListener(){}}};
    if(name==='uxp')return {storage:{localFileSystem:{getDataFolder:async()=>folder,getPluginFolder:async()=>{throw Error('not needed');}}},host:{version:'24.0.1'},versions:{uxp:'6.3.3'}};
    throw Error(name);
  }};
  vm.runInNewContext(code,context);
  return {poll:()=>interval(),command:()=>context.module.exports.commands.probe()};
}
function request(files,id='a'.repeat(32),operation='set_label') {
  files.set('probe-request.json',JSON.stringify({id,token:'secret',operation,expires_at_ms:Date.now()+5000}));
}
async function main(){
  let files=new Map(),control={executed:0,created:0,failFinal:2};
  let plugin=host(files,control);await settle();request(files);
  const reads=control.contextReads;
  await plugin.command();assert.equal(control.executed,1);
  assert.equal(control.contextReads,reads+1,'Committed work refreshes selection before its final receipt');
  assert.deepEqual(JSON.parse(files.get('layer-context.json')).layer_ids,[99]);
  assert.equal(JSON.parse(files.get('result-'+ 'a'.repeat(32)+'.json')).phase,'accepted');
  await plugin.command();assert.equal(control.executed,1);
  await plugin.command();assert.equal(control.executed,1);
  const receipt=JSON.parse(files.get('result-'+ 'a'.repeat(32)+'.json'));
  assert.equal(receipt.phase,'completed');assert.ok(receipt.session);assert.equal(receipt.schema,1);
  assert.deepEqual(receipt.layer_context.layer_ids,[99]);
  assert.deepEqual(receipt.layer_context,JSON.parse(files.get('layer-context.json')));
  // Reload with the exact original, unexpired request still in the IPC slot.
  plugin=host(files,control);await settle();await plugin.command();assert.equal(control.executed,1);
  request(files,'b'.repeat(32),'new_document');await plugin.command();assert.equal(control.created,1);
  plugin=host(files,control);await settle();assert.equal(control.created,1);
  files=new Map();control={executed:0,created:0,failFinal:0,unknown:true};
  plugin=host(files,control);await settle();request(files);await plugin.command();
  assert.equal(control.executed,1);assert.equal(JSON.parse(files.get('result-'+ 'a'.repeat(32)+'.json')).result_unknown,true);
  plugin=host(files,control);await settle();assert.equal(control.executed,1);
  files=new Map();control={executed:0,created:0,failFinal:0,failAccepted:true};
  plugin=host(files,control);await settle();request(files);await plugin.command();assert.equal(control.executed,0);
  console.log('PASS: durable acceptance before mutation; final-write retry without replay; reload dedupe; unknown retained; new-document receipt; disk failure prevents mutation');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
