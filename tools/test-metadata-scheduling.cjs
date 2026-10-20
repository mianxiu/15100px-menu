// Production worker ordering with controlled host waits. No real PS claim.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('uxp/offline-probe/main.js','utf8');
const settle=async()=>{for(let n=0;n<30;n++)await new Promise(resolve=>setImmediate(resolve));};
async function host(initialCommand=false){
  const files=new Map(),c={now:100000,captures:0,preferences:0,documents:0,selection:0};
  const timers=new Map();let release;
  const folder={async getEntry(name){if(!files.has(name))throw Error('missing');return {read:async()=>files.get(name)};},
    async createFile(name){return {write:async text=>files.set(name,text)};}};
  const snapshot=()=>({session:c.session,document_id:1,layer_ids:[2],kind:'pixel',mask:15,quick_mask:127});
  const labels={selectionContextFresh:async checkpoint=>{if(checkpoint)await checkpoint();c.selection++;return snapshot();},
    interfacePreferences:async()=>{c.preferences++;if(c.block)await new Promise(resolve=>{release=resolve;});return {ui_theme:'light-gray',ui_font_size:'large',ui_preferences_complete:true,ui_preferences_time_ms:c.now};},
    capture:async()=>{c.captures++;return snapshot();},documentTarget:()=>({document_ids:[1]}),paintClipboardAvailable:()=>false};
  const app={get documents(){c.documents++;if(c.onDocuments)c.onDocuments();return [{title:'original'}];},activeDocument:{title:'original'}};
  function command(id){files.set('probe-request.json',JSON.stringify({token:'token',id,operation:'capture',expires_at_ms:c.now+9000}));}
  if(initialCommand)command('initial');
  const sandbox={console,Date:class extends Date{static now(){return c.now;}},module:{exports:{}},
    setInterval(fn,ms){timers.set(ms,fn);},setTimeout,clearTimeout,
    require(name){
      if(name==='photoshop')return {app,action:{addNotificationListener(){}},core:{}};
      if(name==='uxp')return {host:{version:'24.2.0'},versions:{uxp:'6.4'},storage:{localFileSystem:{getDataFolder:async()=>folder,getPluginFolder:async()=>{throw Error('optional');}}}};
      if(name==='./labels.js')return (ps,session)=>{c.session=session;return labels;};
      if(name==='./probe-config.js')return 'token';throw Error(name);
    }};
  vm.runInNewContext(source,sandbox);await settle();
  return {files,c,command,poll:()=>timers.get(16)(),pulse:()=>timers.get(1500)(),release:()=>release(),
    heartbeat:()=>JSON.parse(files.get('probe-last.json')),layer:()=>files.get('layer-context.json'),
    menu:()=>files.set('menu-context-request.json',JSON.stringify({token:'token',session:c.session,id:'a'.repeat(32),expires_at_ms:c.now+9000}))};
}
(async()=>{
  let h=await host(true);
  assert.equal(h.c.captures,1);assert.equal(h.c.preferences,0);assert.equal(h.c.documents,0);
  assert.equal(h.heartbeat().metadata_time_ms,0);assert.equal(h.heartbeat().metadata_phase,'pending');
  h.c.now+=100;await h.poll();assert.equal(h.c.preferences,1);assert.equal(h.c.documents,1);
  assert.equal(h.heartbeat().metadata_time_ms,h.c.now);assert.equal(h.heartbeat().document_name,'original');
  const preferencesAt=h.heartbeat().ui_preferences_time_ms;
  for(let n=0;n<12;n++){h.c.now+=6000;await h.poll();}
  assert.equal(h.c.preferences,1,'Successful startup preferences must not be polled');
  assert.equal(h.heartbeat().ui_preferences_time_ms,preferencesAt);
  assert.equal(h.c.documents,13,'Document metadata still changes independently');
  // A due metadata refresh must not precede either command or basic menu read.
  for(const kind of ['command','menu']){
    h=await host();h.c.now+=6000;const before={...h.c};
    if(kind==='command')h.command('capture-due');else h.menu();
    await h.poll();assert.equal(h.c.preferences,before.preferences);assert.equal(h.c.documents,before.documents);
    if(kind==='command')assert.equal(h.c.captures,1);
    else assert.equal(JSON.parse(h.files.get('menu-context-result.json')).menu_phase,'completed');
  }
  // JS liveness during an awaited metadata getter never freshens selection,
  // metadata, or execution evidence; commands wait for that original call.
  h=await host(true);const metadataAt=h.heartbeat().metadata_time_ms;
  h.c.now+=6000;h.c.block=true;const pending=h.poll();await settle();
  const oldLayer=h.layer(),documents=h.c.documents,preferences=h.c.preferences;
  h.command('after-wait');h.c.now+=6000;await h.pulse();await settle();
  assert.equal(h.heartbeat().plugin_time_ms,h.c.now);assert.equal(h.heartbeat().metadata_time_ms,metadataAt);
  assert.equal(h.heartbeat().reason,'js-alive');assert.equal(h.layer(),oldLayer);
  assert.equal([...h.files.keys()].some(name=>name.startsWith('execution-')),false);
  await h.poll();assert.equal(h.c.captures,1);assert.equal(h.c.preferences,preferences);
  h.release();await pending;assert.equal(h.c.documents,documents,'Yield before the next document getter');
  assert.equal(h.heartbeat().metadata_time_ms,metadataAt,'Interrupted metadata must not publish');
  h.c.block=false;await h.poll();assert.equal(h.c.captures,2);await h.poll();assert.equal(h.c.captures,2);
  // Checkpoints after synchronous getters also skip remaining metadata work.
  h=await host();h.c.now+=6000;h.c.onDocuments=()=>h.command('during-document-get');
  const previous=h.heartbeat().metadata_time_ms;await h.poll();assert.equal(h.heartbeat().metadata_time_ms,previous);
  await h.poll();assert.equal(h.c.captures,1);
  console.log('PASS metadata scheduling: cold/due command and menu priority; awaited-call ownership; pure JS pulse; original ages; getter checkpoints; no replay');
})().catch(error=>{console.error(error);process.exitCode=1;});
