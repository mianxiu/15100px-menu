// Read-only, network-free installation and local IPC probe.
const {app} = require('photoshop');
const uxp = require('uxp');
const token = require('./probe-config.js');
const session = String(Date.now()) + '-' + Math.random().toString(16).slice(2);
const labels = require('./labels.js')(require('photoshop'), session);
const seen = new Set();
let sequence = 0;
let running = false;
let lastRequest = null;
let lastHeartbeat = 0;
let pluginManifest = null;
let contextReadAt=0,contextWriteAt=0,contextSignature='';
async function updateLayerContext(folder,now) {
  if(now-contextReadAt<100)return;
  contextReadAt=now;
  let value;
  try {value=labels.selectionContext();}
  catch(_) {value={session,document_id:null,layer_ids:[],kind:'unknown',mask:0};}
  const signature=JSON.stringify(value);
  if(signature!==contextSignature || now-contextWriteAt>=1000) {
    await record(folder,'layer-context.json',{...value,schema:1,plugin_time_ms:now});
    contextSignature=signature;contextWriteAt=now;
  }
}
async function metadata() {
  if (!pluginManifest) {
    try {
      const folder = await uxp.storage.localFileSystem.getPluginFolder();
      pluginManifest = JSON.parse(await (await folder.getEntry('manifest.json')).read());
    } catch (_) { return {plugin_name: 'unavailable', command_label: 'unavailable'}; }
  }
  return {plugin_name: pluginManifest.name, command_label: pluginManifest.entrypoints[0].label.default};
}
function optional(read) {
  try { const value = read(); return value == null ? 'unavailable' : String(value); }
  catch (_) { return 'unavailable'; }
}
async function record(folder, name, value) {
  const file = await folder.createFile(name, {overwrite: true});
  await file.write(JSON.stringify(value));
}
async function probe(reason) {
  if (running) return;
  running = true;
  try {
    const folder = await uxp.storage.localFileSystem.getDataFolder();
    const now = Date.now();
    await updateLayerContext(folder,now);
    if (reason !== 'poll' || now - lastHeartbeat >= 5000) {
      await record(folder, 'probe-last.json', {
        ...await metadata(),
        reason: reason === 'poll' ? 'heartbeat' : reason,
        sequence: ++sequence, probe_version: '0.3.6', session, transport: 'plugin-data-files',
        photoshop_version: optional(() => uxp.host.version),
        uxp_version: optional(() => uxp.versions.uxp),
        plugin_id: 'com.15100px.menu.offline-probe',
        document_count: app.documents.length, document_name: app.documents.length ? app.activeDocument.title : null, plugin_time_ms: now, phase: 'ready'
      });
      lastHeartbeat = now;
    }
    let request;
    try {
      const file = await folder.getEntry('probe-request.json');
      const raw = await file.read();
      if (raw.length > 4096) return;
      request = JSON.parse(raw);
    } catch (_) { return; }
    if (request.token !== token || !['inspect','capture','set_label','new_document'].includes(request.operation) ||
        typeof request.id !== 'string' || request.id.length > 128 ||
        seen.has(request.id) || !Number.isFinite(request.expires_at_ms) ||
        request.expires_at_ms < Date.now() || request.expires_at_ms > Date.now() + 30000) return;
    seen.add(request.id); // Consume before any write; never retry after an uncertain response.
    const response = {id: request.id, probe_version: '0.3.6', operation: request.operation,
      transport: 'plugin-data-files', document_count: app.documents.length,
      completed_at_ms: Date.now(), phase: 'completed'};
    try {
      if (request.operation === 'inspect') response.target = labels.documentTarget();
      if (request.operation === 'capture') response.target = await labels.capture();
      if (request.operation === 'set_label') response.result = await labels.setLabel(request);
      if (request.operation === 'new_document') response.result = await labels.createDocument(request);
    } catch (error) { response.phase = 'failed'; response.error = String(error); response.result_unknown=!!error.resultUnknown; }
    response.completed_at_ms = Date.now();
    await record(folder, 'probe-response.json', response);
    lastRequest = request.id;
  } catch (error) {
    console.log('Offline file probe error', String(error));
  } finally { running = false; }
}
module.exports = {commands: {probe: () => probe('command')}};
probe('startup');
// Notifications make selection/type/lock changes visible on the next poll;
// the bounded DOM poll also covers changes made by external COM scripts.
try {require('photoshop').action.addNotificationListener(
  ['select','make','delete','set','undo','redo'].map(event=>({event})),()=>{contextReadAt=0;});}
catch(_) {}
setInterval(() => probe('poll'), 16);


