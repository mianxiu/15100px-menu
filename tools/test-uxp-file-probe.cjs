// Verifies request fencing; simulation cannot establish actual UXP loading.
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const source = fs.readFileSync('uxp/offline-probe/main.js', 'utf8');
async function main() {
  const files = new Map(), writes = [];
  const folder = {
    createFile: async name => ({write: async text => {
      files.set(name, text); writes.push({name, value: JSON.parse(text)});
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
  const uxp = {storage: {localFileSystem: {getDataFolder: async () => folder,
    getPluginFolder: async () => ({getEntry:async () => ({read:async () => JSON.stringify(manifest)})})}}};
  const app = {documents: [{title: 'untitled'}], activeDocument: {title: 'untitled'}};
  const context = {module: {exports: {}}, console, Date:Clock,
    require: name => name === 'photoshop' ? {app,action:{addNotificationListener:(events,callback)=>{dirty=callback;}}} : name === 'uxp' ? uxp : name === './labels.js' ? (()=>({interfacePreferences:async()=>({}),selectionContext:()=>selection,selectionContextFresh:async()=>selection,documentTarget:()=>({session:'test',document_ids:[1],active_document_id:1})})) : 'test-token',
    setInterval: fn => { tick = fn; }, fetch: () => {throw Error('network must not be used');}};
  vm.runInNewContext(source, context);
  await new Promise(resolve => setImmediate(resolve));
  const heartbeat=writes.find(w=>w.name==='probe-last.json').value;
  assert.equal(heartbeat.phase, 'ready');
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
  console.log('PASS: network-free startup, optional metadata, token, expiry, operation, duplicate fencing');
}
main().catch(error => {console.error(error); process.exitCode = 1;});
