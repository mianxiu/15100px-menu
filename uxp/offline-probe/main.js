// Read-only, network-free installation and local IPC probe.
const {app} = require('photoshop');
const uxp = require('uxp');
const token = require('./probe-config.js');
const session = String(Date.now()) + '-' + Math.random().toString(16).slice(2);
const hostVersion=String(uxp.host?.version || '').split('.').map(Number);
const legacyPreview=hostVersion[0]===24 && hostVersion[1]===0 && hostVersion[2]>=1;
const labels = require('./labels.js')(require('photoshop'), session, {legacyPreview});
const seen = new Set();
let sequence = 0;
let running = false;
let lastRequest = null;
let lastHeartbeat = 0;
let pluginManifest = null;
let contextReadAt=0,contextWriteAt=0,contextSignature='';
let contextInterval=100;
let observation={};
let pendingResponse=null;
let completedReceipts=[];
let lastWorkAt=0;
let menuRefreshId='';
let heartbeatValue=null;
let activeExecution=null,executionPulseRunning=false;
// This pulse performs only local file I/O. A pending Photoshop await must not
// hide which original operation owns the host, or masquerade as fresh layer data.
async function executionPulse() {
  if(!activeExecution || executionPulseRunning)return;
  executionPulseRunning=true;
  try {
    const current=activeExecution;
    await record(current.folder,'execution-'+current.id+'.json',{
      schema:1,id:current.id,session,operation:current.operation,command:current.command,
      stage:current.stage,stage_started_at_ms:current.stageAt,seq:current.seq,
      phase:'running',plugin_time_ms:Date.now()});
  } catch(error) {console.log('Execution pulse unavailable',String(error));}
  finally {executionPulseRunning=false;}
}
async function executionStage(stage,seq) {
  if(!activeExecution)return;
  activeExecution.stage=stage;activeExecution.stageAt=Date.now();
  if(Number.isSafeInteger(seq))activeExecution.seq=seq;
  // Detailed durable checkpoints are opt-in for owned test documents only.
  // Normal dragging does not add per-frame filesystem writes.
  if(activeExecution.trace)await executionPulse();
}
function boundedPreviewRead(read,timeout=250) {
  let pending=null;
  const expired={};
  return async()=>{
    // Only local mailbox I/O can be timed out here. Photoshop mutations and
    // redraw calls must always remain awaited until their actual outcome.
    // Reuse an unresolved read rather than accumulating abandoned file reads.
    if(!pending) {
      pending=Promise.resolve().then(read).then(value=>({value}),()=>({value:null}));
    }
    let timer;const current=pending;
    try {
      const result=await Promise.race([current,new Promise(resolve=>{timer=setTimeout(()=>resolve(expired),timeout);})]);
      if(result===expired)return null;
      // Retain late data until it is consumed. Clearing on resolution would
      // lose every frame if disk latency consistently just exceeded timeout.
      if(pending===current)pending=null;
      return result.value;
    }
    finally {clearTimeout(timer);}
  };
}
async function refreshMenuContext(folder,now) {
  let request;
  try {request=JSON.parse(await (await folder.getEntry('menu-context-request.json')).read());}catch(_){return false;}
  if(request.token!==token || request.session!==session || !/^[0-9a-f]{32}$/.test(request.id) || request.id===menuRefreshId || !Number.isFinite(request.expires_at_ms) || request.expires_at_ms<now || request.expires_at_ms>now+10000)return false;
  const started=Date.now();
  // Yield only between read-only host calls. Never abandon a Photoshop call
  // or consume/replay an operation here: the next poll owns its normal dispatch.
  async function checkpoint() {
    await readHeartbeat(folder);
    let current,cancel,command;
    try {current=JSON.parse(await(await folder.getEntry('menu-context-request.json')).read());}catch(_){}
    try {cancel=JSON.parse(await(await folder.getEntry('menu-context-cancel.json')).read());}catch(_){}
    try {command=JSON.parse(await(await folder.getEntry('probe-request.json')).read());}catch(_){}
    let reason='';
    // expires_at_ms limits acceptance, not an already accepted read. A large
    // snapshot may finish later, with fresh identity/capability validation.
    // Still bound the read itself and yield immediately to close/new commands.
    if(Date.now()-started>30000)reason='read-timeout';
    else if(current?.token!==token || current?.session!==session || current?.id!==request.id)reason='superseded';
    else if(cancel?.token===token && cancel?.session===session && cancel?.id===request.id)reason='closed';
    else if(command?.token===token && (!command.session || command.session===session) &&
        typeof command.id==='string' && !seen.has(command.id) &&
        ['inspect','capture','set_label','new_document'].includes(command.operation) &&
        Number.isFinite(command.expires_at_ms) && command.expires_at_ms>=Date.now() && command.expires_at_ms<=Date.now()+30000)reason='command';
    if(reason){const error=Error('Menu read yielded: '+reason);error.menuReadInterrupted=true;
      menuRefreshId=request.id;observation.menu={...observation.menu,interrupted:reason,elapsed_ms:Date.now()-started,completed_at_ms:Date.now()};throw error;}
  }
  let context;
  try {await checkpoint();context=await labels.selectionContextFresh(checkpoint);await checkpoint();}
  catch(error) {
    if(error.menuReadInterrupted)return true;
    menuRefreshId=request.id;
    observation.menu={selection_ms:Date.now()-started,error:String(error).slice(0,200),completed_at_ms:Date.now()};
    return true;
  }
  const readDone=Date.now();contextReadAt=readDone;
  const needsShape=!context.locked && !context.background && (context.kind==='shape-fill' && context.layer_ids.length===1 || context.layer_ids.length>=2 && context.layer_ids.length<=128);
  const basic={...context,shape_editor:{available:false},schema:1,plugin_time_ms:readDone,
    menu_request_id:request.id,menu_phase:needsShape?'basic':'completed',timings_ms:{selection_ms:readDone-started}};
  // Publish ordinary capabilities before optional vector/pattern metadata.
  // A slow or failed color read must not leave every layer action disabled.
  await record(folder,'menu-context-result.json',basic);
  await record(folder,'layer-context.json',basic);
  menuRefreshId=request.id;
  observation.menu={selection_ms:readDone-started,completed_at_ms:readDone,phase:basic.menu_phase};
  if(needsShape) {
    let shape={available:false},error='';
    try {await checkpoint();shape=await labels.observeShape(context,true,null,checkpoint);await checkpoint();}
    catch(e){if(e.menuReadInterrupted)return true;error=String(e).slice(0,200);}
    const matches=labels.selectionMatches(context),done=Date.now();
    observation.menu={...observation.menu,shape_ms:done-readDone,shape_error:error,selection_changed:!matches,phase:'completed'};
    // A slow optional read needs fresh eligibility, not a fresh timestamp on
    // old locks/capabilities. A changed identity never enables the editor.
    if(matches) {
      let latest;
      try {latest=done-readDone>=1000?await labels.selectionContextFresh(checkpoint):context;}
      catch(error){if(error.menuReadInterrupted)return true;throw error;}
      try {await checkpoint();}catch(error){if(error.menuReadInterrupted)return true;throw error;}
      if(latest.document_id===context.document_id && latest.layer_ids.join(',')===context.layer_ids.join(','))
        await record(folder,'menu-context-result.json',{...basic,...latest,plugin_time_ms:done-readDone>=1000?Date.now():readDone,
          shape_editor:shape,menu_phase:'completed',timings_ms:{...basic.timings_ms,shape_ms:done-readDone}});
    }
  }
  return true;
}
async function finishResponse(folder,response) {
  // Store the final outcome before the compatibility response slot. If storage
  // is temporarily unavailable, retain the outcome in memory and only retry
  // writing that outcome, never run the Photoshop command again.
  await record(folder,'result-'+response.id+'.json',response);
  await record(folder,'probe-response.json',response);
  pendingResponse=null;
  if(activeExecution?.id===response.id)activeExecution=null;
  completedReceipts.push('result-'+response.id+'.json');
  if(completedReceipts.length>64) {
    const name=completedReceipts.shift();
    for(const file of [name,name.replace('result-','mask-preview-'),name.replace('result-','mask-preview-status-'),name.replace('result-','execution-'),name.replace('result-','legacy-prepared-'),name.replace('result-','legacy-result-')])
      try {await (await folder.getEntry(file)).delete();}catch(_){}
  }
}
async function updateLayerContext(folder,now,force=false,prepared=null,checkpoint=null) {
  if(!force && now-contextReadAt<contextInterval)return;
  contextReadAt=now;
  let value;
  let error='';
  try {value=prepared && labels.selectionMatches(prepared)?prepared:await labels.selectionContextFresh(checkpoint);}
  catch(e) {if(e.menuReadInterrupted){observation.background={interrupted:e.reason,elapsed_ms:Date.now()-now,completed_at_ms:Date.now()};return;}
    error=String(e).slice(0,200);value={session,document_id:null,layer_ids:[],kind:'unknown',mask:0};}
  // Throttle from read completion: if DOM work itself takes over 100ms,
  // measuring from its start would immediately launch another costly read.
  const readDone=Date.now();contextReadAt=readDone;
  contextInterval=Math.max(error?1000:100,Math.min(1000,readDone-now));
  observation.background={selection_ms:readDone-now,interval_ms:contextInterval,completed_at_ms:readDone,error};
  // Vector properties and the pattern catalog are only needed for an opened
  // layer menu. Do not continuously reread them while Photoshop is idle.
  const shape={available:false};
  const signature=JSON.stringify([value,shape]);
  const snapshot={...value,shape_editor:shape,schema:1,plugin_time_ms:Date.now()};
  if(force || signature!==contextSignature || now-contextWriteAt>=1000) {
    await record(folder,'layer-context.json',snapshot);
    contextSignature=signature;contextWriteAt=Date.now();
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
async function readHeartbeat(folder) {
  const now=Date.now();
  if(!heartbeatValue || now-lastHeartbeat<5000)return;
  // Only a live JS checkpoint can renew transport liveness. No host getters,
  // and no retimestamping of layer snapshots or metadata: their original
  // timestamps remain separate. A blocked host call cannot renew this lease.
  await record(folder,'probe-last.json',{...heartbeatValue,reason:'read-progress',
    sequence:++sequence,plugin_time_ms:now,metadata_time_ms:heartbeatValue.plugin_time_ms,
    read_only_work:true,layer_observation:observation});
  lastHeartbeat=now;
}
async function probe(reason) {
  if (running) return;
  running = true;
  try {
    const folder = await uxp.storage.localFileSystem.getDataFolder();
    if(pendingResponse) {await finishResponse(folder,pendingResponse);return;}
    const now = Date.now();
    if (reason !== 'poll' || now - (heartbeatValue?.plugin_time_ms || 0) >= 5000) {
      heartbeatValue={
        ...await metadata(),
        reason: reason === 'poll' ? 'heartbeat' : reason,
        sequence: ++sequence, probe_version: '0.3.40', session, transport: 'plugin-data-files',
        layer_observation:observation,
        ...await labels.interfacePreferences(),
        photoshop_version: optional(() => uxp.host.version),
        uxp_version: optional(() => uxp.versions.uxp),
        document_redraw_available: typeof require('photoshop').core?.redrawDocument === 'function',
        legacy_preview_available:legacyPreview,
        plugin_id: 'com.15100px.menu.offline-probe',
        document_count: app.documents.length, document_name: app.documents.length ? app.activeDocument.title : null, plugin_time_ms: now, phase: 'ready'
      };
      await record(folder,'probe-last.json',heartbeatValue);
      lastHeartbeat = now;
    }
    // A chord may follow Caps after its menu request was published. Service
    // the accepted command before optional menu/color reads; capture's short
    // quiet period also protects the following fixed-target write.
    async function idleRead() {
      if(now-lastWorkAt<80)return;
      if(await refreshMenuContext(folder,now))return;
      await updateLayerContext(folder,now,false,null,async()=>{
        await readHeartbeat(folder);
        let command,menu;
        try {command=JSON.parse(await(await folder.getEntry('probe-request.json')).read());}catch(_){}
        try {menu=JSON.parse(await(await folder.getEntry('menu-context-request.json')).read());}catch(_){}
        const pendingCommand=command?.token===token && (!command.session || command.session===session) &&
          typeof command.id==='string' && !seen.has(command.id) &&
          ['inspect','capture','set_label','new_document'].includes(command.operation) &&
          Number.isFinite(command.expires_at_ms) && command.expires_at_ms>=Date.now() && command.expires_at_ms<=Date.now()+30000;
        const pendingMenu=menu?.token===token && menu.session===session && /^[0-9a-f]{32}$/.test(menu.id) &&
          menu.id!==menuRefreshId && Number.isFinite(menu.expires_at_ms) && menu.expires_at_ms>=Date.now() && menu.expires_at_ms<=Date.now()+10000;
        if(pendingCommand || pendingMenu){const error=Error('Background read yielded');error.menuReadInterrupted=true;error.reason=pendingCommand?'command':'menu';throw error;}
      });
    }
    let request;
    try {
      const file = await folder.getEntry('probe-request.json');
      const raw = await file.read();
      if (raw.length > 4096) return;
      request = JSON.parse(raw);
    } catch (_) { await idleRead();return; }
    if (request.token !== token || !['inspect','capture','set_label','new_document'].includes(request.operation) ||
        typeof request.id !== 'string' || request.id.length > 128 ||
        seen.has(request.id) || !Number.isFinite(request.expires_at_ms) ||
        request.expires_at_ms > Date.now() + 30000) {
      // Metadata DOM reads are comparatively costly. Pending work takes
      // priority; a short quiet period also lets capture's write arrive before
      // an unrelated cache refresh. Execution still rechecks fresh eligibility.
      await idleRead();
      return;
    }
    // A previous host's mailbox must remain untouched, but must not starve
    // fresh read-only snapshots after a normal Photoshop restart.
    if(request.session && request.session!==session){await idleRead();return;}
    const modifying=['set_label','new_document'].includes(request.operation);
    if(modifying) {
      if(!/^[0-9a-f]{32}$/.test(request.id))return;
      // A durable accepted/final receipt survives plugin reload. Its presence
      // consumes this ID even if no final result could be recorded.
      try {await folder.getEntry('result-'+request.id+'.json');seen.add(request.id);return;}
      catch(_){}
    }
    if(request.expires_at_ms<Date.now()) {
      if(!modifying){await idleRead();return;}
      // A valid, unseen request can expire behind a slow read. Give its
      // original identity a durable rejection instead of silently dropping it
      // and making the caller wait forever for an outcome. Existing accepted
      // records above, other sessions and malformed packets are never changed.
      seen.add(request.id);
      const rejected={schema:1,session,id:request.id,probe_version:'0.3.40',operation:request.operation,
        phase:'failed',error:'请求在执行前已过期；未修改 Photoshop',not_executed:true,result_unknown:false,completed_at_ms:Date.now()};
      pendingResponse=rejected;await finishResponse(folder,rejected);
      lastRequest=request.id;return;
    }
    seen.add(request.id); // Consume before any write; never retry after an uncertain response.
    const response = {schema:1,session,id: request.id, probe_version: '0.3.40', operation: request.operation,
      transport: 'plugin-data-files', document_count: app.documents.length,
      completed_at_ms: Date.now(), phase: 'completed'};
    const timingStarted=Date.now(),timings={};
    if(modifying)await record(folder,'result-'+request.id+'.json',{...response,phase:'accepted'});
    timings.accept_ms=Date.now()-timingStarted;
    const operationStarted=Date.now();
    if(modifying) {
      activeExecution={folder,id:request.id,operation:request.operation,command:request.command,
        stage:'accepted',stageAt:Date.now(),seq:0,trace:request.preview_trace===true};
      await executionStage('dispatch');
    }
    let progressSerial=0,progressLast='',progressAt=0,progressFrame=0,progressRestoring=false;
    function progressStage(name){
      if(name.includes('rollback')){progressRestoring=true;return name.startsWith('verify')?'restore-verify':'restore';}
      if(name==='redraw-native')return progressRestoring?'restore-redraw':'redraw';
      if(name==='publish-frame')return 'ready';
      if(name==='commit-history')return 'commit';
      if(name.startsWith('write'))return 'write';
      if(name.startsWith('verify') || name==='validate-frame')return progressRestoring?'restore-verify':'verify';
      if(name==='capture-target' || name==='enter-modal')return 'prepare';
      return null;
    }
    async function previewProgress(stage,done=0,total=0,frame){
      if(Number.isSafeInteger(frame))progressFrame=frame;
      if(progressRestoring && stage==='verify')stage='restore-verify';
      if(progressRestoring && stage==='redraw')stage='restore-redraw';
      if(stage==='restore')progressRestoring=true;
      const now=Date.now(),key=stage+':'+progressFrame;
      if(key===progressLast && now-progressAt<100 && done!==total)return;
      progressLast=key;progressAt=now;
      try{await record(folder,'preview-progress-'+request.id+'.json',{id:request.id,session,token,
        serial:++progressSerial,stage,done,total,frame:progressFrame});}catch(_){}
    }
    try {
      if(request.capture_current!==undefined) {
        if(request.capture_current!==true || request.capture_session!==session || request.operation!=='set_label' || request.target!==undefined ||
            !['selectAbove','selectBelow','extendAbove','extendBelow','copyStyle','pasteStyle'].includes(request.command))throw Error('Invalid direct Caps binding');
        // Keep both fresh captures: bind here, then the existing executor
        // checks the exact target again inside its modal before any write.
        const captured=await (['selectAbove','selectBelow','extendAbove','extendBelow'].includes(request.command)?labels.captureSelection():labels.capture());
        response.captured_target=captured;
        await record(folder,'result-'+request.id+'.json',{...response,phase:'accepted'});
        request={...request,target:captured};
      }
      if (request.operation === 'inspect') {
        response.target = labels.documentTarget();
        if(request.shape_inspect)response.shape_editor=await labels.observeShape(await labels.selectionContextFresh(),true);
      }
      if (request.operation === 'capture') response.target = await labels.capture();
      if(request.operation==='set_label' && request.command==='shape.legacy.preview') {
        // Reserve the plugin's existing worker without entering executeAsModal.
        // While native JSX owns the host, only mailbox I/O and cached pulses run.
        const prepared=await labels.prepareLegacyShape(request);
        if(JSON.stringify(prepared).length>(request.paint?.mask_batch?900000:60000))throw Error('预览准备数据过大，请减少批量图层或路径复杂度');
        await record(folder,'legacy-prepared-'+request.id+'.json',{schema:1,id:request.id,session,operation:request.operation,token,phase:'prepared',prepared});
        await executionStage('legacy-native-wait');
        while(true) {
          let native=null;
          try {const raw=await(await folder.getEntry('legacy-result-'+request.id+'.json')).read();if(raw.length<=65536)native=JSON.parse(raw);}catch(_){}
          if(native?.schema===1 && native.id===request.id && native.session===session && native.operation===request.operation && native.token===token && ['completed','failed'].includes(native.phase)) {
            response.result=await labels.finishLegacyShape(request,prepared,native);break;
          }
          if(heartbeatValue && Date.now()-lastHeartbeat>=1000){lastHeartbeat=Date.now();await record(folder,'probe-last.json',{...heartbeatValue,phase:'preview',reason:'legacy-native',plugin_time_ms:lastHeartbeat});}
          await new Promise(resolve=>setTimeout(resolve,40));
        }
      }
      if (request.operation === 'set_label' && request.command!=='shape.legacy.preview') response.result = await labels.setLabel(request,
        request.command==='shape.preview'?{
          stage:async(name,seq)=>{await executionStage(name,seq);const stage=progressStage(name);if(stage)await previewProgress(stage,0,0,seq);},
          progress:previewProgress,
          read:boundedPreviewRead(async()=>{
            if(heartbeatValue && Date.now()-lastHeartbeat>=1000) {
              lastHeartbeat=Date.now();
              await record(folder,'probe-last.json',{...heartbeatValue,phase:'preview',reason:'mask-preview',plugin_time_ms:lastHeartbeat});
            }
            try {
              const raw=await (await folder.getEntry('mask-preview-'+request.id+'.json')).read();
              if(raw.length>4096)throw Error('Preview mailbox exceeds limit');
              return JSON.parse(raw);
            } catch(error) {
              // A transient filesystem read cannot renew the preview lease.
              // Expiry rolls back; never restart or replay the operation.
              return null;
            }
          }),
          applied:value=>record(folder,'mask-preview-status-'+request.id+'.json',{
            id:request.id,session,phase:'preview',...value,plugin_time_ms:Date.now()})
        }:null);
      if (request.operation === 'new_document') response.result = await labels.createDocument(request);
    } catch (error) { response.phase = 'failed'; response.error = String(error); response.result_unknown=!!error.resultUnknown; }
    response.completed_at_ms = Date.now();
    timings.operation_ms=Date.now()-operationStarted;
    if(modifying) {
      // Keep the committed outcome even if metadata storage fails. Prepare the
      // new selection before confirming completion, so an immediately reopened
      // menu cannot freeze the previous layer. This never repeats a mutation.
      pendingResponse=response;
      if(response.phase==='completed') {
        const feedbackStarted=Date.now();
        try {response.layer_context=await updateLayerContext(folder,Date.now(),true,response.result.selection_context);}
        catch(error) {console.log('Selection feedback unavailable',String(error));}
        timings.selection_feedback_ms=Date.now()-feedbackStarted;
      }
      response.timings_ms=timings;
      await executionStage('persist-result');
      await finishResponse(folder,response);
    }
    else await record(folder, 'probe-response.json', response);
    lastRequest = request.id;
    if(['shape.preview','shape.legacy.preview'].includes(request.command))lastHeartbeat=0;
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
setInterval(executionPulse,1000);


