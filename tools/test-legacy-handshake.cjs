// The legacy reservation must NOT enter executeAsModal or query PS while JSX runs.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('uxp/offline-probe/main.js','utf8');
async function exercise(failure=false,host='24.0.1'){
 const files=new Map(),queries=[];let tick,prepares=0,finishes=0;
 const folder={createFile:async name=>({write:async text=>files.set(name,text)}),getEntry:async name=>{if(!files.has(name))throw Error('missing');return {read:async()=>files.get(name)};}};
 const app={documents:[{title:'Owned'}],activeDocument:{title:'Owned'}};
 const labels={interfacePreferences:async()=>{queries.push('preferences');return {};},selectionContext:()=>{queries.push('selection');return {kind:'pixel',layer_ids:[2]};},
  prepareLegacyShape:async()=>{prepares++;return {before:{revision:'r'}};},finishLegacyShape:async(request,prepared,result)=>{finishes++;assert.equal(result.id,request.id);if(failure){const e=Error('rollback unconfirmed');e.resultUnknown=true;throw e;}return {verified:true,selection_context:{kind:'pixel',layer_ids:[2]}};}};
 const context={module:{exports:{}},console,Date,setTimeout,clearTimeout,setInterval:(fn,ms)=>{if(ms===16)tick=fn;},
  require:name=>name==='photoshop'?{app,core:{executeAsModal:()=>{throw Error('No modal in legacy handshake');}},action:{addNotificationListener:()=>{}}}:name==='uxp'?{host:{version:host},versions:{uxp:'6'},storage:{localFileSystem:{getDataFolder:async()=>folder,getPluginFolder:async()=>({getEntry:async()=>({read:async()=>JSON.stringify({name:'Owned',entrypoints:[{label:{default:'Probe'}}]})})})}}}:name==='./labels.js'?()=>labels:'token',fetch:()=>{throw Error('No network');}};
 vm.runInNewContext(source,context);await new Promise(r=>setImmediate(r));
 const heartbeat=JSON.parse(files.get('probe-last.json'));assert.equal(heartbeat.legacy_preview_available,true);
 const id=(failure?'b':'a').repeat(32),request={id,session:heartbeat.session,token:'token',operation:'set_label',command:'shape.legacy.preview',expires_at_ms:Date.now()+5000};
 files.set('probe-request.json',JSON.stringify(request));const pending=tick();await new Promise(r=>setImmediate(r));
 assert.equal(prepares,1);const prepared=JSON.parse(files.get('legacy-prepared-'+id+'.json'));assert.equal(prepared.id,id);
 const count=queries.length;await tick();assert.equal(queries.length,count,'Worker reservation must suppress background PS reads');
 files.set('legacy-result-'+id+'.json',JSON.stringify({...request,schema:1,session:'forged',phase:'completed',result:{verified:true}}));
 await new Promise(r=>setTimeout(r,55));assert.equal(finishes,0,'Reject a wrong-session native receipt');
 files.set('legacy-result-'+id+'.json',JSON.stringify({...request,schema:1,phase:'completed',result:{verified:true}}));
 await new Promise(r=>setTimeout(r,55));assert.equal(finishes,0,'A JSX receipt before normal COM return cannot finish the worker');
 files.set('legacy-exited-'+id+'.json',JSON.stringify({...request,schema:1,exited:true,session:'other'}));
 await new Promise(r=>setTimeout(r,55));assert.equal(finishes,0,'Exit acknowledgement must belong to this request/session/token');
 files.set('legacy-exited-'+id+'.json',JSON.stringify({...request,schema:1,exited:true}));await pending;
 const terminal=JSON.parse(files.get('result-'+id+'.json'));assert.equal(finishes,1);assert.equal(terminal.phase,failure?'failed':'completed');
 if(failure)assert.equal(terminal.result_unknown,true);
 await tick();assert.equal(prepares,1,'Consumed request must not be replayed');
}
(async()=>{for(const host of ['24.0.0','24.0.1']){await exercise(false,host);await exercise(true,host);}console.log('PASS legacy handshake 24.0.0/24.0.1: native reservation without modal or host reads; token/session fencing, terminal persistence, unknown preservation and no replay');})().catch(e=>{console.error(e);process.exitCode=1;});
