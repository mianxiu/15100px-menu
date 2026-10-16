// Production poll loop with a simulated slow DOM/color read. No real PS claim.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const code=process.argv.includes('--baseline')?require('node:child_process').execFileSync('git',['show','HEAD:uxp/offline-probe/main.js'],{encoding:'utf8'}):fs.readFileSync('uxp/offline-probe/main.js','utf8');
const settle=async()=>{for(let i=0;i<30;i++)await new Promise(resolve=>setImmediate(resolve));};
async function host(){
 const files=new Map(),control={now:Date.now(),cost:0,reads:0,shapes:0,kind:'shape-fill',ids:[7],changed:false};
 let poll,release,releaseRead;
 const context=()=>{control.reads++;control.now+=control.cost;return {session:control.session,schema:1,document_id:1,layer_ids:control.ids,kind:control.kind,mask:15,quick_mask:127};};
 const folder={async getEntry(name){if(!files.has(name))throw Error('missing');return {async read(){return files.get(name);}};},async createFile(name){return {async write(raw){files.set(name,raw);}};}};
 const labels={selectionContext:context,selectionContextFresh:async()=>{if(control.readBlock)await new Promise(r=>{releaseRead=r;});return context();},selectionMatches:()=>!control.changed,interfacePreferences:async()=>({}),
   observeShape:async()=>{control.shapes++;if(control.block)await new Promise(r=>{release=r;});if(control.shapeFail)throw Error('color unavailable');
     return {available:true,revision:'s:1'};}};
 const sandbox={console:{log(){}},module:{exports:{}},Date:class extends Date{static now(){return control.now;}},setInterval(fn){poll=fn;},require(name){
   if(name==='./labels.js')return (ps,session)=>{control.session=session;return labels;};if(name==='./probe-config.js')return 'token';
   if(name==='photoshop')return {app:{documents:[]},action:{addNotificationListener(){}}};
   if(name==='uxp')return {storage:{localFileSystem:{getDataFolder:async()=>folder,getPluginFolder:async()=>{throw Error('no manifest');}}},host:{},versions:{}};
   throw Error(name);
 }};
 vm.runInNewContext(code,sandbox);await settle();
 const session=JSON.parse(files.get('probe-last.json')).session;
 const request=(id='a'.repeat(32),values={})=>files.set('menu-context-request.json',JSON.stringify({id,session,token:'token',expires_at_ms:control.now+9000,...values}));
 return {files,control,poll:()=>poll(),request,release:()=>release(),releaseRead:()=>releaseRead(),result:()=>JSON.parse(files.get('menu-context-result.json'))};
}
async function main(){
 let h=await host();assert.equal(h.control.shapes,0,'Idle polling must not read vector metadata or preset catalogs');
 h.control.cost=3400;h.control.block=true;h.request();h.poll();await settle();
 assert.equal(h.result().menu_phase,'basic','Slow color read must not block ordinary layer capabilities');
 assert.equal(h.result().mask,15);assert.equal(h.result().timings_ms.selection_ms,3400);
 assert.equal(h.control.shapes,1);const before=h.control.reads;
 h.control.now+=3500;h.release();await settle();
 assert.equal(h.result().menu_phase,'completed');assert.equal(h.result().shape_editor.available,true);
 assert.ok(h.control.reads>before,'Slow color completion rereads eligibility instead of retimestamping old locks');
 assert.equal(h.result().plugin_time_ms,h.control.now);
 const shapes=h.control.shapes;await h.poll();await settle();assert.equal(h.control.shapes,shapes,'Completed menu ID must not be reread');
 h=await host();h.control.block=true;h.request();h.poll();await settle();h.control.changed=true;h.release();await settle();
 assert.equal(h.result().menu_phase,'basic','Changed identity must never publish paint metadata');
 h=await host();h.control.shapeFail=true;h.request();await h.poll();await settle();
 assert.equal(h.result().menu_phase,'completed');assert.equal(h.result().mask,15);assert.equal(h.result().shape_editor.available,false);
 h=await host();h.control.kind='pixel';h.request();await h.poll();await settle();
 assert.equal(h.result().menu_phase,'completed');assert.equal(h.control.shapes,0,'Ordinary layers must not read vector metadata');
 h=await host();h.request('b'.repeat(32),{token:'wrong'});await h.poll();await settle();assert.equal(h.files.has('menu-context-result.json'),false);
 h.request('c'.repeat(32),{expires_at_ms:h.control.now-1});await h.poll();await settle();assert.equal(h.files.has('menu-context-result.json'),false);
 h=await host();h.control.kind='pixel';h.control.readBlock=true;
 h.request('a'.repeat(32));h.poll();await settle();
 h.request('b'.repeat(32));h.releaseRead();await settle();
 assert.equal(h.result().menu_request_id,'a'.repeat(32),'An awaited old read must retain its original request ID');
 h.control.readBlock=false;await h.poll();await settle();
 assert.equal(h.result().menu_request_id,'b'.repeat(32),'A newer menu gets its own fresh read, never the previous result');
 console.log('PASS: slow basic/paint reads; basic before paint; fresh eligibility; identity/expiry/token fences; paint failure; no idle color reads');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
