// Verifies request fencing; simulation cannot establish actual UXP loading.
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const source = fs.readFileSync('uxp/offline-probe/main.js', 'utf8');
async function main() {
  const files = new Map(), writes = [];
  const folder = {
    createFile: async name => ({name,write: async text => {
      files.set(name, text); writes.push({name, value: name.endsWith('.jsx')?text:JSON.parse(text)});
    }}),
    getEntry: async name => ({read: async () => {
      if (!files.has(name)) throw Error('missing'); return files.get(name);
    }})
  };
  let tick,dirty;
  let now=Date.now();
  class Clock extends Date {static now(){return now;}}
  let selection={session:'test',document_id:1,layer_ids:[2],kind:'pixel',mask:15};
  const manifest = JSON.parse(fs.readFileSync('uxp/offline-probe/manifest.json','utf8'));
  let redrawCalls=0,refreshTokens=0,redrawResult='PSMENU_REDRAW_OK';
  const uxp = {storage: {localFileSystem: {getDataFolder: async () => folder,
    createSessionToken:entry=>{assert.equal(entry.name,'preview-redraw-24.jsx');refreshTokens++;return 'fixed-refresh-session-token';},
    getPluginFolder: async () => ({getEntry:async () => ({read:async () => JSON.stringify(manifest)})})}}};
  const app = {documents: [{title: 'untitled'}], activeDocument: {title: 'untitled'}};
  const context = {module: {exports: {}}, console, Date:Clock,setTimeout,clearTimeout,
    require: name => name === 'photoshop' ? {app,action:{addNotificationListener:(events,callback)=>{dirty=callback;},batchPlay:async descriptors=>{
      redrawCalls++;assert.equal(descriptors.length,1);const c=descriptors[0];
      assert.equal(c._obj,'AdobeScriptAutomation Scripts');assert.equal(c.javaScript._path,'fixed-refresh-session-token');
      assert.equal(c._options.dialogOptions,'silent');return [{javaScriptMessage:redrawResult}];
    }}} : name === 'uxp' ? uxp : name === './labels.js' ? (()=>({interfacePreferences:async()=>({}),selectionContext:()=>selection,selectionContextFresh:async()=>selection,documentTarget:()=>({session:'test',document_ids:[1],active_document_id:1})})) : 'test-token',
    setInterval: (fn,ms) => { if(ms===16)tick = fn; }, fetch: () => {throw Error('network must not be used');}};
  vm.runInNewContext(source, context);
  await new Promise(resolve => setImmediate(resolve));
  const heartbeat=writes.find(w=>w.name==='probe-last.json').value;
  assert.equal(heartbeat.phase, 'ready');
  assert.equal(heartbeat.document_redraw_available, false);
  assert.equal(heartbeat.photoshop_version, 'unavailable');
  assert.equal(heartbeat.plugin_name,manifest.name);
  assert.equal(heartbeat.command_label,'检查连接');
  assert.equal(JSON.parse(files.get('layer-context.json')).kind,'pixel');
  const submit = async values => {
    files.set('probe-request.json', JSON.stringify({id: 'one', token: 'test-token',
      operation: 'inspect', expires_at_ms: Date.now() + 5000, ...values}));
    now+=100;await tick();
  };
  await submit({token: 'wrong'});
  await submit({expires_at_ms: Date.now() - 1});
  await submit({operation: 'color'});
  await submit({expires_at_ms: Date.now() + 60000});
  assert.equal(files.has('probe-response.json'), false);
  await submit({});
  assert.equal(JSON.parse(files.get('probe-response.json')).id, 'one');
  assert.equal(JSON.parse(files.get('probe-response.json')).document_count, 1);
  await submit({});
  assert.equal(writes.filter(x => x.name === 'probe-response.json').length, 1);
  await submit({id: 'two'});
  assert.equal(JSON.parse(files.get('probe-response.json')).id, 'two');
  selection={...selection,kind:'background',mask:1};now+=100;dirty();await tick();
  assert.equal(JSON.parse(files.get('layer-context.json')).mask,1);
  const count=writes.filter(w=>w.name==='layer-context.json').length;
  now+=100;dirty();await tick();assert.equal(writes.filter(w=>w.name==='layer-context.json').length,count);
  assert.equal(typeof context.redrawLegacyPreview,'undefined');
  assert.equal(refreshTokens,0);assert.equal(redrawCalls,0);
  assert.equal(source.includes('AdobeScriptAutomation Scripts'),false,'Production must not route preview through nested JSX');
  let localReads=0,releaseRead;
  const read=context.boundedPreviewRead(()=>{localReads++;return new Promise(resolve=>{releaseRead=resolve;});},10);
  assert.equal(await read(),null);assert.equal(await read(),null);
  assert.equal(localReads,1,'A stalled local read must not create a queue of orphaned reads');
  releaseRead({seq:1});await new Promise(resolve=>setImmediate(resolve));
  assert.equal((await read()).seq,1,'A slow completed read must remain available on the next poll');
  assert.equal(localReads,1);
  assert.equal(await read(),null);assert.equal(localReads,2,'A completed read allows the next fresh mailbox read');
  releaseRead({seq:2});
  const failing=context.boundedPreviewRead(async()=>{throw Error('local read failed');},10);
  assert.equal(await failing(),null);
  console.log('PASS: network-free startup, optional metadata, token, expiry, operation, duplicate fencing');
}
main().catch(error => {console.error(error); process.exitCode = 1;});
