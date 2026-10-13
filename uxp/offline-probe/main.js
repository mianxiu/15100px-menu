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
let pendingResponse=null;
let completedReceipts=[];
let lastWorkAt=0;
async function finishResponse(folder,response) {
  // Store the final outcome before the compatibility response slot. If storage
  // is temporarily unavailable, retain the outcome in memory and only retry
  // writing that outcome, never run the Photoshop command again.
  await record(folder,'result-'+response.id+'.json',response);
  await record(folder,'probe-response.json',response);
  pendingResponse=null;
  completedReceipts.push('result-'+response.id+'.json');
  if(completedReceipts.length>64) {
    const name=completedReceipts.shift();
    try {await (await folder.getEntry(name)).delete();}catch(_){}
  }
}
async function updateLayerContext(folder,now,force=false) {
  if(!force && now-contextReadAt<100)return;
  contextReadAt=now;
  let value;
  try {value=labels.selectionContext();}
  catch(_) {value={session,document_id:null,layer_ids:[],kind:'unknown',mask:0};}
  const signature=JSON.stringify(value);
  const snapshot={...value,schema:1,plugin_time_ms:now};
  if(force || signature!==contextSignature || now-contextWriteAt>=1000) {
    await record(folder,'layer-context.json',snapshot);
    contextSignature=signature;contextWriteAt=now;
  }
  return snapshot;
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
    if(pendingResponse) {await finishResponse(folder,pendingResponse);return;}
    const now = Date.now();
    if (reason !== 'poll' || now - lastHeartbeat >= 5000) {
      await record(folder, 'probe-last.json', {
        ...await metadata(),
        reason: reason === 'poll' ? 'heartbeat' : reason,
        sequence: ++sequence, probe_version: '0.3.9', session, transport: 'plugin-data-files',
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
    } catch (_) { await updateLayerContext(folder,now);return; }
    if (request.token !== token || !['inspect','capture','set_label','new_document'].includes(request.operation) ||
        typeof request.id !== 'string' || request.id.length > 128 ||
        seen.has(request.id) || !Number.isFinite(request.expires_at_ms) ||
        request.expires_at_ms < Date.now() || request.expires_at_ms > Date.now() + 30000) {
      // Metadata DOM reads are comparatively costly. Pending work takes
      // priority; a short quiet period also lets capture's write arrive before
      // an unrelated cache refresh. Execution still rechecks fresh eligibility.
      if(now-lastWorkAt>=80)await updateLayerContext(folder,now);
      return;
    }
    if(request.session && request.session!==session)return;
    const modifying=['set_label','new_document'].includes(request.operation);
    if(modifying) {
      if(!/^[0-9a-f]{32}$/.test(request.id))return;
      // A durable accepted/final receipt survives plugin reload. Its presence
      // consumes this ID even if no final result could be recorded.
      try {await folder.getEntry('result-'+request.id+'.json');seen.add(request.id);return;}
      catch(_){}
    }
    seen.add(request.id); // Consume before any write; never retry after an uncertain response.
    const response = {schema:1,session,id: request.id, probe_version: '0.3.9', operation: request.operation,
      transport: 'plugin-data-files', document_count: app.documents.length,
      completed_at_ms: Date.now(), phase: 'completed'};
    if(modifying)await record(folder,'result-'+request.id+'.json',{...response,phase:'accepted'});
    try {
      if (request.operation === 'inspect') response.target = labels.documentTarget();
      if (request.operation === 'capture') response.target = await labels.capture();
      if (request.operation === 'set_label') response.result = await labels.setLabel(request);
      if (request.operation === 'new_document') response.result = await labels.createDocument(request);
    } catch (error) { response.phase = 'failed'; response.error = String(error); response.result_unknown=!!error.resultUnknown; }
    response.completed_at_ms = Date.now();
    if(modifying) {
      // Keep the committed outcome even if metadata storage fails. Prepare the
      // new selection before confirming completion, so an immediately reopened
      // menu cannot freeze the previous layer. This never repeats a mutation.
      pendingResponse=response;
      if(response.phase==='completed') {
        try {response.layer_context=await updateLayerContext(folder,Date.now(),true);}
        catch(error) {console.log('Selection feedback unavailable',String(error));}
      }
      await finishResponse(folder,response);
    }
    else await record(folder, 'probe-response.json', response);
    lastRequest = request.id;
    // Capture gets a quiet period while its write follows; after modification
    // refresh the new selection on the next poll, without an extra 80ms wait.
    lastWorkAt=modifying?0:Date.now();
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


