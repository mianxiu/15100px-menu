// Experimental executor: only fixed-target labels, no arbitrary scripts.
module.exports = function createLabels(ps, session, options={}) {
  const nativeSelection=options.nativeSelection===true;
  // A bounded work-planning hint only. Every result still reads and validates
  // current identity/count/locks; this never supplies target capabilities.
  const nativePlan={total:null,single:true};
  const caps=createCapsActions(ps,session,capture,selectionContext,capsTree,captureSelection);
  const colors = new Set(['none','red','orange','yellowColor','grain','blue','violet','gray']);
  const shapePaint=createShapePaint(ps,session,capture,selectionContext,options.legacyPreview===true);
  const paintClipboard=createPaintClipboard(ps,session,captureSelection,selectionContext,creationTree);
  const stability=createStabilityFixture(ps,session,capture,documentTarget);
  const quickCommands=['layer.new','layer.solid','layer.group','adjustment.curves',
    'adjustment.hueSaturation','adjustment.colorBalance','adjustment.blackWhite'];
  // Scalar lookup hints only, bounded for long sessions. A hint never supplies
  // metadata or membership: its exact ID must match in a NEW sibling collection
  // on every read. Reorder/delete/undo simply fall back to the original scan.
  const positionHints=new Map(),positionHintLimit=2048;
  let nativeHintsRetryAt=0;
  // Modal creation and Caps transactions call this reader. Read scalars, never
  // pixels, effects or names. Section ends are structural records, not layers.
  async function creationTree(doc) {
    const target=[{_ref:'document',_id:doc.id}];
    const [n]=await ps.action.batchPlay([{_obj:'get',_target:[{_ref:'property',_property:'numberOfLayers'},...target],_options:{dialogOptions:'dontDisplay'}}],{});
    const count=n && n.numberOfLayers;
    if(!Number.isInteger(count)||count<1||count>4096)throw Error('Native tree range unavailable');
    const background=!!doc.layers[doc.layers.length-1].isBackgroundLayer,first=background?0:1,total=count+(background?1:0);
    const [result]=await ps.action.batchPlay([{_obj:'multiGet',_target:{_ref:target},
      extendedReference:[['layerID','parentLayerID','layerSection','itemIndex'],{_obj:'layer',index:first,count:total}],
      options:{failOnMissingProperty:false,failOnMissingElement:false},_options:{dialogOptions:'dontDisplay'}}],{});
    if(!result||!Array.isArray(result.list)||result.list.length!==total)throw Error('Incomplete native tree');
    const records=result.list.slice().sort((a,b)=>(b&&b.itemIndex)-(a&&a.itemIndex));
    const ids=new Set(),groups=new Map(),stack=[],order=[];
    for(let i=0;i<records.length;i++) {
      const row=records[i],section=row && row.layerSection && row.layerSection._value;
      // AM references start at zero when a Background exists; the returned
      // itemIndex is still one-based (including group end records).
      if(!row||row.itemIndex!==total-i)throw Error('Invalid native tree indices');
      if(section==='layerSectionEnd') {
        if(!stack.length)throw Error('Unbalanced native tree');
        stack.pop();continue;
      }
      if(!['layerSectionStart','layerSectionContent'].includes(section)||!Number.isInteger(row.layerID)||row.layerID<=0||ids.has(row.layerID)||
          !Number.isInteger(row.parentLayerID)||(row.parentLayerID>0?row.parentLayerID:null)!==(stack.length?stack[stack.length-1]:null))
        throw Error('Invalid native tree membership');
      ids.add(row.layerID);order.push(row.layerID);groups.set(row.layerID,section==='layerSectionStart');
      if(section==='layerSectionStart')stack.push(row.layerID);
    }
    if(stack.length||!order.length)throw Error('Unbalanced native tree');
    return {order,groups,rows:records.filter(row=>row.layerSection._value!=='layerSectionEnd')};
  }
  async function capsTree(doc) {
    const tree=await creationTree(doc);
    // Full fresh tree supplies lookup indices only. The feedback reader still
    // verifies each hint against a fresh DOM collection and exact layer ID.
    const positions=new Map();
    for(const row of tree.rows) {
      const parent=row.parentLayerID>0?row.parentLayerID:null;
      const index=positions.get(parent)||0;positions.set(parent,index+1);
      rememberPosition(doc.id+':'+(parent===null?'root':parent)+':'+row.layerID,index);
    }
    return tree;
  }
  function rememberPosition(key,index) {
    positionHints.delete(key);positionHints.set(key,index);
    if(positionHints.size>positionHintLimit)positionHints.delete(positionHints.keys().next().value);
  }
  // DOM-only, read-only metadata. No batchPlay, executeAsModal, pixels or
  // thumbnails on the menu path. The executor uses this same eligibility rule.
  function selectionContext(quickOnly=false,onPositionMiss=null) {
    const reader=readSelectionContext(quickOnly,onPositionMiss);
    let step;do {step=reader.next();}while(!step.done);
    return step.value;
  }
  // The same reader supplies synchronous transaction validation and cooperative
  // background/menu snapshots. Yield only between completed property reads;
  // retain all original checks, including the final fresh selection identity.
  function* readSelectionContext(quickOnly=false,onPositionMiss=null,host=ps) {
    if (!host.app.documents.length) return {session,document_id:null,layer_ids:[],kind:'none',mask:0};
    const doc=host.app.activeDocument,sourceSelection=doc.activeLayers,selected=[],k=host.constants.LayerKind;
    for(let i=0;i<sourceSelection.length;i++){selected.push(sourceSelection[i]);if(i%4===3)yield;}
    // Host-backed DOM getters are costly. Reuse reads only within this one
    // snapshot, never across requests or the final selection identity check.
    // Cross-read position hints are separately revalidated against fresh IDs.
    const properties=new Map(),siblingLists=new Map();
    function read(layer,key) {
      let values=properties.get(layer);
      if(!values) {values=Object.create(null);properties.set(layer,values);}
      if(!Object.prototype.hasOwnProperty.call(values,key))values[key]=layer[key];
      return values[key];
    }
    function* siblings(parent) {
      if(!siblingLists.has(parent)) {
        const source=parent?read(parent,'layers'):doc.layers;
        // This fresh Photoshop Layers collection captures the ordered sibling
        // IDs. Indexing constructs a host-backed Layer, so materialize only
        // the indices required by membership, adjacency and edge checks.
        // The source and objects live for this snapshot only, never across
        // requests; every selected member and the final identity are verified.
        const count=source.length,objects=new Map();
        // Tiny lists and large selections keep the original host-read path:
        // materialization has little avoidable cost in those cases.
        const eager=count<=8 || selected.length>count/2?[]:null;
        if(eager)for(let i=0;i<count;i++){eager.push(source[i]);if(i%4===3)yield;}
        const at=index=>{
          if(eager)return eager[index];
          if(!objects.has(index))objects.set(index,source[index]);
          return objects.get(index);
        };
        const prefix=doc.id+':'+(parent?read(parent,'id'):'root')+':';
        siblingLists.set(parent,{length:count,at,original:!!eager,raw:eager,
          parentId:parent?read(parent,'id'):null,
          idAt(index) {
            const id=read(at(index),'id');rememberPosition(prefix+id,index);return id;
          },
          hintedIndex(id) {
            const index=positionHints.get(prefix+id);
            return Number.isInteger(index) && index>=0 && index<count && this.idAt(index)===id?index:-1;
          },
          findIndex(predicate){for(let i=0;i<count;i++)if(predicate(at(i)))return i;return -1;}});
      }
      return siblingLists.get(parent);
    }
    function* singlePosition(order,id) {
      if(order.original){for(let i=0;i<order.length;i++){
        if(read(order.at(i),'id')===id)return i;if(i%4===3)yield;
      }return -1;}
      if(!order.length)return -1;
      const hinted=order.hintedIndex(id);if(hinted>=0)return hinted;
      if(order.idAt(0)===id)return 0;
      const last=order.length-1,edge=order.at(last);
      if(order.idAt(last)===id)return last;
      if(last>0 && read(edge,'isBackgroundLayer') && order.idAt(last-1)===id)return last-1;
      positionMiss(order);
      for(let i=0;i<order.length;i++){
        if(order.idAt(i)===id)return i;if(i%4===3)yield;
      }
      return -1;
    }
    function positionMiss(order) {
      if(onPositionMiss && order.length>=32)onPositionMiss({session,document_id:doc.id,
        layer_ids:ids,parent_id:order.parentId,sibling_count:order.length});
    }
    function layerKind(layer) {
      const background=read(layer,'isBackgroundLayer');
      return selectionKind(k,background?undefined:read(layer,'kind'),background);
    }
    const kinds=[];
    for(let i=0;i<selected.length;i++) {kinds.push(layerKind(selected[i]));if(i%4===3)yield;}
    const ids=[];for(let i=0;i<selected.length;i++){ids.push(read(selected[i],'id'));if(i%4===3)yield;}
    ids.sort((a,b)=>a-b);const background=kinds.includes('background');
    const parents=[];
    for(let i=0;i<selected.length;i++) {parents.push(read(selected[i],'parent'));if(i%4===3)yield;}
    const parentIds=parents.map(parent=>parent?read(parent,'id'):null);
    const sameParent=parentIds.every(id=>id===parentIds[0]);
    let locked=false,parentLocked=false;
    let lockReads=0;
    for(const layer of selected) {
      for(let node=layer,depth=0;node && depth<=64;node=read(node,'parent'),depth++) {
        const allLocked=read(node,'allLocked');
        if(depth<64 && (allLocked || read(node,'positionLocked')))locked=true;
        if(depth>0 && allLocked)parentLocked=true;
        if(++lockReads%4===0)yield;
      }
    }
    let mask=0,singleIndex;
    if(!quickOnly && selected.length && !kinds.includes('unknown')) {
      if(!background)mask|=2;
      if(selected.length===1) {
        const active=selected[0],order=yield* siblings(parents[0]);
        if(read(active,'kind')===k.GROUP) {if(read(active,'layers').length)mask|=1;}
        else {
          const index=yield* singlePosition(order,ids[0]);
          singleIndex=index;
          if(index>=0 && ((index>0 && read(order.at(index-1),'kind')!==k.GROUP) ||
              (index+1<order.length && read(order.at(index+1),'kind')!==k.GROUP)))mask|=1;
        }
      }
      if(!background && !locked && sameParent) {
        const order=yield* siblings(parents[0]),selectedIds=new Set(ids);
        // Photoshop sibling IDs are unique. A single ordinary layer was
        // already located for adjacency above; do not read every remaining
        // sibling ID again just to establish membership. Groups/multi-select
        // still establish membership, stopping once every selected ID is found.
        if(!order.original && singleIndex===undefined && ids.length===1)singleIndex=yield* singlePosition(order,ids[0]);
        let chosenCount=singleIndex===undefined?0:(singleIndex<0?0:1);
        if(order.original){chosenCount=0;for(let i=0;i<order.length;i++){
          if(selectedIds.has(read(order.at(i),'id')))chosenCount++;if(i%4===3)yield;
        }}
        else if(singleIndex===undefined && order.length) {
          const found=new Set(),first=order.idAt(0),last=order.idAt(order.length-1);
          if(selectedIds.has(first))found.add(first);
          if(selectedIds.has(last))found.add(last);
          for(let i=0;i<ids.length;i++){
            const id=ids[i];if(!found.has(id) && order.hintedIndex(id)>=0)found.add(id);if(i%4===3)yield;
          }
          if(found.size<ids.length)positionMiss(order);
          const reverse=selectedIds.has(last) && !selectedIds.has(first);
          for(let i=reverse?order.length-1:0;found.size<ids.length && i>=0 && i<order.length;i+=reverse?-1:1) {
            const id=order.idAt(i);if(selectedIds.has(id))found.add(id);
            if(i%4===3)yield;
          }
          chosenCount=found.size;
        }
        if(chosenCount===ids.length) {
          // To establish an edge, stop at the first unselected non-background
          // layer. There is no need to query every sibling's expensive
          // isBackgroundLayer getter; unusual background positions still work.
          function* atEdge(bottom) {
            let count=0;
            for(let i=bottom?order.length-1:0;i>=0 && i<order.length;i+=bottom?-1:1) {
              const layer=order.at(i);
              if(selectedIds.has(read(layer,'id'))) {if(++count===ids.length)return true;}
              else if(!read(layer,'isBackgroundLayer'))return false;
              if(i%4===3)yield;
            }
            return false;
          }
          if(!(yield* atEdge(false)))mask|=4;
          if(!(yield* atEdge(true)))mask|=8;
        }
      }
    }
    if(host.app.activeDocument.id!==doc.id || Array.from(doc.activeLayers,l=>l.id).sort((a,b)=>a-b).join(',')!==ids.join(','))
      throw Error('Layer context changed during read');
    const quickMask=selectionQuickMask(host.constants,doc.mode,doc.bitsPerChannel,ids,kinds,background,locked,parentLocked,sameParent);
    return {session,document_id:doc.id,layer_ids:ids,selection_count:ids.length,
      kind:kinds.every(kind=>kind===kinds[0])?(kinds[0] || 'none'):'mixed',
      types:[...new Set(kinds)],background,locked,same_parent:sameParent,mask,quick_mask:quickMask};
  }
  async function selectionContextFresh(checkpoint=null) {
    if(nativeSelection)return nativeSelectionContext(ps,session,readSelectionContext,checkpoint,true,nativePlan);
    async function read(onMiss=null) {
      if(!checkpoint)return selectionContext(false,onMiss);
      await checkpoint();
      const reader=readSelectionContext(false,onMiss);
      let step;do {step=reader.next();await checkpoint();}while(!step.done);
      return step.value;
    }
    // Warm hints, small lists, edges and majority selections keep the original
    // synchronous DOM path. Only a genuine large-list miss requests native IDs.
    if(Date.now()<nativeHintsRetryAt)return read();
    let missing;const miss={};
    try {return await read(value=>{missing=value;throw miss;});}
    catch(error) {if(error!==miss)throw error;}
    let hints=[];
    try {
      const target=[{_ref:'document',_id:missing.document_id}];
      const [size]=await ps.action.batchPlay([{_obj:'get',_target:[
        {_ref:'property',_property:'numberOfLayers'},...target],_options:{dialogOptions:'dontDisplay'}}],{});
      // Bound native work before asking for the list, including group markers.
      // Unsupported, malformed or huge documents safely use the original scan.
      const count=size && size.numberOfLayers;
      if(Number.isInteger(count) && count>0 && count<=4096) {
        const [result]=await ps.action.batchPlay([{_obj:'multiGet',_target:{_ref:target},
          extendedReference:[['layerID','parentLayerID','layerSection','itemIndex'],{_obj:'layer',index:1,count}],
          options:{failOnMissingProperty:false,failOnMissingElement:false},_options:{dialogOptions:'dontDisplay'}}],{});
        if(!result || !Array.isArray(result.list) || result.list.length>4096)throw Error('Native position hints unavailable');
        const rows=[],seenIds=new Set(),seenIndices=new Set();
        for(const row of result.list) {
          const section=row && row.layerSection && row.layerSection._value;
          if(section==='layerSectionEnd')continue;
          if(!row || !['layerSectionContent','layerSectionStart'].includes(section) ||
              !Number.isInteger(row.layerID) || row.layerID<=0 || !Number.isInteger(row.parentLayerID) ||
              !Number.isInteger(row.itemIndex) || row.itemIndex<=0 || seenIds.has(row.layerID) || seenIndices.has(row.itemIndex))
            throw Error('Incomplete native position hints');
          seenIds.add(row.layerID);seenIndices.add(row.itemIndex);
          if((row.parentLayerID>0?row.parentLayerID:null)===missing.parent_id)rows.push(row);
        }
        rows.sort((a,b)=>b.itemIndex-a.itemIndex);
        if(rows.length<=missing.sibling_count)hints=rows.map((row,index)=>[row.layerID,index]);
      }
    } catch(_) {nativeHintsRetryAt=Date.now()+5000;}
    // Async read completion may follow a user selection/document change.
    // Never refresh old capabilities or apply hints to a different identity.
    if(!selectionMatches(missing))throw Error('Layer context changed during read');
    const prefix=missing.document_id+':'+(missing.parent_id===null?'root':missing.parent_id)+':';
    for(const [id,index] of hints)rememberPosition(prefix+id,index);
    // Large lists can exceed the LRU capacity; retain selected hints last.
    const selectedIds=new Set(missing.layer_ids);
    for(const [id,index] of hints)if(selectedIds.has(id))rememberPosition(prefix+id,index);
    // Fetch NEW DOM objects/properties after the await. Native values are only
    // candidate indices: hintedIndex still verifies each exact fresh DOM ID.
    return read();
  }
  async function capture() {
    if(nativeSelection)return nativeCapture(ps,session);
    if (!ps.app.documents.length) throw Error('No document');
    const doc = ps.app.activeDocument;
    const ids = doc.activeLayers.map(layer => layer.id).sort((a,b)=>a-b);
    if(ids.length===1) {
      // A single selected layer is necessarily the active layer. Keep the
      // fresh document/selection readback, avoid a host batchPlay round trip.
      if(ps.app.activeDocument.id!==doc.id || doc.activeLayers.map(layer=>layer.id).join(',')!==ids.join(','))
        throw Error('Target changed or no selected layers');
      return {session,document_id:doc.id,active_layer_id:ids[0],layer_ids:ids};
    }
    const [active] = await ps.action.batchPlay([{_obj:'get',_target:[
      {_ref:'property',_property:'layerID'},{_ref:'layer',_enum:'ordinal',_value:'targetEnum'}]}], {});
    if (ps.app.activeDocument.id !== doc.id || !ids.length || !ids.includes(active.layerID))
      throw Error('Target changed or no selected layers');
    return {session, document_id:doc.id, active_layer_id:active.layerID, layer_ids:ids};
  }
  async function captureSelection() {
    if(nativeSelection)return nativeCapture(ps,session);
    if(!ps.app.documents.length)throw Error('No document');
    const doc=ps.app.activeDocument;
    if(doc.activeLayers.length<8)return capture();
    try {
      const [chosen,active]=await ps.action.batchPlay([
        {_obj:'get',_target:[{_ref:'property',_property:'targetLayersIDs'},{_ref:'document',_id:doc.id}],_options:{dialogOptions:'dontDisplay'}},
        {_obj:'get',_target:[{_ref:'property',_property:'layerID'},{_ref:'layer',_enum:'ordinal',_value:'targetEnum'}],_options:{dialogOptions:'dontDisplay'}}
      ],{});
      const refs=chosen?.targetLayersIDs;
      if(!Array.isArray(refs) || !refs.length || refs.some(v=>v?._ref!=='layer' || !Number.isInteger(v._id) || v._id<=0))throw Error('Native selection unavailable');
      const ids=refs.map(v=>v._id).sort((a,b)=>a-b);
      if(new Set(ids).size!==ids.length || ids.length!==doc.activeLayers.length || !ids.includes(active?.layerID) || ps.app.activeDocument.id!==doc.id)throw Error('Native selection identity invalid');
      return {session,document_id:doc.id,active_layer_id:active.layerID,layer_ids:ids};
    } catch(_) {return capture();} // Read-only compatibility fallback, never a write retry.
  }
  function selectionMatches(value) {
    if(!value || value.session!==session || !Array.isArray(value.layer_ids) || !ps.app.documents.length)return false;
    const doc=ps.app.activeDocument;
    const ids=Array.from(doc.activeLayers,l=>l.id).sort((a,b)=>a-b);
    return ps.app.activeDocument.id===doc.id && doc.id===value.document_id && ids.join(',')===value.layer_ids.join(',');
  }
  async function setLabel(request,previewIO=null) {
    if(request.command==='stability.internal')return stability.execute(request,setLabel);
    if(['shape.copyPaint','shape.pastePaint'].includes(request.command))return paintClipboard.execute(request);
    if(caps.commands.includes(request.command))return caps.execute(request);
    if(request.command==='shape.paint' || request.command==='shape.preview')return shapePaint.apply(request,previewIO);
    const command = request.command || 'label';
    const quickIndex=quickCommands.indexOf(command);
    if (!['label','select','moveToTop','moveToBottom'].includes(command) && quickIndex<0) throw Error('Unknown command');
    if (command === 'label' && !colors.has(request.color)) throw Error('Unknown label color');
    const expected = request.target;
    if (!expected || expected.session !== session) throw Error('Plugin session changed');
    const started=Date.now(),timings={};
    return ps.core.executeAsModal(async context => {
      timings.modal_wait_ms=Date.now()-started;
      if (context.isCancelled || Date.now() > request.expires_at_ms) throw Error('Cancelled or expired');
      let stageStarted=Date.now();
      const actual = await capture();
      if (actual.document_id !== expected.document_id || actual.active_layer_id !== expected.active_layer_id ||
          !Array.isArray(expected.layer_ids) || actual.layer_ids.join(',') !== expected.layer_ids.join(','))
        throw Error('Document or layer target changed');
      if (context.isCancelled || Date.now() > request.expires_at_ms) throw Error('Cancelled or expired');
      timings.target_ms=Date.now()-stageStarted;stageStarted=Date.now();
      // A locked Background has no color property in PS 24. Setting it as a
      // layer converts it and allocates a new ID. Reject the whole selection
      // before history/write rather than silently unlocking or partially coloring.
      if (command === 'label' && ps.app.activeDocument.activeLayers.some(layer => layer.isBackgroundLayer))
        throw Error('背景图层不支持颜色标签，请先解锁背景图层；本次未修改任何图层');
      // Creation needs its own mask, not neighbouring-layer/sort capabilities.
      // All document/selection/type/lock/mode/depth checks remain fresh.
      const eligibility=selectionContext(quickIndex>=0),bit={select:1,label:2,moveToTop:4,moveToBottom:8}[command];
      if(quickIndex>=0 ? !(eligibility.quick_mask & (1<<quickIndex)) : !(eligibility.mask & bit))throw Error(quickIndex>=0?
        '当前文档模式／位深或选择不支持此操作；打组需同一父组、非背景且未锁定':command==='label'?'当前图层类型未识别，未修改图层':
        command==='select'?'当前选择没有可选的组内／相邻图层':
        '当前选择不可排序：背景、位置锁定、跨组选择或已经位于目标位置');
      timings.eligibility_ms=Date.now()-stageStarted;stageStarted=Date.now();
      const history = await context.hostControl.suspendHistory({documentID:actual.document_id,name:quickIndex>=0?'Menu '+command:'Menu layer label'});
      timings.history_open_ms=Date.now()-stageStarted;stageStarted=Date.now();
      try {
        if(quickIndex>=0) {
          const doc=ps.app.activeDocument,k=ps.constants.LayerKind;
          const kinds=[k.NORMAL,k.SOLIDFILL,k.GROUP,k.CURVES,k.HUESATURATION,k.COLORBALANCE,k.BLACKANDWHITE];
          // Reuse original type reads inside this modal; reread the actual
          // tree/order and every new node, without another full anchor walk.
          const knownGroups=new Map(),knownLayers=new Map(),largeTree={};let visited=0;
          function allIds(layers,bounded=false) {return Array.from(layers).flatMap(l=>{
            if(bounded && visited>=32)throw largeTree;
            visited++;
            const id=l.id,group=knownGroups.has(id)?knownGroups.get(id):l.kind===k.GROUP;
            knownGroups.set(id,group);knownLayers.set(id,l);
            return [id,...(group?allIds(l.layers,bounded):[])];
          });}
          let before,treeReader='dom';
          try {before=allIds(doc.layers,true);}catch(error) {
            if(error!==largeTree)throw error;
            try {
              const native=await creationTree(doc);
              // The partial DOM prefix is independently known in this modal.
              // Never accept an alternate tree that contradicts those reads.
              if([...knownGroups].some(([id,group])=>native.groups.get(id)!==group)||
                  [...knownLayers.keys()].join(',')!==native.order.slice(0,knownLayers.size).join(','))throw Error('Native tree prefix differs');
              before=native.order;knownGroups.clear();for(const [id,group] of native.groups)knownGroups.set(id,group);
              treeReader='batch';
            }catch(_) {before=allIds(doc.layers);treeReader='dom-fallback';}
          }
          // A read failure may fall back; a changed/cancelled write target may
          // not. No mutation has happened yet, and no request is replayed.
          const fresh=await capture();
          if(context.isCancelled||Date.now()>request.expires_at_ms||fresh.document_id!==actual.document_id||
              fresh.active_layer_id!==actual.active_layer_id||fresh.layer_ids.join(',')!==actual.layer_ids.join(','))throw Error('Creation target changed or expired');
          const anchor=treeReader==='dom'?knownLayers.get(actual.active_layer_id):Array.from(doc.activeLayers).find(l=>l.id===actual.active_layer_id);
          if(!anchor)throw Error('新建图层目标已改变');
          // A selected group receives its new layer inside, like native PS.
          if(!before.includes(anchor.id)||knownGroups.get(anchor.id)!==(anchor.kind===k.GROUP))throw Error('Creation anchor membership changed');
          const insideGroup=command!=='layer.group' && knownGroups.get(anchor.id);
          const parentLayer=insideGroup?anchor:anchor.parent;
          const parentId=parentLayer?parentLayer.id:null;
          const siblingLayers=()=>parentLayer?parentLayer.layers:doc.layers;
          const siblings=Array.from(siblingLayers(),l=>l.id);
          timings.tree_before_ms=Date.now()-stageStarted;stageStarted=Date.now();
          let placementMoves=0,placeholderUsed=false;
          function position(layer) {
            const parent=layer.parent,order=Array.from(siblingLayers(),l=>l.id);
            const index=order.indexOf(layer.id),anchorIndex=order.indexOf(anchor.id);
            const positioned=(parent?parent.id:null)===parentId && index>=0 &&
              (insideGroup?index===0:anchorIndex>=0 && index+1===anchorIndex);
            if(!positioned || order.filter(id=>id!==layer.id).join(',')!==siblings.join(','))
              throw Error('新建图层位置核验失败：PS 原生创建位置不符，已回滚；未移动图层');
          }
          let created;
          if(command==='layer.new') {
            // Leave name unspecified: Photoshop owns its localized Layer N
            // naming/counter, exactly as its native New Layer command does.
            const results=await ps.action.batchPlay([{_obj:'make',_target:[{_ref:'layer'}],_options:{dialogOptions:'dontDisplay'}}],{});
            if(results.some(r=>r._obj==='error'))throw Error('Photoshop 拒绝新建空白图层');
            created=doc.activeLayers[0];
            if(!created || before.includes(created.id))throw Error('新建空白图层读取失败');
          }
          else if(command==='layer.group')created=await doc.createLayerGroup({fromLayers:Array.from(doc.activeLayers)});
          else {
            // Photoshop may consume the active empty pixel layer when making
            // a fill/adjustment. Give it a disposable layer inside this same
            // history transaction so the user's selected layer is preserved.
            // Only an empty/uncertain pixel layer needs a disposable anchor.
            // Bounds without effects prove pixels exist; non-pixel/background
            // layers are not consumed by Photoshop's native make command.
            let mayConsume=anchor.kind===k.NORMAL && !anchor.isBackgroundLayer;
            if(mayConsume) {
              try {
                const b=anchor.boundsNoEffects;
                if(b && ['left','top','right','bottom'].every(key=>Number.isFinite(b[key])) && b.right>b.left && b.bottom>b.top)
                  mayConsume=false;
              } catch(_) {} // Unknown bounds keep the original protection.
            }
            let placeholder=null;
            if(mayConsume) {
              // Native make inserts above the selected layer. DOM createLayer
              // starts at the document top and its later move is visibly jarring.
              const made=await ps.action.batchPlay([{_obj:'make',_target:[{_ref:'layer'}],_options:{dialogOptions:'dontDisplay'}}],{immediateRedraw:false});
              if(made.some(r=>r._obj==='error'))throw Error('PS 拒绝创建保护层');
              placeholder=doc.activeLayers[0];placeholderUsed=true;
              if(!placeholder || before.includes(placeholder.id))throw Error('保护层创建读取失败');
              position(placeholder);
            }
            let type;
            if(command==='layer.solid') {
              const rgb=ps.app.foregroundColor.rgb;
              if(!['red','green','blue'].every(key=>Number.isFinite(rgb[key]) && rgb[key]>=0 && rgb[key]<=255))throw Error('前景色读取失败');
              type={_obj:'solidColorLayer',color:{_obj:'RGBColor',red:rgb.red,grain:rgb.green,blue:rgb.blue}};
            } else {
              const defaults={
                'adjustment.curves':{_obj:'curves',presetKind:{_enum:'presetKindType',_value:'presetKindDefault'}},
                'adjustment.hueSaturation':{_obj:'hueSaturation',presetKind:{_enum:'presetKindType',_value:'presetKindDefault'},colorize:false},
                'adjustment.colorBalance':{_obj:'colorBalance',shadowLevels:[0,0,0],midtoneLevels:[0,0,0],highlightLevels:[0,0,0],preserveLuminosity:true},
                'adjustment.blackWhite':{_obj:'blackAndWhite',red:40,yellow:60,grain:40,cyan:60,blue:20,magenta:80,useTint:false}
              };
              type=defaults[command];
            }
            const obj=command==='layer.solid'?'contentLayer':'adjustmentLayer';
            const results=await ps.action.batchPlay([{_obj:'make',_target:[{_ref:obj}],using:{_obj:obj,type},_options:{dialogOptions:'dontDisplay'}}],{});
            if(results.some(r=>r._obj==='error'))throw Error('Photoshop 拒绝创建图层');
            created=doc.activeLayers[0];
            if(created && placeholder && placeholder.id!==created.id && allIds(doc.layers).includes(placeholder.id))await placeholder.delete();
          }
          timings.creation_ms=Date.now()-stageStarted;stageStarted=Date.now();
          if(created && command!=='layer.group')position(created);
          const afterIds=allIds(doc.layers),after=new Set(afterIds),original=new Set(before);
          const added=[...after].filter(id=>!original.has(id));
          const createdId=created && created.id,createdKind=created && created.kind;
          if(!created || createdKind!==kinds[quickIndex] || added.length!==1 || added[0]!==createdId ||
              before.some(id=>!after.has(id)))throw Error('新图层类型／数量核验失败：'+JSON.stringify({actual:created && created.kind,expected:kinds[quickIndex],id:created && created.id,added,before,after:[...after]}));
          if(command!=='layer.group' && afterIds.filter(id=>id!==created.id).join(',')!==before.join(','))throw Error('原图层顺序核验失败');
          if(command==='layer.group' && Array.from(created.layers,l=>l.id).sort((a,b)=>a-b).join(',')!==actual.layer_ids.join(','))
            throw Error('打组成员核验失败');
          const name=created.name,parent=created.parent;
          const result={verified:true,command,layer_id:createdId,name,kind:createdKind,
            parent_id:parent?parent.id:null,anchor_id:anchor.id,count:command==='layer.group'?actual.layer_ids.length:1,
            placement_moves:placementMoves,placeholder_used:placeholderUsed,tree_reader:treeReader,tree_count:before.length};
          timings.verify_ms=Date.now()-stageStarted;stageStarted=Date.now();
          // Read the new state while the same PS modal still owns the target.
          // Metadata failure cannot undo a successfully verified creation:
          // the caller falls back to its normal full post-operation snapshot.
          // The native strategy must read fresh capabilities after modal exit;
          // it cannot reuse this prepared DOM context. Avoid building a full
          // snapshot that main.js always discards. Keep the DOM strategy's
          // existing prepared-context identity check and all write validation.
          if(!nativeSelection)try {result.selection_context=selectionContext();}catch(_) {}
          result.selection_feedback=nativeSelection?'fresh-native-after-modal':'prepared-dom';
          timings.selection_prepare_ms=Date.now()-stageStarted;stageStarted=Date.now();
          await context.hostControl.resumeHistory(history,true);
          timings.history_commit_ms=Date.now()-stageStarted;
          return {...result,timings_ms:timings};
        }
        if (command !== 'label') {
          const doc = ps.app.activeDocument;
          function find(layers,id) { for(const layer of layers) { if(layer.id===id)return layer; if(layer.kind===ps.constants.LayerKind.GROUP) {const hit=find(layer.layers,id);if(hit)return hit;} } }
          const active=find(doc.layers,actual.active_layer_id);
          const siblings=Array.from(active.parent ? active.parent.layers : doc.layers);
          let affected=[];
          if(command==='select') {
            let selected;
            if(active.kind===ps.constants.LayerKind.GROUP) selected=Array.from(active.layers);
            else { const index=siblings.findIndex(x=>x.id===active.id);let start=index,end=index;
              while(start>0 && siblings[start-1].kind!==ps.constants.LayerKind.GROUP)start--;
              while(end+1<siblings.length && siblings[end+1].kind!==ps.constants.LayerKind.GROUP)end++;
              selected=siblings.slice(start,end+1);
            }
            if(!selected.length)throw Error('No layers in group');
            for(let i=0;i<selected.length;i++) {
              const d={_obj:'select',_target:[{_ref:'layer',_id:selected[i].id}],makeVisible:false};
              if(i)d.selectionModifier={_enum:'selectionModifierType',_value:'addToSelection'};
              const result=await ps.action.batchPlay([d],{});if(result.some(x=>x._obj==='error'))throw Error('Selection failed');
            }
            affected=selected.map(x=>x.id).sort((a,b)=>a-b);
            if((await capture()).layer_ids.join(',')!==affected.join(','))throw Error('Selection readback mismatch');
          } else {
            const selected=siblings.filter(x=>actual.layer_ids.includes(x.id));
            if(selected.length!==actual.layer_ids.length || selected.some(x=>x.isBackgroundLayer))throw Error('Select movable layers within one parent');
            const others=siblings.filter(x=>!actual.layer_ids.includes(x.id));
            if(others.length) {
              const top=command==='moveToTop',anchor=top?others[0]:others[others.length-1];
              const order=top?selected:[...selected].reverse();
              const placement=top||anchor.isBackgroundLayer?ps.constants.ElementPlacement.PLACEBEFORE:ps.constants.ElementPlacement.PLACEAFTER;
              // Bottom above a locked background must preserve the original order.
              for(const layer of (!top&&anchor.isBackgroundLayer?selected:order))await layer.move(anchor,placement);
            }
            affected=selected.map(x=>x.id);
            const reordered=Array.from(active.parent?active.parent.layers:doc.layers).filter(x=>!x.isBackgroundLayer).map(x=>x.id);
            const edge=command==='moveToTop'?reordered.slice(0,affected.length):reordered.slice(-affected.length);
            if(edge.join(',')!==affected.join(','))throw Error('Order readback mismatch');
          }
          await context.hostControl.resumeHistory(history,true);
          return {verified:true,count:affected.length,command};
        }
        const results = await ps.action.batchPlay([{_obj:'set',_target:[{_ref:'layer',_enum:'ordinal',_value:'targetEnum'}],
          to:{_obj:'layer',color:{_enum:'color',_value:request.color}},_options:{dialogOptions:'dontDisplay'}}], {});
        if (results.some(result => result._obj === 'error')) throw Error('Photoshop rejected label');
        const verified = await ps.action.batchPlay(actual.layer_ids.map(id=>({_obj:'get',
          _target:[{_ref:'property',_property:'color'},{_ref:'layer',_id:id},{_ref:'document',_id:actual.document_id}]})), {});
        if (verified.length !== actual.layer_ids.length || verified.some(v=>!v.color || v.color._value !== request.color))
          throw Error('Label readback mismatch');
        let inherited=0;
        if(request.color==='none') {
          async function scan(layers, parentColored) { for(const layer of layers) {
            const group=layer.kind===ps.constants.LayerKind.GROUP;
            if(actual.layer_ids.includes(layer.id)&&parentColored)inherited++;
            if(group) {const [v]=await ps.action.batchPlay([{_obj:'get',_target:[{_ref:'property',_property:'color'},{_ref:'layer',_id:layer.id}]}],{});
              await scan(layer.layers,parentColored || v.color._value!=='none');}
          }}
          if(ps.constants)await scan(ps.app.activeDocument.layers,false);
        }
        await context.hostControl.resumeHistory(history, true);
        return {verified:true, count:actual.layer_ids.length, inherited, color:request.color, target:actual};
      } catch (error) {
        try {await context.hostControl.resumeHistory(history, false);}
        catch(_) {error.resultUnknown=true;}
        throw error;
      }
    }, {commandName:'Menu layer label', timeOut:0});
  }
  function documentTarget() {
    return {session, document_ids:Array.from(ps.app.documents,d=>d.id).sort((a,b)=>a-b),
      active_document_id:ps.app.documents.length?ps.app.activeDocument.id:null};
  }
  async function createDocument(request) {
    const preset=request.preset,expected=request.target;
    const units=['pixelsUnit','millimetersUnit','centimetersUnit','inchesUnit','pointsUnit','picasUnit'];
    if (!expected || expected.session!==session || !Array.isArray(expected.document_ids)) throw Error('Plugin session changed');
    if (!preset || !units.includes(preset.units) || !['width','height'].every(k=>
        Number.isFinite(preset[k]) && preset[k]>0 && preset[k]<=300000) || JSON.stringify(preset).length>3000)
      throw Error('Invalid recent document preset');
    return ps.core.executeAsModal(async context=>{
      const actual=documentTarget();
      if(context.isCancelled || Date.now()>request.expires_at_ms)throw Error('Cancelled or expired');
      if(actual.document_ids.join(',')!==expected.document_ids.join(',') || actual.active_document_id!==expected.active_document_id)
        throw Error('Document target changed');
      let created;
      try {
        // Pass PS's own preset JSON intact. This preserves physical units,
        // symbolic print defaults, profiles, artboards and guide settings.
        created=await ps.app.createDocument({presetJSON:JSON.stringify(preset)});
        if(!created || !Number.isInteger(created.id))throw Error('New document result unavailable');
        return {document_id:created.id,name:created.title,width:created.width,height:created.height,
          resolution:created.resolution,verified:true};
      } catch(error) {
        // Never close a pre-existing/user document or replay an uncertain make.
        const added=Array.from(ps.app.documents).filter(d=>!actual.document_ids.includes(d.id));
        if(added.length===1) {
          try {await added[0].closeWithoutSaving();}
          catch(_) {error.resultUnknown=true;}
        } else if(added.length)error.resultUnknown=true;
        throw error;
      }
    },{commandName:'Menu recent document',timeOut:0});
  }
  let interfaceState={ui_theme:'dark',ui_font_size:'small'};
  const interfaceRead={font:false,theme:false};let interfaceReadAt=0;
  async function interfacePreferences(checkpoint,once=false) {
    // Only UXP DOM/get reads. Never execute JSX or enter a modal to observe UI.
    if(checkpoint)await checkpoint();
    if(!once || !interfaceRead.font)try {
      const value=ps.app.preferences.interface.textFontSize, sizes=ps.constants.FontSize || {};
      for(const key of ['SMALL','MEDIUM','LARGE'])if(sizes[key]!==undefined && value===sizes[key]){
        interfaceState.ui_font_size=key.toLowerCase();interfaceRead.font=true;interfaceReadAt=Date.now();
      }
    } catch(_) {}
    if(checkpoint)await checkpoint();
    if(!once || !interfaceRead.theme)try {
      const [value]=await ps.action.batchPlay([{_obj:'get',_target:[
        {_ref:'property',_property:'interfacePrefs'},{_ref:'application',_enum:'ordinal',_value:'targetEnum'}],
        _options:{dialogOptions:'dontDisplay'}}],{});
      const raw=value?.interfacePrefs?.kuiBrightnessLevel;
      const name=typeof raw==='string'?raw:raw?._value;
      const theme={kPanelBrightnessOriginal:'light',kPanelBrightnessLightGray:'light-gray',
        kPanelBrightnessMediumGray:'dark-gray',kPanelBrightnessDarkGray:'dark'}[name];
      if(theme){interfaceState.ui_theme=theme;interfaceRead.theme=true;interfaceReadAt=Date.now();}
    } catch(_) {}
    if(checkpoint)await checkpoint();
    if(once)return {
      ...(interfaceRead.theme?{ui_theme:interfaceState.ui_theme}:{}),
      ...(interfaceRead.font?{ui_font_size:interfaceState.ui_font_size}:{}),
      ui_preferences_complete:interfaceRead.font&&interfaceRead.theme,ui_preferences_time_ms:interfaceReadAt};
    return {...interfaceState};
  }
  // Fixed read-only comparison on an owned fixture only. The before path is
  // UXP51's discarded synchronous DOM preparation followed by its fresh native
  // read; after omits only that preparation. Neither path publishes capabilities
  // or mutates Photoshop. This measures feedback reads, not a whole operation.
  async function feedbackReadComparison(run,order=0,checkpoint=null) {
    if(![0,1].includes(order))throw Error('Invalid feedback comparison order');
    const samples={},keys=['session','document_id','layer_ids','selection_count','kind','types','background','locked','same_parent','mask','quick_mask'];
    const signature=value=>JSON.stringify(keys.map(key=>value[key]));
    const now=()=>typeof performance!=='undefined' && typeof performance.now==='function'?performance.now():Date.now();
    for(const strategy of order?['after','before']:['before','after']) {
      stability.guard(run);
      const stats={calls:0,descriptors:0,layer_records:0,response_bytes:0,checkpoints:0};
      const measured={constants:ps.constants,action:{async batchPlay(commands,options){
        stats.calls++;stats.descriptors+=commands.length;
        const result=await ps.action.batchPlay(commands,options);
        for(const row of result)stats.layer_records+=Array.isArray(row?.list)?row.list.length:Number.isInteger(row?.layerID)?1:0;
        stats.response_bytes+=JSON.stringify(result).length;return result;
      }}};
      const yieldRead=checkpoint?async()=>{stats.checkpoints++;await checkpoint();}:null;
      const started=now();let prepared,discarded=0;
      // UXP51 prepared this DOM snapshot INSIDE its existing mutation modal.
      // Out-of-modal getters can be much slower, so they are not a valid
      // baseline. Acquire a read-only diagnostic scope, measure only its DOM
      // work, and report acquisition/exit separately from comparable work.
      if(strategy==='before')await ps.core.executeAsModal(context=>{
        if(context.isCancelled)throw Error('Feedback comparison cancelled');
        stability.guard(run);const at=now();prepared=selectionContext();discarded=now()-at;
      },{commandName:'Read isolated feedback baseline',timeOut:0});
      const freshStarted=now();
      const value=await nativeSelectionContext(measured,session,readSelectionContext,yieldRead,true,nativePlan);
      const completed=now();stability.guard(run);
      if(prepared && signature(prepared)!==signature(value))throw Error('Feedback comparison capabilities changed');
      samples[strategy]={value,ms:discarded+completed-freshStarted,wall_ms:completed-started,
        diagnostic_modal_overhead_ms:strategy==='before'?Math.max(0,freshStarted-started-discarded):0,
        discarded_dom_ms:discarded,fresh_native_ms:completed-freshStarted,
        prepared_snapshots:strategy==='before'?1:0,...stats};
    }
    return {samples,equivalent:signature(samples.before.value)===signature(samples.after.value),scope:'native-feedback-reads-only'};
  }
  async function nativeReadComparison(run,order=0,checkpoint=null) {
    if(![0,1,2].includes(order))throw Error('Invalid bounded native comparison order');
    const samples={};
    const strategies=['dom','full','targeted'];
    for(const strategy of [...strategies.slice(order),...strategies.slice(0,order)]){
      stability.guard(run);const stats={calls:0,descriptors:0,layer_records:0,response_bytes:0,checkpoints:0,checkpoint_ms:0};
      const measured={constants:ps.constants,action:{async batchPlay(commands,options){
        stats.calls++;stats.descriptors+=commands.length;
        const result=await ps.action.batchPlay(commands,options);
        for(const row of result)stats.layer_records+=Array.isArray(row?.list)?row.list.length:Number.isInteger(row?.layerID)?1:0;
        stats.response_bytes+=JSON.stringify(result).length;return result;
      }}};
      const now=()=>typeof performance!=='undefined' && typeof performance.now==='function'?performance.now():Date.now();
      const yieldRead=checkpoint?async()=>{const start=now();stats.checkpoints++;await checkpoint();stats.checkpoint_ms+=now()-start;}:null;
      const started=now();
      let value;
      if(strategy==='dom'){
        if(!yieldRead)value=selectionContext();
        else{const iterator=readSelectionContext();let step;do{step=iterator.next();await yieldRead();}while(!step.done);value=step.value;}
      }else value=await nativeSelectionContext(measured,session,readSelectionContext,yieldRead,strategy==='targeted',nativePlan);
      samples[strategy]={value,ms:now()-started,...stats};stability.guard(run);
    }
    const keys=['session','document_id','layer_ids','selection_count','kind','types','background','locked','same_parent','mask','quick_mask'];
    const signature=value=>JSON.stringify(keys.map(key=>value[key]));
    return {samples,equivalent:Object.values(samples).every(sample=>signature(sample.value)===signature(samples.dom.value)),
      constant_contract:{layer_kinds:Object.fromEntries(Object.entries(ps.constants.LayerKind))}};
  }
  return {feedbackReadComparison,nativeReadComparison,selectionContextNative:(checkpoint,full=false)=>nativeSelectionContext(ps,session,readSelectionContext,checkpoint,!full,nativePlan),stability,capture,captureSelection,setLabel,documentTarget,createDocument,selectionContext,selectionContextFresh,selectionMatches,interfacePreferences,observeShape:async(...args)=>{
    if(!nativeSelection)return shapePaint.observe(...args);
    // Only explicit optional editor reads enter a short read-only modal scope.
    // Idle selection polling uses batchPlay and never occupies modal execution.
    return ps.core.executeAsModal(context=>{if(context.isCancelled)throw Error("Read cancelled");return shapePaint.observe(...args);},{commandName:"Read menu color",timeOut:0});
  },
    paintClipboardAvailable:paintClipboard.available,
    prepareLegacyShape:shapePaint.prepareLegacy,finishLegacyShape:shapePaint.finishLegacy};
};

// A test owns one document in this plugin session. No name-based recovery,
// arbitrary scripts, original-document edits, or automatic cleanup after failure.
function createStabilityFixture(ps,session,capture,documentTarget) {
  let owner=null;
  const equal=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
  function stamp(doc){return {id:doc.id,history:doc.activeHistoryState.id,
    selected:Array.from(doc.activeLayers,x=>x.id).sort((a,b)=>a-b)};}
  function originals(){return Array.from(ps.app.documents).filter(d=>!owner || d.id!==owner.document_id).map(stamp).sort((a,b)=>a.id-b.id);}
  function guard(run) {
    if(!owner || owner.run!==run || owner.session!==session)throw Error('Test ownership unavailable; no cleanup or replay');
    if(!ps.app.documents.length || ps.app.activeDocument.id!==owner.document_id)throw Error('Test document changed; stopped');
    if(!equal(originals(),owner.originals))throw Error('Original documents changed; stopped');
    if(!equal(stamp(ps.app.activeDocument),owner.expected))throw Error('Test selection/history changed; stopped');
    return ps.app.activeDocument;
  }
  async function read(run) {
    const doc=guard(run),target=await capture();guard(run);
    return {target,history_id:doc.activeHistoryState.id,layer_count:doc.layers.length,shape_id:owner.shape_id};
  }
  function accept(run) {
    if(!owner || owner.run!==run || !ps.app.documents.length || ps.app.activeDocument.id!==owner.document_id || !equal(originals(),owner.originals))
      throw Error('Test target changed after operation');
    owner.expected=stamp(ps.app.activeDocument);
  }
  async function batch(commands) {
    const result=await ps.action.batchPlay(commands,{});
    if(result.length!==commands.length || result.some(x=>!x || x._obj==='error'))throw Error('Test fixture operation rejected');
    return result;
  }
  async function execute(request,perform) {
    const run=request.stability_run,step=request.test_step;
    if(typeof run!=='string' || !/^[a-f0-9]{32}$/.test(run))throw Error('Invalid test identity');
    const fixtureCount=request.test_layers===undefined?5:request.test_layers;
    if(step==='fixture' && ![4,5,100,300].includes(fixtureCount))throw Error('Invalid bounded fixture size');
    if(step==='fixture' && request.test_background!==undefined && typeof request.test_background!=='boolean')throw Error('Invalid fixture background');
    if(step==='fixture')return ps.core.executeAsModal(async context=>{
      if(owner && !Array.from(ps.app.documents).some(d=>d.id===owner.document_id) && equal(originals(),owner.originals))owner=null;
      if(owner)throw Error('An owned test document is still retained');
      if(context.isCancelled || Date.now()>request.expires_at_ms || !equal(documentTarget(),request.target))throw Error('Test document set changed');
      const saved=originals(),active=request.target.active_document_id;
      let doc;
      try {doc=await ps.app.createDocument({name:'Photoshop Menu Test '+run.slice(0,8),width:128,height:128,resolution:72,mode:'RGBColorMode',fill:request.test_background===true?'white':'transparent'});}
      catch(error){if(!equal(documentTarget(),request.target))error.resultUnknown=true;throw error;}
      if(!doc || !Number.isInteger(doc.id) || request.target.document_ids.includes(doc.id)){
        const error=Error('Test creation outcome unknown');error.resultUnknown=true;throw error;
      }
      owner={run,session,document_id:doc.id,originals:saved,original_active:active,expected:stamp(doc)};
      await batch([{_obj:'make',_target:[{_ref:'contentLayer'}],using:{_obj:'contentLayer',
        type:{_obj:'solidColorLayer',color:{_obj:'RGBColor',red:40,grain:90,blue:150}},
        shape:{_obj:'rectangle',top:{_unit:'pixelsUnit',_value:8},left:{_unit:'pixelsUnit',_value:8},
          bottom:{_unit:'pixelsUnit',_value:80},right:{_unit:'pixelsUnit',_value:80}}},_options:{dialogOptions:'dontDisplay'}}]);
      owner.shape_id=doc.activeLayers[0].id;
      owner.expected=stamp(doc);
      // A first content layer can replace the transparent starter layer.
      // Keep the historical default's three makes; explicit scale fixtures
      // instead fill to their requested REAL count on this host.
      const extra=request.test_layers===undefined?3:fixtureCount-doc.layers.length;
      if(extra<0 || extra>299)throw Error('Unexpected isolated fixture layer count');
      for(let i=0;i<extra;i++){
        if(context.isCancelled || ps.app.activeDocument.id!==owner.document_id)throw Error('Test creation cancelled or target changed');
        await batch([{_obj:'make',_target:[{_ref:'layer'}],_options:{dialogOptions:'dontDisplay'}}]);
        owner.expected=stamp(doc);
      }
      await batch([{_obj:'select',_target:[{_ref:'layer',_id:owner.shape_id}],makeVisible:false,_options:{dialogOptions:'dontDisplay'}}]);
      accept(run);return {verified:true,...await read(run)};
    },{commandName:'Menu isolated test fixture',timeOut:0});
    guard(run);
    if(['label','layer.new','layer.group'].includes(step)) {
      const target=(await read(run)).target;
      const result=await perform({...request,command:step,target,...(step==='label'?{color:request.test_color}: {})});
      accept(run);return {...result,...await read(run)};
    }
    if(!['select-shape','select-many','select-root','lock-target','undo','finish'].includes(step))throw Error('Unknown test step');
    return ps.core.executeAsModal(async context=>{
      const doc=guard(run);
      if(context.isCancelled || Date.now()>request.expires_at_ms)throw Error('Test cancelled or expired');
      if(step==='finish') {
        const original=owner.original_active;
        await doc.closeWithoutSaving();
        owner=null;
        if(original!==null) {
          const target=Array.from(ps.app.documents).find(d=>d.id===original);
          if(!target)throw Error('Original document no longer available');
          ps.app.activeDocument=target;
        }
        return {verified:true,closed_owned_document:true,original_active_restored:true};
      }
      if(step==='select-shape')await batch([{_obj:'select',_target:[{_ref:'layer',_id:owner.shape_id}],makeVisible:false,_options:{dialogOptions:'dontDisplay'}}]);
      if(step==='select-root'){
        const index=request.test_index,count=doc.layers.length;
        if(count>300 || !Number.isInteger(index) || index<0 || index>=count)throw Error('Invalid bounded root selection');
        await batch([{_obj:'select',_target:[{_ref:'layer',_id:doc.layers[index].id}],makeVisible:false,_options:{dialogOptions:'dontDisplay'}}]);
      }
      if(step==='lock-target'){
        if(!['none','all','position'].includes(request.test_lock) || doc.activeLayers.length!==1)throw Error('Invalid test lock');
        const layer=doc.activeLayers[0];layer.allLocked=false;layer.positionLocked=false;
        if(request.test_lock==='all')layer.allLocked=true;
        if(request.test_lock==='position')layer.positionLocked=true;
      }
      if(step==='select-many') {
        const ids=Array.from(doc.layers).slice(0,32).map(l=>l.id);
        for(let i=0;i<ids.length;i++)await batch([{_obj:'select',_target:[{_ref:'layer',_id:ids[i]}],makeVisible:false,
          ...(i?{selectionModifier:{_enum:'selectionModifierType',_value:'addToSelection'}}:{}),_options:{dialogOptions:'dontDisplay'}}]);
      }
      if(step==='undo') {
        const states=Array.from(doc.historyStates),index=states.findIndex(s=>s.id===doc.activeHistoryState.id);
        if(index<1 || states[index-1].id!==request.restore_history)throw Error('Single undo checkpoint mismatch');
        doc.activeHistoryState=states[index-1];
        if(doc.activeHistoryState.id!==request.restore_history)throw Error('Single undo readback mismatch');
      }
      accept(run);return {verified:true,...await read(run)};
    },{commandName:'Menu isolated test '+step,timeOut:0});
  }
  return {read,guard,accept,execute};
}


// Session-local native paint clipboard. No pixels, geometry, effects or mask
// parameters are pasted; native gradient/transparency/dash attributes survive.
function createPaintClipboard(ps,session,capture,selectionContext,readTree) {
  let clipboard=null;
  const clone=v=>JSON.parse(JSON.stringify(v));
  const stable=v=>JSON.stringify(v,(k,x)=>x && !Array.isArray(x) && typeof x==='object'?
    Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])):x);
  const same=(a,b)=>stable(a)===stable(b);
  const invariantKeys=['layerKind','hasVectorMask','hasUserMask','userMaskFeather','userMaskDensity','vectorMaskFeather','vectorMaskDensity',
    'layerEffects','fillOpacity','opacity','mode','group','visible','name','layerLocking'];
  const target=(id,doc)=>[{_ref:'layer',_id:id},{_ref:'document',_id:doc}];
  async function batch(commands) {
    const values=await ps.action.batchPlay(commands,{});
    if(values.length!==commands.length || values.some(v=>!v || v._obj==='error'))throw Error(values.find(v=>v?._obj==='error')?.message || '形状外观读写失败');
    return values;
  }
  function locked(layer){for(let p=layer;p;p=p.parent)if(p.allLocked || p.locked || p.pixelsLocked || p.positionLocked || p.transparentPixelsLocked || p.isBackgroundLayer)return true;return false;}
  function guard(context,request,accepted=false){if(context.isCancelled || !accepted && Date.now()>request.expires_at_ms)throw Error('Cancelled or expired');}
  async function identity(expected){const now=await capture();if(!same(now,expected))throw Error('形状外观目标已改变');return now;}
  async function snapshot(expected,context,request,accepted=false) {
    guard(context,request,accepted);await identity(expected);
    const doc=ps.app.activeDocument;
    if(doc.mode!==ps.constants.DocumentMode.RGB || ![ps.constants.BitsPerChannelType.EIGHT,ps.constants.BitsPerChannelType.SIXTEEN].includes(doc.bitsPerChannel))throw Error('形状外观仅支持RGB8／16位文档');
    const ids=expected.layer_ids;if(!ids.length || ids.length>128)throw Error('请选择1至128个未锁定形状图层');
    const rows=[];
    for(let start=0;start<ids.length;start+=8){guard(context,request,accepted);
      rows.push(...await batch(ids.slice(start,start+8).map(id=>({_obj:'get',_target:target(id,doc.id),_options:{dialogOptions:'dontDisplay'}}))));}
    if(rows.some((v,i)=>v.layerID!==ids[i] || !v.hasVectorMask || !['solidColorLayer','gradientLayer','patternLayer'].includes(v.adjustment?.[0]?._obj)))
      throw Error('整批仅支持带矢量蒙版的形状填充图层；未修改');
    const tree=await readTree(doc),parents=new Map(tree.rows.map(v=>[v.layerID,v.parentLayerID>0?v.parentLayerID:null])),descriptors=new Map(rows.map(v=>[v.layerID,v])),checked=new Set();
    async function check(id){if(checked.has(id))return;let row=descriptors.get(id);if(!row){[row]=await batch([{_obj:'get',_target:target(id,doc.id),_options:{dialogOptions:'dontDisplay'}}]);descriptors.set(id,row);}
      const locks=row.layerLocking;if(!locks || row.layerID!==id || locks.protectAll || !tree.groups.get(id) && (row.background || locks.protectComposite || locks.protectPosition || locks.protectTransparency))throw Error('形状或祖先已锁定');
      if(!parents.has(id))throw Error('形状成员已改变');checked.add(id);const parent=parents.get(id);if(parent!==null)await check(parent);}
    for(const id of ids)await check(id);
    const paths=[];for(let start=0;start<ids.length;start+=8){guard(context,request,accepted);
      paths.push(...await batch(ids.slice(start,start+8).map(id=>({_obj:'get',_target:[{_ref:'property',_property:'pathContents'},
        {_ref:'path',_enum:'path',_value:'vectorMask'},...target(id,doc.id)],_options:{dialogOptions:'dontDisplay'}}))));}
    const orders=new Map();
    for(const row of tree.rows){const parent=parents.get(row.layerID);if(!orders.has(parent))orders.set(parent,[]);orders.get(parent).push(row.layerID);}
    const members=rows.map((v,i)=>{
      const id=ids[i],parent=parents.get(id);
      if(!paths[i]?.pathContents)throw Error('形状路径读取不完整');
      return {id,parent,order:orders.get(parent),path:paths[i].pathContents,
        invariants:Object.fromEntries(invariantKeys.map(k=>[k,v[k]??null])),
        fill:v.adjustment[0],stroke:v.AGMStrokeStyleInfo??null};
    });
    await identity(expected);
    const result={identity:expected,members};if(stable(result).length>4000000)throw Error('形状外观过于复杂，请减少批量图层');return result;
  }
  async function choose(ids,active,doc) {
    const ordered=ids.filter(id=>id!==active).concat(active);
    await batch(ordered.map((id,i)=>({_obj:'select',_target:target(id,doc),makeVisible:false,
      ...(i?{selectionModifier:{_enum:'selectionModifierType',_value:'addToSelection'}}:{}),_options:{dialogOptions:'dontDisplay'}})));
  }
  async function execute(request) {
    const copying=request.command==='shape.copyPaint';
    if(!copying && request.command!=='shape.pastePaint')throw Error('Unknown paint clipboard command');
    return ps.core.executeAsModal(async context=>{
      guard(context,request);const expected=request.target;
      if(expected?.session!==session)throw Error('形状剪贴板会话已改变');
      const before=await snapshot(expected,context,request),doc=expected.document_id;
      if(copying){
        if(before.members.length!==1)throw Error('复制形状外观需要单选');
        const {fill,stroke}=before.members[0];
        // Missing native stroke is the standard disabled stroke. A concrete
        // descriptor is needed when replacing a target's existing stroke.
        const defaultStroke={_obj:'strokeStyle',strokeStyleVersion:2,strokeEnabled:false,fillEnabled:true,
          strokeStyleLineWidth:{_unit:'pixelsUnit',_value:1},strokeStyleContent:{_obj:'solidColorLayer',color:{_obj:'RGBColor',red:0,grain:0,blue:0}}};
        const next=clone({fill,stroke:stroke??defaultStroke});if(stable(next).length>524288)throw Error('形状外观过于复杂');
        clipboard=next;return {verified:true,count:1,shape_clipboard_available:true,selection_context:selectionContext()};
      }
      if(!clipboard)throw Error('请先复制形状填充与描边；重启PS后需要重新复制');
      const wanted=clone(clipboard);let open=false,uncertain=false,history;
      try {
        guard(context,request);await identity(expected);
        history=await context.hostControl.suspendHistory({documentID:doc,name:'粘贴形状填充与描边'});open=true;
        let accepted=false;
        for(const member of before.members){
          guard(context,request,accepted);accepted=true;
          await batch([{_obj:'select',_target:target(member.id,doc),makeVisible:false,_options:{dialogOptions:'dontDisplay'}}]);
          const current=await capture();
          if(current.document_id!==doc || current.active_layer_id!==member.id || current.layer_ids.join(',')!==String(member.id))throw Error('形状粘贴目标已改变');
          await batch([{_obj:'set',_target:[{_ref:'contentLayer',_enum:'ordinal',_value:'targetEnum'}],
            to:{_obj:'shapeStyle',fillContents:clone(wanted.fill),strokeStyle:clone(wanted.stroke)},_options:{dialogOptions:'dontDisplay'}}]);
        }
        await choose(expected.layer_ids,expected.active_layer_id,doc);
        const after=await snapshot(expected,context,request,true);
        for(let i=0;i<before.members.length;i++){
          const {fill:a,stroke:b,...rest}=after.members[i],{fill,stroke,...original}=before.members[i];
          if(!same(rest,original) || !same(a,wanted.fill) || !same(b,wanted.stroke))throw Error('形状外观／路径／蒙版／顺序读回不符');
        }
        guard(context,request,true);open=false;uncertain=true;await context.hostControl.resumeHistory(history,true);uncertain=false;
        return {verified:true,count:before.members.length,placement_moves:0,shape_clipboard_available:true,selection_context:selectionContext()};
      } catch(error){
        if(open)try {
          open=false;await context.hostControl.resumeHistory(history,false);
          await choose(expected.layer_ids,expected.active_layer_id,doc);
          // Cancellation/expiry stops writes, but never suppresses rollback
          // verification. Only the original owned transaction is inspected.
          const restored=await snapshot(expected,{isCancelled:false},{...request,expires_at_ms:Date.now()+30000});
          if(!same(restored,before))uncertain=true;
        }catch(_){uncertain=true;}
        if(uncertain)error.resultUnknown=true;throw error;
      }
    },{commandName:copying?'复制形状填充与描边':'粘贴形状填充与描边',timeOut:0});
  }
  return {execute,available:()=>clipboard!==null};
}

// Cached vector-paint metadata and request-bound, one-history preview writes.
function createShapePaint(ps,session,capture,selectionContext,legacyPreview=false) {
  const batchMasks=createBatchMasks(ps,session,capture,selectionContext,legacyPreview);
  let cache=null,serial=0,catalog=[],catalogAt=0,catalogInfo={};
  const clone=value=>JSON.parse(JSON.stringify(value));
  const rgb=color=>color?._obj==='RGBColor'?[color.red,color.grain??color.green,color.blue].map(v=>Math.round(Number(v))):null;
  function paint(raw) {
    if(raw?._obj==='solidColorLayer') {const c=rgb(raw.color);return c && c.every(v=>Number.isFinite(v))?{kind:'solid',rgb:c}:null;}
    if(raw?._obj==='gradientLayer') {
      const colors=raw.gradient?.colors;
      if(!Array.isArray(colors) || colors.length<2 || colors.length>32)return null;
      const stops=colors.map(v=>({rgb:rgb(v.color),location:Math.round(v.location)}));
      const method=raw.gradientsInterpolationMethod?._value ?? 'classic';
      return stops.every(v=>v.rgb && v.rgb.every(Number.isFinite)) && ['classic','linear','perceptual'].includes(method)?{kind:'gradient',stops,method}:null;
    }
    if(raw?._obj==='patternLayer' && typeof raw.pattern?.name==='string')return {kind:'pattern',name:raw.pattern.name};
    return null;
  }
  async function patterns() {
    if(Date.now()-catalogAt<30000)return catalog;
    try {
      const [v]=await ps.action.batchPlay([{_obj:'get',_target:[{_ref:'property',_property:'presetManager'},
        {_ref:'application',_enum:'ordinal',_value:'targetEnum'}],_options:{dialogOptions:'dontDisplay'}}],{});
      catalogInfo={keys:Object.keys(v),groups:(v.presetManager || []).map(x=>({kind:x._obj,keys:Object.keys(x),count:Array.isArray(x.name)?x.name.length:0}))};
      const group=v.presetManager?.find(x=>/pattern|PttR/i.test(x._obj || ''));
      catalog=Array.isArray(group?.name)?group.name.filter(v=>typeof v==='string' && v.length<=128).slice(0,128):[];
      catalogAt=Date.now();
    } catch(error) {catalogInfo={error:String(error)};}
    return catalog;
  }
  async function readCore(doc,id,checkpoint=null) {
    const keys=['layerKind','hasVectorMask','adjustment','AGMStrokeStyleInfo'];
    const descriptors=keys.map(key=>({_obj:'get',_target:[{_ref:'property',_property:key},
      {_ref:'layer',_id:id},{_ref:'document',_id:doc.id}],_options:{dialogOptions:'dontDisplay'}}));
    const result=[];
    if(checkpoint){for(const descriptor of descriptors){await checkpoint();result.push(...await ps.action.batchPlay([descriptor],{}));}await checkpoint();}
    else result.push(...await ps.action.batchPlay(descriptors,{}));
    const vector=result[1]?.hasVectorMask===true;
    const fill=result[2]?.adjustment?.[0],stroke=result[3]?.AGMStrokeStyleInfo;
    if(!paint(fill))return null;
    const defaultStroke={_obj:'strokeStyle',strokeStyleVersion:2,strokeEnabled:false,fillEnabled:true,
      strokeStyleLineWidth:{_unit:'pixelsUnit',_value:1},strokeStyleContent:{_obj:'solidColorLayer',color:{_obj:'RGBColor',red:0,grain:0,blue:0}}};
    const actualStroke=vector?(stroke || defaultStroke):defaultStroke;
    if(actualStroke.strokeStyleLineWidth && !['pixelsUnit','pointsUnit'].includes(actualStroke.strokeStyleLineWidth._unit))return null;
    if(!paint(actualStroke.strokeStyleContent))return null;
    const raw={fill,stroke:actualStroke,vector};
    if(vector) {
      // Read only while enriching an eligible shape, never on the basic
      // snapshot path or ordinary fill layers. Unknown values stay unavailable.
      const layer=doc.activeLayers[0];
      if(!layer || layer.id!==id)return null;
      try {
        const feather=layer.vectorMaskFeather,density=layer.vectorMaskDensity;
        if(typeof feather==='number' && Number.isFinite(feather) && feather>=0 && feather<=1000 &&
           typeof density==='number' && Number.isFinite(density) && density>=0 && density<=100)
          raw.mask={feather,density};
      } catch(_) {}
    }
    return raw;
  }
  async function observe(context,force=false,frozenCatalog=null,checkpoint=null) {
    if(context.layer_ids?.length>1)return batchMasks.observe(context,checkpoint);
    if(context.kind!=='shape-fill' || context.layer_ids?.length!==1 || context.locked || !ps.app.documents.length)
      return {available:false};
    const doc=ps.app.activeDocument,id=context.layer_ids[0],key=doc.id+':'+id;
    if(!force && cache?.key===key && Date.now()-cache.at<500)return cache.data;
    if(doc.mode!==ps.constants.DocumentMode.RGB || ![ps.constants.BitsPerChannelType.EIGHT,ps.constants.BitsPerChannelType.SIXTEEN].includes(doc.bitsPerChannel))
      return {available:false};
    if(checkpoint)await checkpoint();
    const raw=await readCore(doc,id,checkpoint);
    if(!raw) {cache={key,at:Date.now(),data:{available:false}};return cache.data;}
    if(ps.app.activeDocument.id!==doc.id || doc.activeLayers.length!==1 || doc.activeLayers[0].id!==id)
      return {available:false};
    const signature=JSON.stringify(raw),revision=cache?.key===key && cache.signature===signature?cache.data.revision:session+':'+(++serial);
    const fill={...paint(raw.fill),enabled:raw.stroke.fillEnabled!==false};
    const stroke={...paint(raw.stroke.strokeStyleContent),enabled:!!raw.stroke.strokeEnabled,
      width:Number(raw.stroke.strokeStyleLineWidth?._value ?? 1)*(raw.stroke.strokeStyleLineWidth?._unit==='pointsUnit'?doc.resolution/72:1)};
    // A live transaction needs only the frozen editor catalog. Refreshing
    // application-wide presets mid-drag adds unrelated host work, and cannot
    // make a newly added pattern valid for the original frozen editor anyway.
    if(checkpoint)await checkpoint();
    const data={available:true,vector:raw.vector,live_preview:typeof ps.core.redrawDocument==='function' || legacyPreview,
      ...(legacyPreview && typeof ps.core.redrawDocument!=='function'?{preview_engine:'legacy-com'}:{}),revision,fill,stroke,
      patterns:frozenCatalog?frozenCatalog.patterns:await patterns(),
      pattern_catalog:frozenCatalog?frozenCatalog.pattern_catalog:catalogInfo};
    if(checkpoint)await checkpoint();
    if(raw.mask)data.mask=clone(raw.mask);
    cache={key,at:Date.now(),signature,raw,data};return data;
  }
  function validatePaint(value) {
    if(!value || !['solid','gradient','pattern'].includes(value.kind) || typeof value.enabled!=='boolean')throw Error('Invalid paint type');
    const color=c=>Array.isArray(c) && c.length===3 && c.every(v=>typeof v==='number' && Number.isFinite(v) && v>=0 && v<=255);
    if(value.kind==='solid' && !color(value.rgb))throw Error('Invalid RGB color');
    if(value.kind==='gradient' && (!Array.isArray(value.stops) || value.stops.length<2 || value.stops.length>32 ||
      value.stops.some((s,i)=>!color(s.rgb) || !Number.isInteger(s.location) || s.location<0 || s.location>4096 || i && s.location<value.stops[i-1].location)))throw Error('Invalid gradient stops');
    if(value.kind==='pattern' && (typeof value.name!=='string' || !value.name || value.name.length>128))throw Error('Invalid pattern name');
    if(value.kind==='gradient' && value.method!==undefined && !['classic','linear','perceptual'].includes(value.method))throw Error('Invalid gradient interpolation');
  }
  function build(value,previous) {
    if(value.kind==='solid')return {_obj:'solidColorLayer',color:{_obj:'RGBColor',red:value.rgb[0],grain:value.rgb[1],blue:value.rgb[2]}};
    if(value.kind==='pattern') {
      if(!catalog.includes(value.name) && previous?.pattern?.name!==value.name)throw Error('图案预设已改变，请重新打开菜单');
      const next=previous?._obj==='patternLayer'?clone(previous):{_obj:'patternLayer'};
      next.pattern=previous?.pattern?.name===value.name?clone(previous.pattern):{_obj:'pattern',name:value.name};return next;
    }
    const next=previous?._obj==='gradientLayer'?clone(previous):{_obj:'gradientLayer',type:{_enum:'gradientType',_value:'linear'},
      angle:{_unit:'angleUnit',_value:0},scale:{_unit:'percentUnit',_value:100}};
    const old=next.gradient || {};
    if(value.method!==undefined)next.gradientsInterpolationMethod={_enum:'gradientInterpolationMethodType',_value:value.method};
    next.gradient={...old,_obj:'gradientClassEvent',name:old.name || 'Menu gradient',gradientForm:{_enum:'gradientForm',_value:'customStops'},
      interfaceIconFrameDimmed:4096,colors:value.stops.map((s,i)=>({_obj:'colorStop',
        color:{_obj:'RGBColor',red:s.rgb[0],grain:s.rgb[1],blue:s.rgb[2]},type:{_enum:'colorStopType',_value:'userStop'},
        location:s.location,midpoint:old.colors?.[i]?.midpoint ?? 50})),
      transparency:old.transparency || [0,4096].map(location=>({_obj:'transferSpec',opacity:{_unit:'percentUnit',_value:100},location,midpoint:50}))};
    return next;
  }
  function samePaint(actual,wanted) {
    if(!actual || actual.kind!==wanted.kind || actual.enabled!==wanted.enabled)return false;
    const close=(a,b)=>a.length===b.length && a.every((v,i)=>Math.abs(v-b[i])<=1);
    if(actual.kind==='solid')return close(actual.rgb,wanted.rgb);
    if(actual.kind==='pattern')return actual.name===wanted.name;
    return (wanted.method===undefined || actual.method===wanted.method) && actual.stops.length===wanted.stops.length && actual.stops.every((s,i)=>s.location===wanted.stops[i].location && close(s.rgb,wanted.stops[i].rgb));
  }
  function validateParams(params) {
    if(!params || typeof params.revision!=='string' || params.revision.length>128)throw Error('Missing shape revision');
    validatePaint(params.fill);validatePaint(params.stroke);
    if(typeof params.stroke.width!=='number' || !Number.isFinite(params.stroke.width) || params.stroke.width<0 || params.stroke.width>1000)throw Error('Invalid stroke width');
    if(Object.prototype.hasOwnProperty.call(params,'mask') && (!params.mask || typeof params.mask!=='object' ||
      Object.keys(params.mask).sort().join(',')!=='density,feather' ||
      typeof params.mask.feather!=='number' || !Number.isFinite(params.mask.feather) || params.mask.feather<0 || params.mask.feather>1000 ||
      typeof params.mask.density!=='number' || !Number.isFinite(params.mask.density) || params.mask.density<0 || params.mask.density>100))throw Error('Invalid vector mask');
  }
  async function redrawPreview(identity,io) {
    // Use only the host document redraw API (PS24.1+). Nested JSX refresh
    // under PS24.0 can remain blocked, even after Cancel Plugin Command.
    const started=Date.now();
    if(io?.stage)await io.stage('redraw-target');
    const [value]=await ps.action.batchPlay([{_obj:'get',_target:[
      {_ref:'property',_property:'layerID'},{_ref:'layer',_id:identity.layerID},
      {_ref:'document',_id:identity.documentID}],_options:{dialogOptions:'silent'}}],{});
    if(value?._obj==='error' || value?.layerID!==identity.layerID)throw Error('Photoshop 预览刷新目标校验失败');
    if(ps.app.activeDocument.id!==identity.documentID || ps.app.activeDocument.activeLayers.length!==1 ||
        ps.app.activeDocument.activeLayers[0].id!==identity.layerID)throw Error('Preview target changed before redraw');
    if(typeof ps.core.redrawDocument!=='function')throw Error('当前PS使用本地草稿，实时预览需要PS24.1及官方重绘API');
    if(io?.stage)await io.stage('redraw-native');
    await ps.core.redrawDocument({documentID:identity.documentID});
    const method='core.redrawDocument';
    return {redraw_method:method,redraw_ms:Date.now()-started};
  }
  async function previewMask(context,request,before,doc,anchor,identity,io,applyPaint) {
    if(!io || typeof io.read!=='function')throw Error('Missing preview mailbox');
    let seq=0,lease=Date.now()+4000,applied=before.mask?clone(before.mask):undefined,updates=0,maxWriteMs=0;
    const close=(a,b)=>!a&&!b || !!a&&!!b&&Math.abs(a.feather-b.feather)<=.01 && Math.abs(a.density-b.density)<=100/255+.001;
    const read=()=>({feather:anchor.vectorMaskFeather,density:anchor.vectorMaskDensity});
    const target=()=>ps.app.activeDocument.id===identity.documentID && doc.activeLayers.length===1 &&
      doc.activeLayers[0].id===identity.layerID && !anchor.allLocked;
    while(true) {
      if(context.isCancelled)throw Error('Photoshop cancelled preview');
      if(io.stage)await io.stage('read-control',seq);
      const packet=await io.read(),now=Date.now();
      if(packet) {
        if(packet.id!==request.id || packet.session!==request.session || packet.token!==request.token ||
          !Number.isSafeInteger(packet.seq) || packet.seq<seq ||
          !Number.isFinite(packet.lease_until_ms) || packet.lease_until_ms>now+5000 ||
          !['preview','commit','cancel'].includes(packet.phase))throw Error('Invalid preview identity or lease');
        lease=packet.lease_until_ms;
        if(lease<now)return {cancelled:true,updates,max_write_ms:maxWriteMs,reason:'lease-expired'};
        if(!target())throw Error('Preview target changed');
        if(packet.phase==='cancel')return {cancelled:true,updates,max_write_ms:maxWriteMs,reason:'cancel'};
        validateParams(packet.paint);
        if(packet.paint.revision!==before.revision || !!packet.paint.mask!==!!request.paint.mask)throw Error('Preview revision changed');
        if(applied && !close(read(),applied))throw Error('Vector mask changed outside preview');
        if(packet.seq>seq || packet.phase==='commit') {
          if(io.stage)await io.stage('validate-frame',packet.seq);
          const wanted=packet.paint.mask || before.mask,started=Date.now();
          const maskChanged=!close(applied,wanted);
          const {changed:colorChanged,...colors}=await applyPaint(packet.paint);
          if(packet.phase==='commit')return {paint:packet.paint,updates,max_write_ms:Math.max(maxWriteMs,Date.now()-started)};
          if(wanted && maskChanged) {
            // Same properties/units as Adobe's DOM setters, with an async
            // modifying batch so PS24.0 can flush the final combined frame.
            const to={_obj:'layer'};
            if(wanted.feather!==applied.feather)to.vectorMaskFeather={_unit:'pixelsUnit',_value:wanted.feather};
            if(wanted.density!==applied.density)to.vectorMaskDensity={_unit:'percentUnit',_value:wanted.density};
            // Photoshop's layer setter processes these mask properties one at
            // a time. Keep both descriptors in one batch and redraw once.
            const descriptors=Object.entries(to).filter(([key])=>key!=='_obj').map(([key,value])=>({
              _obj:'set',_target:[{_ref:'layer',_id:identity.layerID},{_ref:'document',_id:identity.documentID}],
              to:{_obj:'layer',[key]:value},_options:{dialogOptions:'silent'}}));
            if(io.stage)await io.stage('write-mask');
            const responses=await ps.action.batchPlay(descriptors,{});
            for(const response of responses)if(response?._obj==='error')throw Error(response.message || 'Photoshop 拒绝蒙版预览');
            if(io.stage)await io.stage('read-mask');
            applied=read();
          }
          if(!target() || !close(applied,wanted))throw Error('Preview mask readback mismatch');
          const redrawCompleted=!!(colorChanged || maskChanged);
          const redraw=redrawCompleted?await redrawPreview(identity,io):{};
          if(!target())throw Error('Preview target changed during redraw');
          updates++;maxWriteMs=Math.max(maxWriteMs,Date.now()-started);seq=packet.seq;
          if(io.stage)await io.stage('publish-frame');
          if(io.applied)await io.applied({seq,...colors,...(applied?{mask:applied}:{}),updates,max_write_ms:maxWriteMs,redraw_completed:redrawCompleted,...redraw});
        }
      }
      // A slow Photoshop redraw may outlast the previously read lease. Read
      // the current mailbox before expiring a still-renewed live session.
      if(!packet && Date.now()>lease)return {cancelled:true,updates,max_write_ms:maxWriteMs,reason:'lease-expired'};
      await new Promise(resolve=>setTimeout(resolve,40));
    }
  }
  async function apply(request,previewIO=null) {
    if(request.paint?.mask_batch)return batchMasks.apply(request,previewIO);
    let params=request.paint;validateParams(params);
    const preview=request.command==='shape.preview';
    if(preview && typeof ps.core.redrawDocument!=='function')
      throw Error('当前PS使用本地草稿，实时预览需要PS24.1及官方重绘API');
    const stage=async name=>{if(previewIO?.stage)await previewIO.stage(name);};
    await stage('enter-modal');
    // Photoshop may recreate thrown errors across the native modal boundary,
    // dropping custom fields. Keep uncertainty outside that boundary.
    let uncertain=false;
    try {return await ps.core.executeAsModal(async context=>{
      await stage('capture-target');
      if(context.isCancelled || Date.now()>request.expires_at_ms)throw Error('Cancelled or expired');
      const actual=await capture(),expected=request.target;
      if(expected?.session!==session || actual.document_id!==expected.document_id || actual.active_layer_id!==expected.active_layer_id || actual.layer_ids.join(',')!==expected.layer_ids?.join(','))throw Error('Document or layer target changed');
      await stage('read-initial-paint');
      const eligibility=selectionContext(true),before=await observe(eligibility,true);
      if(!before.available || before.revision!==params.revision)throw Error('填充／描边已改变，请重新打开菜单；本次未修改');
      if(params.mask && (!before.vector || !before.mask))throw Error('当前图层不支持矢量蒙版羽化／密度；本次未修改');
      if(!before.vector && params.fill.kind!==before.fill.kind)throw Error('普通填充层保持PS原生类型；本次未修改');
      if(!before.vector && (!params.fill.enabled || params.stroke.kind!==before.stroke.kind || params.stroke.enabled!==before.stroke.enabled
          || params.stroke.width!==before.stroke.width || JSON.stringify(params.stroke.rgb)!==JSON.stringify(before.stroke.rgb)))
        throw Error('普通填充层不支持形状描边或禁用填充；本次未修改');
      const original=cache.raw,doc=ps.app.activeDocument,anchor=doc.activeLayers[0];
      const identity={documentID:doc.id,layerID:anchor.id};
      const target=()=>ps.app.activeDocument.id===identity.documentID && doc.activeLayers.length===1 &&
        doc.activeLayers[0].id===identity.layerID && !anchor.allLocked;
      const parent=anchor.parent,parentId=parent?.id ?? null,order=Array.from(parent?parent.layers:doc.layers,l=>l.id);
      let appliedPaint=before,liveColors=before,appliedRaw=original,paintTouched=false;
      const rawKey=raw=>JSON.stringify([raw.fill,raw.stroke,raw.vector]);
      let appliedRawKey=rawKey(original);
      const preparePaint=()=>{
        const key=p=>JSON.stringify([p.kind,p.enabled,p.rgb,p.stops?.map(s=>[s.location,...s.rgb]),p.name,p.width,p.method]);
        const fillChanged=key(params.fill)!==key(appliedPaint.fill),strokeChanged=key(params.stroke)!==key(appliedPaint.stroke);
        const paintChanged=fillChanged || strokeChanged;
        // Vector-backed content must use Photoshop's shapeStyle setter.
        // Direct solidColorLayer writes are unavailable in some real shapes,
        // including vector masks inherited by a newly created solid fill.
        const to=before.vector?{_obj:'shapeStyle'}:build(params.fill,original.fill);
        if(before.vector) {
          if(fillChanged)to.fillContents=build(params.fill,original.fill);
          if(strokeChanged || params.fill.enabled!==appliedPaint.fill.enabled) {
            to.strokeStyle={...clone(appliedRaw.stroke),strokeStyleVersion:2,fillEnabled:params.fill.enabled};
            if(strokeChanged)Object.assign(to.strokeStyle,{strokeEnabled:params.stroke.enabled,
              strokeStyleContent:build(params.stroke,original.stroke.strokeStyleContent)});
            if(params.stroke.width!==appliedPaint.stroke.width)
              to.strokeStyle.strokeStyleLineWidth={_unit:'pixelsUnit',_value:params.stroke.width};
          }
        }
        return {paintChanged,to};
      };
      let prepared=preparePaint();
      const applyPreviewPaint=async value=>{
        if(!target())throw Error('Preview target changed');
        params=value;
        if(!before.vector && (params.fill.kind!==before.fill.kind || !params.fill.enabled ||
          params.stroke.kind!==before.stroke.kind || params.stroke.enabled!==before.stroke.enabled ||
          params.stroke.width!==before.stroke.width || JSON.stringify(params.stroke.rgb)!==JSON.stringify(before.stroke.rgb)))
          throw Error('普通填充层保持PS原生类型与描边');
        const next=preparePaint();
        // Mask-only updates retain the cheap DOM path. Colors use four targeted
        // properties, never a document tree or per-frame pattern enumeration.
        if(next.paintChanged || paintTouched) {
          await stage('read-color-before');
          const raw=await readCore(doc,identity.layerID);
          if(!raw || rawKey(raw)!==appliedRawKey)throw Error('Fill or stroke changed outside preview');
        }
        if(!target())throw Error('Preview target changed during read');
        if(next.paintChanged) {
          await stage('write-color');
          if(!target())throw Error('Preview target changed before write');
          // PS24 contentLayer setters require the current content reference.
          // ID references can reject or silently do nothing. The frozen target
          // is checked immediately above, with no intervening await, and the
          // actual color/identity is checked again after the write.
          const [response]=await ps.action.batchPlay([{_obj:'set',_target:[{_ref:'contentLayer',_enum:'ordinal',_value:'targetEnum'}],
            to:next.to,_options:{dialogOptions:'silent'}}],{});
          if(response?._obj==='error')throw Error(response.message || 'Photoshop 拒绝颜色预览');
          await stage('read-color-after');
          // Paint validation needs fresh identity/type/ancestor locks, not
          // sibling adjacency and sort capabilities on every color frame.
          const actual=await observe(selectionContext(true),true,before);
          if(!target() || !actual.available || actual.vector!==before.vector || !samePaint(actual.fill,params.fill) ||
            !samePaint(actual.stroke,params.stroke) || Math.abs(actual.stroke.width-params.stroke.width)>.01)
            throw Error('Fill or stroke preview readback mismatch');
          appliedPaint=clone(params);liveColors=actual;appliedRaw=cache.raw;appliedRawKey=rawKey(appliedRaw);paintTouched=true;
        }
        return {fill:liveColors.fill,stroke:liveColors.stroke,changed:next.paintChanged};
      };
      if(context.isCancelled || Date.now()>request.expires_at_ms)throw Error('Cancelled or expired');
      await stage('suspend-history');
      const history=await context.hostControl.suspendHistory({documentID:doc.id,name:'Menu shape paint'});
      let historyOpen=true,committed=false;
      const originalSignature=cache.signature;
      try {
        let previewStats=null;
        if(preview) {
          const signature=cache.signature;
          previewStats=await previewMask(context,request,before,doc,anchor,identity,previewIO,applyPreviewPaint);
          if(previewStats.cancelled) {
            await stage('rollback-history');
            historyOpen=false;uncertain=true;
            await context.hostControl.resumeHistory(history,false);cache=null;
            await redrawPreview(identity,previewIO);
            await stage('verify-rollback');
            await observe(selectionContext(true),true,before);
            if(!cache || cache.signature!==signature || doc.activeLayers.length!==1 || doc.activeLayers[0].id!==anchor.id ||
              (anchor.parent?.id ?? null)!==parentId || Array.from(parent?parent.layers:doc.layers,l=>l.id).join(',')!==order.join(','))
              {const error=Error('预览回滚结果待核对');error.resultUnknown=true;throw error;}
            uncertain=false;
            return {cancelled:true,verified:true,rollback_verified:true,preview:previewStats,selection_context:selectionContext()};
          }
          params=previewStats.paint;
          prepared=preparePaint();
        }
        const {paintChanged,to}=prepared;
        if(context.isCancelled || !preview && Date.now()>request.expires_at_ms)throw Error('Cancelled or expired');
        if(!target())throw Error('Paint target changed before final write');

        if(paintChanged) {
          const [response]=await ps.action.batchPlay([{_obj:'set',_target:[{_ref:'contentLayer',_enum:'ordinal',_value:'targetEnum'}],
            to,_options:{dialogOptions:'silent'}}],{});
          if(response?._obj==='error')throw Error(response.message || 'Photoshop 拒绝修改形状颜色');
        }
        if(params.mask) {
          if(params.mask.feather!==anchor.vectorMaskFeather)anchor.vectorMaskFeather=params.mask.feather;
          if(params.mask.density!==anchor.vectorMaskDensity)anchor.vectorMaskDensity=params.mask.density;
        }
        await stage('verify-final');
        const after=await observe(selectionContext(true),true,preview?before:null);
        const wantedMask=params.mask || before.mask;
        if(wantedMask && (!after.mask || Math.abs(after.mask.feather-wantedMask.feather)>.01 ||
          Math.abs(after.mask.density-wantedMask.density)>100/255+.001))throw Error('矢量蒙版羽化／密度读回不符，已回滚');
        if(!after.available || after.vector!==before.vector || !samePaint(after.fill,params.fill) || !samePaint(after.stroke,params.stroke) || Math.abs(after.stroke.width-params.stroke.width)>.01 ||
          doc.activeLayers.length!==1 || doc.activeLayers[0].id!==anchor.id || (anchor.parent?.id ?? null)!==parentId ||
          Array.from(parent?parent.layers:doc.layers,l=>l.id).join(',')!==order.join(','))throw Error('形状颜色／图层身份读回不符，已回滚');
        await stage('commit-history');
        historyOpen=false;uncertain=true;
        await context.hostControl.resumeHistory(history,true);committed=true;uncertain=false;
        return {count:1,verified:true,placement_moves:0,fill_kind:after.fill.kind,stroke_kind:after.stroke.kind,
          ...(after.mask?{mask:after.mask}:{}),...(previewStats?{preview:previewStats}:{}),selection_context:selectionContext()};
      } catch(error) {
        await stage('rollback-error');
        uncertain=uncertain || !!error.resultUnknown || committed;
        if(historyOpen) {
          try {
            historyOpen=false;
            await context.hostControl.resumeHistory(history,false);cache=null;
            await stage('verify-error-rollback');
            await observe(selectionContext(true),true,before);
            if(!target() || !cache || cache.signature!==originalSignature ||
                (anchor.parent?.id ?? null)!==parentId ||
                Array.from(parent?parent.layers:doc.layers,l=>l.id).join(',')!==order.join(','))uncertain=true;
          } catch(_) {uncertain=true;}
        }
        throw error;
      }
    },{commandName:preview?'Menu paint preview':'Menu shape paint',timeOut:0,...(preview?{interactive:true}:{})});
    } catch(error) {
      if(uncertain) {
        const result=Error(String(error));result.resultUnknown=true;throw result;
      }
      throw error;
    }
  }
  async function prepareLegacy(request) {
    if(!legacyPreview || typeof ps.core.redrawDocument==='function')throw Error('Legacy preview channel unavailable');
    if(request.paint?.mask_batch)return batchMasks.prepareLegacy(request);
    validateParams(request.paint);
    const actual=await capture(),expected=request.target;
    if(Date.now()>request.expires_at_ms || expected?.session!==session || actual.document_id!==expected.document_id ||
      actual.active_layer_id!==expected.active_layer_id || actual.layer_ids.join(',')!==expected.layer_ids?.join(','))throw Error('Legacy preview target changed');
    const before=await observe(selectionContext(true),true);
    if(!before.available || before.revision!==request.paint.revision)throw Error('填充／描边已改变，请重新打开菜单；本次未修改');
    if(request.paint.mask && (!before.vector || !before.mask))throw Error('Vector mask unavailable');
    if(!before.vector && (request.paint.fill.kind!==before.fill.kind || !request.paint.fill.enabled ||
      JSON.stringify(request.paint.stroke)!==JSON.stringify(before.stroke)))throw Error('Ordinary fill type must remain unchanged');
    const doc=ps.app.activeDocument,anchor=doc.activeLayers[0];
    if(doc.id!==actual.document_id || doc.activeLayers.length!==1 || anchor?.id!==actual.active_layer_id)throw Error('Legacy prepare selection changed');
    return {before:clone(before),raw:clone(cache.raw),parent_id:anchor.parent?.id??null,
      order:Array.from(anchor.parent?anchor.parent.layers:doc.layers,l=>l.id)};
  }
  async function finishLegacy(request,prepared,response) {
    if(request.paint?.mask_batch)return batchMasks.finishLegacy(request,prepared,response);
    if(response.phase!=='completed') {const error=Error(response.error || 'Legacy preview failed');error.resultUnknown=response.result_unknown===true;throw error;}
    let uncertain=true;
    try {
      const result=response.result;
      if(!result || result.verified!==true || typeof result.cancelled!=='undefined' && typeof result.cancelled!=='boolean')throw Error('Invalid native preview result');
      const wanted=result.cancelled?prepared.before:result.paint;
      validateParams(wanted);
      if(wanted.revision!==request.paint.revision || result.preview?.engine!=='standalone-extendscript' || !Number.isInteger(result.preview.last_seq) || result.preview.last_seq<0 ||
        !result.cancelled && (result.placement_moves!==0 || ![0,1].includes(result.count)) || result.cancelled && result.rollback_verified!==true)throw Error('Native preview proof incomplete');
      // The native transaction read back its target, paint, vector path, pixel
      // mask and sibling order BEFORE publishing this authenticated terminal.
      // Do not reinterpret a later user selection as an unknown old write, or
      // add a duplicate paint query. Fresh selection feedback is separate.
      cache=null;
      uncertain=false;
      const {paint,...summary}=result;
      try {summary.selection_context=selectionContext();}catch(_){}
      return summary;
    } catch(error) {if(uncertain)error.resultUnknown=true;throw error;}
  }
  return {observe,apply,prepareLegacy,finishLegacy};
}

// Fixed reference-Caps actions. No menu letters, synthetic keys or IME changes.
function createCapsActions(ps,session,capture,selectionContext,readNativeTree,captureSelection) {
  const commands=['selectAbove','selectBelow','extendAbove','extendBelow','moveUp','moveDown','copyStyle','pasteStyle','editStyle','convertSmartObject'];
  async function convert(request) {
    return ps.core.executeAsModal(async context=>{
      if(context.isCancelled || Date.now()>request.expires_at_ms)throw Error('Cancelled or expired');
      const expected=request.target,actual=await capture();
      if(expected?.session!==session || actual.document_id!==expected.document_id || actual.active_layer_id!==expected.active_layer_id || actual.layer_ids.join(',')!==expected.layer_ids?.join(','))
        throw Error('Smart object target changed');
      const doc=ps.app.activeDocument,k=ps.constants.LayerKind;
      function tree(layers,parent=null) {return Array.from(layers).flatMap(l=>[{layer:l,id:l.id,parent},...(l.kind===k.GROUP?tree(l.layers,l.id):[])]);}
      const before=tree(doc.layers),selected=before.filter(l=>actual.layer_ids.includes(l.id));
      if(selected.length!==actual.layer_ids.length)throw Error('Smart object target missing');
      const parent=selected[0].parent;
      if(selected.some(l=>l.parent!==parent))throw Error('请在同一父组内选择要转换的图层');
      if(selected.length===1 && selected[0].layer.kind===k.SMARTOBJECT)
        return {verified:true,unchanged:true,count:1,command:'convertSmartObject',selection_context:selectionContext()};
      const removed=new Set();
      function packed(l){removed.add(l.id);if(l.kind===k.GROUP)for(const child of l.layers)packed(child);}
      for(const item of selected)packed(item.layer);
      const unchanged=before.filter(l=>!removed.has(l.id)).map(l=>[l.id,l.parent]);
      if(context.isCancelled || Date.now()>request.expires_at_ms)throw Error('Cancelled or expired');
      const history=await context.hostControl.suspendHistory({documentID:doc.id,name:'Menu convert smart object'});
      try {
        const results=await ps.action.batchPlay([{_obj:'newPlacedLayer',_options:{dialogOptions:'dontDisplay'}}],{});
        if(results.some(v=>v._obj==='error'))throw Error('Photoshop 拒绝转换智能对象');
        const after=await capture(),now=tree(doc.layers),made=now.find(l=>l.id===after.active_layer_id);
        if(after.document_id!==actual.document_id || after.layer_ids.length!==1 || !made || made.layer.kind!==k.SMARTOBJECT || made.parent!==parent ||
           JSON.stringify(now.filter(l=>l.id!==made.id).map(l=>[l.id,l.parent]))!==JSON.stringify(unchanged))
          throw Error('智能对象类型／选择／原图层顺序读回不符，已回滚');
        const selection=selectionContext();
        await context.hostControl.resumeHistory(history,true);
        return {verified:true,count:selected.length,command:'convertSmartObject',smart_object_id:made.id,selection_context:selection};
      } catch(error) {
        try {await context.hostControl.resumeHistory(history,false);}catch(_){error.resultUnknown=true;}
        throw error;
      }
    },{commandName:'Menu convert smart object',timeOut:0});
  }
  async function select(request) {
    const timings={},started=Date.now();
    return ps.core.executeAsModal(async context=>{
      timings.modal_wait_ms=Date.now()-started;
      const check=()=>{if(context.isCancelled || Date.now()>request.expires_at_ms)throw Error('Cancelled or expired');};
      check();let at=Date.now();
      const actual=await captureSelection(),expected=request.target;
      if(actual.document_id!==expected.document_id || actual.active_layer_id!==expected.active_layer_id || actual.layer_ids.join(',')!==expected.layer_ids?.join(','))throw Error('Caps target changed');
      timings.target_ms=Date.now()-at;
      const doc=ps.app.activeDocument;
      function walk(layers){return Array.from(layers).flatMap(l=>[l,...(l.kind===ps.constants.LayerKind.GROUP?walk(l.layers):[])]);}
      async function order(){
        if(doc.layers.length>=8)try{return (await readNativeTree(doc)).order;}catch(_){}
        return walk(doc.layers).map(l=>l.id);
      }
      at=Date.now();const before=await order(),members=new Set(before);
      if(!actual.layer_ids.length || !actual.layer_ids.includes(actual.active_layer_id) || actual.layer_ids.some(id=>!members.has(id)))throw Error('Caps target missing');
      timings.before_tree_ms=Date.now()-at;check();
      const command=request.command,extend=command.startsWith('extend');
      const step={_obj:'select',_target:[{_ref:'layer',_enum:'ordinal',_value:command.endsWith('Above')?'forwardEnum':'backwardEnum'}],makeVisible:false,_options:{dialogOptions:'dontDisplay'}};
      if(extend)step.selectionModifier={_enum:'selectionModifierType',_value:'addToSelection'};
      const descriptors=[];
      if(!extend && actual.layer_ids.length>1)descriptors.push({_obj:'select',_target:[{_ref:'layer',_id:actual.active_layer_id}],makeVisible:false,_options:{dialogOptions:'dontDisplay'}});
      descriptors.push(step);at=Date.now();
      const results=await ps.action.batchPlay(descriptors,{});
      const rejected=results.find(v=>v._obj==='error');
      if(rejected) {
        if(rejected.result===-128)return {verified:true,cancelled:true,count:0,command,selection_context:selectionContext(),selection_timings_ms:timings};
        throw Error(rejected.message||'Photoshop rejected selection');
      }
      timings.select_ms=Date.now()-at;at=Date.now();
      const after=await captureSelection(),now=await order();
      if(after.document_id!==actual.document_id || now.length!==before.length || now.some(id=>!members.has(id)))throw Error('Caps document/layer identity changed');
      if(extend?actual.layer_ids.some(id=>!after.layer_ids.includes(id)):after.layer_ids.length!==1)throw Error('Layer selection readback mismatch');
      if(now.join(',')!==before.join(','))throw Error('Caps layer order changed');
      timings.after_tree_ms=Date.now()-at;at=Date.now();
      const feedback=selectionContext();
      // No deferred old snapshot: complete only with current capabilities.
      if(feedback.document_id!==after.document_id || feedback.layer_ids.join(',')!==after.layer_ids.join(','))throw Error('Caps feedback identity changed');
      timings.feedback_ms=Date.now()-at;
      return {verified:true,count:actual.layer_ids.length,command,selection_context:feedback,selection_timings_ms:timings};
    },{commandName:'Menu '+request.command,timeOut:0});
  }
  async function execute(request) {
    const command=request.command,expected=request.target;
    if(!commands.includes(command) || expected?.session!==session)throw Error('Unsupported Caps command/session');
    if(command==='convertSmartObject')return convert(request);
    if(['selectAbove','selectBelow','extendAbove','extendBelow'].includes(command))return select(request);
    return ps.core.executeAsModal(async context=>{
      if(context.isCancelled || Date.now()>request.expires_at_ms)throw Error('Cancelled or expired');
      const actual=await capture();
      if(actual.document_id!==expected.document_id || actual.active_layer_id!==expected.active_layer_id || actual.layer_ids.join(',')!==expected.layer_ids?.join(','))throw Error('Caps target changed');
      const doc=ps.app.activeDocument;
      function walk(layers){return Array.from(layers).flatMap(l=>[l,...(l.kind===ps.constants.LayerKind.GROUP?walk(l.layers):[])]);}
      async function readOrder() {
        // Keep full before/after tree validation. Large flat documents use
        // the already validated scalar reader, not per-layer DOM objects.
        if(doc.layers.length>=64)try {return (await readNativeTree(doc)).order;}catch(_){}
        return walk(doc.layers).map(l=>l.id);
      }
      const order=await readOrder(),membership=new Set(order);
      const selected=Array.from(doc.activeLayers),active=selected.find(l=>l.id===actual.active_layer_id);
      if(context.isCancelled || Date.now()>request.expires_at_ms)throw Error('Cancelled or expired');
      if(!active || selected.length!==actual.layer_ids.length || selected.some(l=>!actual.layer_ids.includes(l.id) || !membership.has(l.id)))throw Error('Caps target missing');
      if(['copyStyle','editStyle'].includes(command) && selected.length!==1)throw Error('此操作需要单选图层');
      const selecting=['selectAbove','selectBelow','extendAbove','extendBelow'].includes(command);
      const mutate=!selecting && command!=='copyStyle';
      if(mutate && selected.some(l=>l.isBackgroundLayer || l.allLocked || l.positionLocked))throw Error('请先解锁目标图层');
      async function batch(descriptors){const values=await ps.action.batchPlay(descriptors,{});if(values.some(v=>v._obj==='error')){const v=values.find(v=>v._obj==='error');const e=Error(v.message || 'Photoshop rejected command');e.cancelled=v.result===-128;throw e;}return values;}
      async function effects(){const [v]=await batch([{_obj:'get',_target:[{_ref:'layer',_id:active.id},{_ref:'document',_id:doc.id}],_options:{dialogOptions:'dontDisplay'}}]);return v.layerEffects;}
      let history=null;
      if(mutate && command!=='editStyle')history=await context.hostControl.suspendHistory({documentID:doc.id,name:'Menu '+command});
      try {
        if(selecting) {
          const descriptor={_obj:'select',_target:[{_ref:'layer',_enum:'ordinal',_value:command.endsWith('Above')?'forwardEnum':'backwardEnum'}],makeVisible:false,_options:{dialogOptions:'dontDisplay'}};
          if(command.startsWith('extend'))descriptor.selectionModifier={_enum:'selectionModifierType',_value:'addToSelection'};
          // Ordinal selection over a full multi-selection may keep every layer.
          // Collapse to the verified active ID before stepping, in this same
          // modal request and batch. Shift extension never collapses the range.
          const descriptors=[];
          if(!command.startsWith('extend') && selected.length>1)
            descriptors.push({_obj:'select',_target:[{_ref:'layer',_id:active.id}],makeVisible:false,_options:{dialogOptions:'dontDisplay'}});
          descriptors.push(descriptor);
          await batch(descriptors);
        } else if(command==='moveUp' || command==='moveDown') {
          const parent=active.parent,parentId=parent?.id??null;
          if(selected.some(l=>(l.parent?.id??null)!==parentId))throw Error('请在同一父组内移动');
          const siblings=Array.from(parent?parent.layers:doc.layers),indices=siblings.map((l,i)=>actual.layer_ids.includes(l.id)?i:-1).filter(i=>i>=0);
          if(indices.length!==selected.length || indices.at(-1)-indices[0]+1!==indices.length)throw Error('请先选择相邻图层');
          const up=command==='moveUp',anchor=siblings[up?indices[0]-1:indices.at(-1)+1];
          if(anchor && !anchor.isBackgroundLayer){const chosen=siblings.filter(l=>actual.layer_ids.includes(l.id));for(const layer of up?chosen:chosen.reverse())await layer.move(anchor,up?ps.constants.ElementPlacement.PLACEBEFORE:ps.constants.ElementPlacement.PLACEAFTER);}
          const next=Array.from(parent?parent.layers:doc.layers,l=>l.id),expectedOrder=siblings.map(l=>l.id);
          if(anchor && !anchor.isBackgroundLayer){const chosen=expectedOrder.filter(id=>actual.layer_ids.includes(id)),others=expectedOrder.filter(id=>!actual.layer_ids.includes(id));let at=others.indexOf(anchor.id)+(up?0:1);others.splice(at,0,...chosen);if(next.join(',')!==others.join(','))throw Error('Step order readback mismatch');}
        } else if(command==='copyStyle') {
          if(!await effects())throw Error('当前图层没有可复制的样式');
          await batch([{_obj:'copyEffects',_options:{dialogOptions:'dontDisplay'}}]);
        } else if(command==='pasteStyle') {
          await batch([{_obj:'pasteEffects',_options:{dialogOptions:'dontDisplay'}}]);
          const values=await batch(selected.map(l=>({_obj:'get',_target:[{_ref:'layer',_id:l.id},{_ref:'document',_id:doc.id}],_options:{dialogOptions:'dontDisplay'}})));
          if(values.some(v=>!v.layerEffects))throw Error('粘贴样式未通过读回核验');
        } else {
          // Photoshop edits the current effects object in its own dialog.
          // Never replace existing effects with an empty object before showing.
          const value=await effects() || {_obj:'layerEffects',scale:{_unit:'percentUnit',_value:100}};
          await batch([{_obj:'set',_target:[{_ref:'property',_property:'layerEffects'},{_ref:'layer',_id:active.id}],to:value,_options:{dialogOptions:'display'}}]);
        }
        const after=await capture(),now=await readOrder();
        if(after.document_id!==actual.document_id || now.length!==order.length || now.some(id=>!membership.has(id)))throw Error('Caps document/layer identity changed');
        if(!selecting && after.layer_ids.join(',')!==actual.layer_ids.join(','))throw Error('Caps selection changed');
        if(selecting && (command.startsWith('extend')?actual.layer_ids.some(id=>!after.layer_ids.includes(id)):after.layer_ids.length!==1))throw Error('Layer selection readback mismatch');
        if(!['moveUp','moveDown'].includes(command) && now.join(',')!==order.join(','))throw Error('Caps layer order changed');
        if(history)await context.hostControl.resumeHistory(history,true);
        return {verified:true,count:selected.length,command,selection_context:selectionContext()};
      } catch(error) {
        if(history){try{await context.hostControl.resumeHistory(history,false);}catch(_){error.resultUnknown=true;}}
        if(error.cancelled)return {verified:true,cancelled:true,count:0,command,selection_context:selectionContext()};
        throw error;
      }
    },{commandName:'Menu '+command,interactive:command==='editStyle',timeOut:0});
  }
  return {commands,execute};
}

// Selected vector masks only. No selection changes, paint setters or per-frame history.
function createBatchMasks(ps,session,capture,selectionContext,legacyPreview) {
  const clone=v=>JSON.parse(JSON.stringify(v)),same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
  let cache=null,serial=0;
  const contentKeys=['layerKind','adjustment','AGMStrokeStyleInfo','hasVectorMask','hasUserMask','userMaskFeather','userMaskDensity'];
  const close=(a,b)=>Math.abs(a.feather-b.feather)<.01 && Math.abs(a.density-b.density)<=100/255+.001;
  function validate(p) {
    if(!p || p.mask_batch!==true || Object.keys(p).sort().join(',')!=='mask,mask_batch,revision' || typeof p.revision!=='string' || !p.revision || p.revision.length>128 ||
        !p.mask || !Object.keys(p.mask).length || Object.keys(p.mask).some(k=>!['feather','density'].includes(k) || typeof p.mask[k]!=='number' || !Number.isFinite(p.mask[k]) || p.mask[k]<0 || p.mask[k]>(k==='feather'?1000:100)))throw Error('Invalid batch mask parameters');
  }
  function locked(layer) {for(let p=layer;p;p=p.parent)if(p.locked || p.allLocked || p.pixelsLocked || p.positionLocked || p.transparentPixelsLocked || p.isBackgroundLayer)return true;return false;}
  function targetSame(a,b) {return a.session===b?.session && a.document_id===b.document_id && a.active_layer_id===b.active_layer_id && same(a.layer_ids,b.layer_ids);}
  async function snapshot(expected=null,checkpoint=null) {
    const identity=await capture();if(expected && !targetSame(identity,expected))throw Error('批量蒙版选择已改变');
    const doc=ps.app.activeDocument,layers=Array.from(doc.activeLayers).sort((a,b)=>a.id-b.id);
    async function checkLocks(){for(let i=0;i<layers.length;i++){if(checkpoint && i%4===0)await checkpoint();if(locked(layers[i]))return false;}return true;}
    if(layers.length<2 || layers.length>128 || !await checkLocks())throw Error('请选择2至128个未锁定的矢量蒙版图层');
    async function read(descriptors){
      if(!checkpoint)return ps.action.batchPlay(descriptors,{});
      const values=[];for(let i=0;i<descriptors.length;i+=4){await checkpoint();values.push(...await ps.action.batchPlay(descriptors.slice(i,i+4),{}));}await checkpoint();return values;
    }
    const descriptors=await read(layers.map(l=>({_obj:'get',_target:[{_ref:'layer',_id:l.id},{_ref:'document',_id:doc.id}],_options:{dialogOptions:'dontDisplay'}})));
    if(descriptors.length!==layers.length || descriptors.some((v,i)=>v?._obj==='error' || v?.layerID!==layers[i].id || v.hasVectorMask!==true))throw Error('所有选中图层都必须有矢量蒙版');
    const paths=await read(layers.map(l=>({_obj:'get',_target:[{_ref:'property',_property:'pathContents'},
      {_ref:'path',_enum:'path',_value:'vectorMask'},{_ref:'layer',_id:l.id},{_ref:'document',_id:doc.id}],_options:{dialogOptions:'dontDisplay'}})));
    const parents=new Map();
    const members=[];for(let i=0;i<layers.length;i++){
      if(checkpoint && i%4===0)await checkpoint();
      const l=layers[i];
      const mask={feather:l.vectorMaskFeather,density:l.vectorMaskDensity},parent=l.parent?.id??null;
      if(!Number.isFinite(mask.feather)||mask.feather<0||mask.feather>1000||!Number.isFinite(mask.density)||mask.density<0||mask.density>100 || !paths[i]?.pathContents)throw Error('矢量蒙版读回不可用');
      if(!parents.has(parent)){
        const siblings=l.parent?l.parent.layers:doc.layers;
        if(!checkpoint)parents.set(parent,Array.from(siblings,x=>x.id));
        else {const order=[],count=siblings.length;for(let j=0;j<count;j++){if(j%8===0)await checkpoint();order.push(siblings[j].id);}parents.set(parent,order);}
      }
      members.push({id:l.id,mask,content:Object.fromEntries(contentKeys.map(k=>[k,descriptors[i][k]??null])),path:paths[i].pathContents,parent_id:parent,order:parents.get(parent)});
    }
    if(!targetSame(await capture(),identity) || !await checkLocks())throw Error('批量蒙版读取期间选择已改变');
    return {identity,members};
  }
  async function observe(context,checkpoint=null) {
    try {
      if(context.locked || context.background || !Array.isArray(context.layer_ids) || context.layer_ids.length<2 || context.layer_ids.length>128)return {available:false};
      if(checkpoint)await checkpoint();
      const snap=await snapshot(null,checkpoint);
      if(snap.identity.document_id!==context.document_id || !same(snap.identity.layer_ids,context.layer_ids))return {available:false};
      const signature=JSON.stringify(snap);if(signature.length>524288)throw Error('所选矢量路径过于复杂，请减少批量图层');
      const revision=cache?.signature===signature?cache.data.revision:session+':batch:'+ ++serial;
      const mask=clone(snap.members[0].mask),mixed=Object.fromEntries(['feather','density'].map(k=>[k,snap.members.some(v=>Math.abs(v.mask[k]-mask[k])>(k==='feather'?.01:100/255+.001))]));
      const data={available:true,mask_batch:true,vector:true,revision,mask,mixed,layer_ids:snap.identity.layer_ids,active_layer_id:snap.identity.active_layer_id,
        live_preview:typeof ps.core.redrawDocument==='function'||legacyPreview,...(legacyPreview && typeof ps.core.redrawDocument!=='function'?{preview_engine:'legacy-com'}:{})};
      cache={signature,data,snap};return data;
    } catch(error) {if(error.menuReadInterrupted)throw error;return {available:false,reason:String(error).slice(0,200)};}
  }
  async function prepare(request) {
    validate(request.paint);
    if(Date.now()>request.expires_at_ms)throw Error('Batch request expired');
    const before=await observe(selectionContext(true));
    if(!before.available || before.revision!==request.paint.revision || !targetSame(cache.snap.identity,request.target))throw Error('批量蒙版或选择已改变，请重新打开菜单');
    return {before:clone(before),members:clone(cache.snap.members),identity:clone(cache.snap.identity)};
  }
  async function prepareLegacy(request) {
    // Older backends do not promise the exact native baseline check. Keep
    // their original complete preparation, including after a plugin-only update.
    if(request.native_batch_validation!==2)return prepare(request);
    validate(request.paint);
    const observed=cache;
    if(Date.now()>request.expires_at_ms || !observed || observed.data.revision!==request.paint.revision ||
        !targetSame(observed.snap.identity,request.target))throw Error('批量蒙版预览已失效，请重新打开菜单');
    // The observed snapshot supplies the expected values, never authority to
    // write. The standalone executor rereads every member/content/path/order
    // and checks exact original masks before opening history or mutating PS.
    // Do not duplicate that complete host read here or start a second modal.
    if(!targetSame(await capture(),request.target) || Date.now()>request.expires_at_ms)throw Error('批量蒙版选择已改变');
    // Preserve the observed double without decimal parsing in ExtendScript.
    // Its number-to-string/parser precision differs from the UXP runtime.
    const doubleHex=value=>{const view=new DataView(new ArrayBuffer(8));view.setFloat64(0,value,false);
      return Array.from({length:8},(_,i)=>view.getUint8(i).toString(16).padStart(2,'0')).join('');};
    const members=clone(observed.snap.members).map(m=>({...m,mask_exact:{feather:doubleHex(m.mask.feather),density:Math.round(m.mask.density*255/100)}}));
    return {before:clone(observed.data),members,identity:clone(observed.snap.identity),native_batch_validation:2};
  }
  function check(actual,baseline,masks) {
    if(!targetSame(actual.identity,baseline.identity) || actual.members.length!==baseline.members.length)throw Error('Batch identity changed');
    for(let i=0;i<actual.members.length;i++){
      const {mask:a,...rest}=actual.members[i],{mask:b,...base}=baseline.members[i];
      if(!same(rest,base) || !close(a,masks[i]))throw Error('Batch mask/content/path/order readback mismatch');
    }
  }
  async function finishLegacy(request,prepared,response) {
    if(response.phase!=='completed'){const e=Error(response.error||'Batch native preview failed');e.resultUnknown=response.result_unknown===true;throw e;}
    try {
      const v=response.result;validate(v.paint);
      if(v.verified!==true || v.mask_batch!==true || !same(v.layer_ids,request.target.layer_ids) || !Number.isInteger(v.count) || v.count<0 || v.count>prepared.members.length || v.placement_moves!==0 ||
          v.paint.revision!==request.paint.revision || v.preview?.engine!=='standalone-extendscript' || !Number.isInteger(v.preview.last_seq) ||
          v.cancelled && v.rollback_verified!==true || !Array.isArray(v.masks) || v.masks.length!==prepared.members.length)throw Error('Incomplete batch proof');
      for(let i=0;i<v.masks.length;i++)if(v.masks[i].id!==prepared.members[i].id || !close(v.masks[i].mask,{...prepared.members[i].mask,...(v.cancelled?{}:v.paint.mask)}))throw Error('Batch final mask mismatch');
      cache=null;const {paint,...result}=v;try{result.selection_context=selectionContext();}catch(_){}return result;
    } catch(error){error.resultUnknown=true;throw error;}
  }
  async function apply(request,io) {
    validate(request.paint);const preview=request.command==='shape.preview';
    if(preview && (typeof ps.core.redrawDocument!=='function' || !io))throw Error('Batch live preview unavailable');
    let progressFrame=0;const progress=async(stage,done=0,total=0)=>{if(io?.progress)await io.progress(stage,done,total,progressFrame);};
    let uncertain=false;
    try {return await ps.core.executeAsModal(async context=>{
      await progress('read');const prepared=await prepare(request),baseline={identity:prepared.identity,members:prepared.members};
      let applied=baseline.members.map(v=>clone(v.mask)),params=request.paint,seq=0,updates=0,changed=false,cancelled=false;
      let historyOpen=false,committed=false,history;const touched=new Set();
      const verify=async masks=>{await progress('verify');check(await snapshot(baseline.identity),baseline,masks);await progress('verify',masks.length,masks.length);};
      async function restoreSelection() {
        const actual=await capture();if(actual.document_id!==baseline.identity.document_id)throw Error('Batch document changed during rollback');
        if(targetSame(actual,baseline.identity))return;
        const ids=baseline.identity.layer_ids.filter(id=>id!==baseline.identity.active_layer_id).concat(baseline.identity.active_layer_id);
        const results=await ps.action.batchPlay(ids.map((id,i)=>({_obj:'select',_target:[{_ref:'layer',_id:id},{_ref:'document',_id:baseline.identity.document_id}],
          makeVisible:false,...(i?{selectionModifier:{_enum:'selectionModifierType',_value:'addToSelection'}}:{}),_options:{dialogOptions:'dontDisplay'}})),{});
        if(results.some(v=>v?._obj==='error'))throw Error('Batch selection restoration failed');
      }
      async function frame(p) {
        validate(p);if(p.revision!==prepared.before.revision)throw Error('Batch revision changed');
        if(context.isCancelled)throw Error('Cancelled');
        await verify(applied);const wanted=baseline.members.map(v=>({...v.mask,...p.mask})),commands=[];
        for(let i=0;i<wanted.length;i++)for(const k of ['feather','density'])if(Math.abs(wanted[i][k]-applied[i][k])>(k==='feather'?.00001:100/255+.001)){
          commands.push({_obj:'set',_target:[{_ref:'layer',_id:baseline.members[i].id},{_ref:'document',_id:baseline.identity.document_id}],
            to:{_obj:'layer',[k==='feather'?'vectorMaskFeather':'vectorMaskDensity']:{_unit:k==='feather'?'pixelsUnit':'percentUnit',_value:wanted[i][k]}},_options:{dialogOptions:'silent'}});touched.add(baseline.members[i].id);
        }
        if(commands.length){await progress('write');changed=true;const results=await ps.action.batchPlay(commands,{});if(results.length!==commands.length || results.some(v=>v?._obj==='error'))throw Error('Batch mask setter failed');await progress('write',wanted.length,wanted.length);}
        await verify(wanted);applied=wanted;params=p;updates++;
        if(preview && commands.length){await progress('redraw');await ps.core.redrawDocument({documentID:baseline.identity.document_id});await verify(applied);}await progress('ready',wanted.length,wanted.length);
      }
      try {
        history=await context.hostControl.suspendHistory({documentID:baseline.identity.document_id,name:'批量羽化／密度'});historyOpen=true;
        if(!preview)await frame(params);
        else {
          let lease=Date.now()+4000;
          while(true){
            if(context.isCancelled)throw Error('Cancelled');
            const packet=await io.read(),now=Date.now();
            if(packet){
              if(packet.id!==request.id||packet.session!==request.session||packet.token!==request.token||!Number.isSafeInteger(packet.seq)||packet.seq<seq||!Number.isFinite(packet.lease_until_ms)||packet.lease_until_ms>now+5000||!['preview','commit','cancel'].includes(packet.phase))throw Error('Invalid batch mailbox');
              lease=packet.lease_until_ms;if(lease<now || packet.phase==='cancel'){cancelled=true;break;}
              validate(packet.paint);if(packet.paint.revision!==prepared.before.revision || packet.seq===seq && !same(packet.paint,params))throw Error('Batch sequence payload changed');
              if(packet.seq>seq){progressFrame=packet.seq;await frame(packet.paint);seq=packet.seq;if(io.applied)await io.applied({seq,updates,count:baseline.members.length,mask_batch:true,redraw_completed:true});}
              if(packet.phase==='commit')break;
            } else if(now>lease){cancelled=true;break;}
            await new Promise(resolve=>setTimeout(resolve,40));
          }
        }
        await verify(applied);await progress(cancelled?'restore':'commit');historyOpen=false;uncertain=true;await context.hostControl.resumeHistory(history,!cancelled);committed=!cancelled;uncertain=false;
        if(cancelled){await restoreSelection();await verify(baseline.members.map(v=>v.mask));if(changed){await progress('restore-redraw');await ps.core.redrawDocument({documentID:baseline.identity.document_id});}await verify(baseline.members.map(v=>v.mask));}
        cache=null;return {verified:true,mask_batch:true,count:cancelled?0:touched.size,placement_moves:0,layer_ids:baseline.identity.layer_ids,
          ...(cancelled?{cancelled:true,rollback_verified:true}:{}),preview:{updates,last_seq:seq},selection_context:selectionContext()};
      } catch(error){
        uncertain=uncertain||committed||!!error.resultUnknown;
        if(historyOpen){historyOpen=false;try{await progress('restore');await context.hostControl.resumeHistory(history,false);await restoreSelection();await verify(baseline.members.map(v=>v.mask));if(preview&&changed){await progress('restore-redraw');await ps.core.redrawDocument({documentID:baseline.identity.document_id});}await verify(baseline.members.map(v=>v.mask));}catch(_){uncertain=true;}}
        cache=null;throw error;
      }
    },{commandName:'批量羽化／密度',timeOut:0,...(preview?{interactive:true}:{})});}
    catch(error){if(uncertain){const e=Error(String(error));e.resultUnknown=true;throw e;}throw error;}
  }
  return {observe,apply,prepare,prepareLegacy,finishLegacy};
}

function selectionKind(k,kind,background) {
  if(background)return 'background';
  for(const [key,name] of [['NORMAL','pixel'],['GROUP','group'],['TEXT','text'],['SMARTOBJECT','smart'],
      ['SOLIDFILL','shape-fill'],['GRADIENTFILL','shape-fill'],['PATTERNFILL','shape-fill']])
    if(k[key]!==undefined && kind===k[key])return name;
  const adjustment=['BLACKANDWHITE','BRIGHTNESSCONTRAST','CHANNELMIXER','COLORBALANCE','COLORLOOKUP',
    'CURVES','EXPOSURE','GRADIENTMAP','HUESATURATION','INVERSION','LEVELS','PHOTOFILTER',
    'POSTERIZE','SELECTIVECOLOR','THRESHOLD','VIBRANCE','GRAIN','CLARITY'];
  if(adjustment.some(key=>k[key]!==undefined && kind===k[key]))return 'adjustment';
  return Object.values(k).includes(kind)?'other':'unknown';
}
function selectionQuickMask(constants,mode,depth,ids,kinds,background,locked,parentLocked,sameParent) {
  const modes=constants.DocumentMode || {},depths=constants.BitsPerChannelType || {};
  const layered=['RGB','CMYK','LAB','GRAYSCALE'].some(key=>modes[key]!==undefined && mode===modes[key]);
  let mask=layered && ids.length && !parentLocked && !kinds.includes('unknown')?3:0;
  if(mask && !background && !locked && sameParent)mask|=4;
  if(mask && [depths.EIGHT,depths.SIXTEEN].some(v=>v!==undefined && depth===v)) {
    mask|=8;if(mode===modes.RGB)mask|=112;
  }
  return mask;
}
function nativeKinds(constants) {
  const k=constants.LayerKind;
  return {1:k.NORMAL,2:k.CURVES,3:k.TEXT,4:k.SOLIDFILL,5:k.SMARTOBJECT,6:k.VIDEO,8:k.LAYER3D,9:k.GRADIENTFILL,10:k.PATTERNFILL,11:k.SOLIDFILL};
}
function nativeModeDepth(constants,before) {
  const m=constants.DocumentMode,b=constants.BitsPerChannelType;
  const modes={RGBColor:m.RGB,CMYKColor:m.CMYK,labColor:m.LAB,grayscale:m.GRAYSCALE,
    bitmap:m.BITMAP,indexedColor:m.INDEXEDCOLOR,multichannel:m.MULTICHANNEL,duotone:m.DUOTONE};
  const mode=modes[before[4].mode?._value],depth=({8:b.EIGHT,16:b.SIXTEEN,32:b.THIRTYTWO})[before[5].depth];
  if(mode===undefined||depth===undefined)throw Error('Unsupported native document mode or depth');
  return {mode,depth};
}
// Photoshop 24.2 Windows has severe per-getter DOM overhead outside modal work.
// No host DOM objects or cross-request capability cache enter this read path.
async function nativeDocumentCount(ps,checkpoint=null) {
  if(checkpoint)await checkpoint();
  const rows=await ps.action.batchPlay([{_obj:'get',_target:[{_ref:'property',_property:'numberOfDocuments'},
    {_ref:'application',_enum:'ordinal',_value:'targetEnum'}],_options:{dialogOptions:'silent'}}],{});
  if(checkpoint)await checkpoint();
  const count=rows?.[0]?.numberOfDocuments;
  if(!Number.isInteger(count)||count<0)throw Error('Native document state unavailable');
  return count;
}
async function nativeSelectionContext(ps,session,reader,checkpoint=null,targeted=true,plan={total:null,single:true}) {
  if(await nativeDocumentCount(ps,checkpoint)===0)return {session,document_id:null,layer_ids:[],kind:'none',mask:0};
  const tick=async()=>{if(checkpoint)await checkpoint();};
  const ref=[{_ref:'document',_enum:'ordinal',_value:'targetEnum'}];
  const property=name=>({_obj:'get',_target:[{_ref:'property',_property:name},...ref],_options:{dialogOptions:'silent'}});
  async function batch(commands,required=commands.length){await tick();const result=await ps.action.batchPlay(commands,{});await tick();
    if(!Array.isArray(result)||result.length!==commands.length||result.slice(0,required).some(v=>!v||v._obj==='error'))throw Error('Native selection unavailable');return result;}
  function identity(rows){
    const id=rows[0].documentID,refs=rows[1].targetLayersIDs;
    if(!Number.isInteger(id)||id<=0||!Array.isArray(refs)||!refs.length||refs.some(x=>x?._ref!=='layer'||!Number.isInteger(x._id)||x._id<=0))throw Error('Invalid native selection identity');
    const ids=refs.map(x=>x._id).sort((a,b)=>a-b);if(new Set(ids).size!==ids.length)throw Error('Duplicate native selection');return {id,ids};
  }
  const fields=['layerID','parentLayerID','itemIndex','layerSection','layerKind','background','layerLocking'];
  const scalar=target=>({_obj:'multiGet',_target:{_ref:target},extendedReference:[fields],
    options:{failOnMissingProperty:false,failOnMissingElement:false},_options:{dialogOptions:'silent'}});
  const headers=()=>['documentID','targetLayersIDs','numberOfLayers','hasBackgroundLayer','mode','depth'].map(property);
  const prefetch=targeted && plan.single && (plan.total===null || plan.total>8);
  const initial=await batch([...headers(),...(prefetch?[scalar([{_ref:'layer',_enum:'ordinal',_value:'targetEnum'},...ref])]:[])],6);
  const before=initial.slice(0,6);
  const chosen=identity(before),count=before[2].numberOfLayers,bg=before[3].hasBackgroundLayer;
  if(!Number.isSafeInteger(count)||count<0||count>1000000||typeof bg!=='boolean'||count+(bg?1:0)<1)throw Error('Native selection range unavailable');
  const total=count+(bg?1:0),documentRef=[{_ref:'document',_id:chosen.id}];
  const kindMap=nativeKinds(ps.constants),{mode,depth}=nativeModeDepth(ps.constants,before);
  if(targeted){plan.total=total;plan.single=chosen.ids.length===1;}
  let fallback='';
  // Tiny trees already return fewer records with fewer descriptors. Preserve
  // that bounded fast path rather than making small documents slower.
  if(targeted && total>8 && chosen.ids.length===1){
    const row=prefetch?initial[6]:(await batch([scalar([{_ref:'layer',_id:chosen.ids[0]},...documentRef])],0))[0],section=row?.layerSection?._value;
    if(Number.isInteger(row?.layerID) && row.layerID>0 && row.layerID!==chosen.ids[0])throw Error('Layer context changed during native read');
    const locks=row?.layerLocking,position=row?.itemIndex;
    const root=row && row.layerID===chosen.ids[0] && section==='layerSectionContent' &&
      Number.isInteger(row.parentLayerID) && row.parentLayerID<=0 && row.background===false &&
      Number.isInteger(position) && position>=(bg?2:1) && position<=total &&
      locks && typeof locks.protectAll==='boolean' && typeof locks.protectPosition==='boolean' && kindMap[row.layerKind]!==undefined;
    if(root){
      // Only immediate AM neighbours are needed for an ordinary root layer.
      // A section end above denotes a group sibling; a section start below
      // denotes a group sibling. No partial tree is presented as a full tree.
      const indices=[position<total?position+1:null,position>1?position-1:null];
      const commands=indices.filter(x=>x!==null).map(index=>scalar([{_ref:'layer',_index:index-(bg?1:0)},...documentRef]));
      const neighbours=commands.length?await batch(commands,0):[];
      let offset=0;const adjacent=indices.map(index=>index===null?null:neighbours[offset++]);
      function relation(value,index,above){
        if(index===null)return {nonGroup:false};
        if(!value || value._obj==='error' || value.itemIndex!==index)return null;
        const part=value.layerSection?._value;
        if(above && part==='layerSectionEnd')return {nonGroup:false};
        if(!Number.isInteger(value.layerID)||value.layerID<=0||value.layerID===row.layerID||
           !Number.isInteger(value.parentLayerID)||value.parentLayerID>0)return null;
        if(part==='layerSectionStart' && !above)return {nonGroup:false};
        if(part!=='layerSectionContent' || typeof value.background!=='boolean' ||
           value.background!==(bg && index===1))return null;
        return {nonGroup:true};
      }
      const above=relation(adjacent[0],indices[0],true),below=relation(adjacent[1],indices[1],false);
      if(above && below){
        const selected=scalar([{_ref:'layer',_id:chosen.ids[0]},...documentRef]);
        // Close the bracket with active document/selection identity last.
        const verified=await batch([selected,...commands,...headers().slice(2),...headers().slice(0,2)]);
        const tail=verified.slice(1+commands.length),after=[...tail.slice(4),...tail.slice(0,4)],last=identity(after);
        const equal=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
        if(last.id!==chosen.id || last.ids.join(',')!==chosen.ids.join(',') ||
           !equal(after.slice(2,6),before.slice(2,6)) || !equal(verified[0],row) ||
           !equal(verified.slice(1,1+commands.length),neighbours))throw Error('Layer context changed during native root read');
        const kind=selectionKind(ps.constants.LayerKind,kindMap[row.layerKind],false),locked=locks.protectAll||locks.protectPosition;
        if(kind==='unknown')throw Error('Unsupported native layer kind');
        let mask=2;if(above.nonGroup||below.nonGroup)mask|=1;
        if(!locked){if(position<total)mask|=4;if(position>(bg?2:1))mask|=8;}
        return {session,document_id:chosen.id,layer_ids:chosen.ids,selection_count:1,kind,types:[kind],
          background:false,locked,same_parent:true,mask,
          quick_mask:selectionQuickMask(ps.constants,mode,depth,chosen.ids,[kind],false,locked,false,true),
          read_path:'native-root-scalars',read_scope:'root-single'};
      }
      fallback='uncertain-adjacency';
    }else fallback='structural-or-property';
    // A read-only fallback is permitted only for the same current selection.
    // Cancellation, a superseding menu and identity changes never downgrade.
    const fence=identity(await batch(['documentID','targetLayersIDs'].map(property)));
    if(fence.id!==chosen.id || fence.ids.join(',')!==chosen.ids.join(','))throw Error('Layer context changed before native fallback');
  }
  if(count>4096)throw Error('Native selection range unavailable');
  const [result]=await batch([{_obj:'multiGet',_target:{_ref:documentRef},extendedReference:[
    ['layerID','parentLayerID','itemIndex','layerSection','layerKind','background','layerLocking'],
    {_obj:'layer',index:bg?0:1,count:total}],options:{failOnMissingProperty:false,failOnMissingElement:false},_options:{dialogOptions:'silent'}}]);
  if(!Array.isArray(result.list)||result.list.length!==total)throw Error('Incomplete native selection tree');
  const rows=result.list.slice().sort((a,b)=>b.itemIndex-a.itemIndex),layers=[],map=new Map(),stack=[];
  const k=ps.constants.LayerKind;
  for(let i=0;i<rows.length;i++){
    if(i%16===0)await tick();const row=rows[i],section=row?.layerSection?._value;
    if(!row||row.itemIndex!==total-i)throw Error('Invalid native tree order');
    if(section==='layerSectionEnd'){if(!stack.length)throw Error('Unbalanced native groups');stack.pop();continue;}
    const parent=stack.length?stack[stack.length-1]:null,locks=row.layerLocking;
    if(!['layerSectionContent','layerSectionStart'].includes(section)||!Number.isInteger(row.layerID)||row.layerID<=0||map.has(row.layerID)||
       !Number.isInteger(row.parentLayerID)||(row.parentLayerID>0?row.parentLayerID:null)!==(parent?.id??null)||
       !locks||typeof locks.protectAll!=='boolean'||typeof locks.protectPosition!=='boolean')throw Error('Invalid native layer membership or locks');
    // Background is an explicit, validated role; never infer it from an
    // otherwise unknown numeric kind (nor reject it for kind=12).
    const kind=section==='layerSectionStart'?k.GROUP:row.background===true?k.NORMAL:kindMap[row.layerKind];
    if(kind===undefined)throw Error('Unsupported native layer kind');
    const layer={id:row.layerID,kind,parent,layers:[],isBackgroundLayer:row.background===true,allLocked:locks.protectAll,positionLocked:locks.protectPosition};
    if(layer.isBackgroundLayer && (!bg||parent||i!==rows.length-1))throw Error('Invalid native background');
    (parent?parent.layers:layers).push(layer);map.set(layer.id,layer);if(section==='layerSectionStart')stack.push(layer);
  }
  if(stack.length||!layers.length||(bg!==layers[layers.length-1].isBackgroundLayer)||chosen.ids.some(id=>!map.has(id)))throw Error('Incomplete native selection membership');
  const doc={id:chosen.id,layers,activeLayers:chosen.ids.map(id=>map.get(id)),mode,bitsPerChannel:depth};
  const virtual={app:{documents:[doc],activeDocument:doc},constants:ps.constants};
  const iterator=reader(false,null,virtual);let step;do{step=iterator.next();await tick();}while(!step.done);
  const after=await batch(['documentID','targetLayersIDs','mode','depth'].map(property)),last=identity(after);
  if(last.id!==chosen.id||last.ids.join(',')!==chosen.ids.join(',')||JSON.stringify(after[2].mode)!==JSON.stringify(before[4].mode)||after[3].depth!==before[5].depth)throw Error('Layer context changed during native read');
  return {...step.value,read_path:'native-24.2',...(targeted && total<=8?{read_scope:'bounded-tree'}:{}),...(fallback?{read_fallback:fallback}:{})};
}

async function nativeCapture(ps,session) {
  if(await nativeDocumentCount(ps)===0)throw Error('No active document; no operation submitted');
  const property=(name,layer=false)=>({_obj:'get',_target:[{_ref:'property',_property:name},{_ref:layer?'layer':'document',_enum:'ordinal',_value:'targetEnum'}],_options:{dialogOptions:'silent'}});
  const result=await ps.action.batchPlay([property('documentID'),property('targetLayersIDs'),property('layerID',true)],{});
  if(!Array.isArray(result)||result.length!==3||result.some(v=>!v||v._obj==='error'))throw Error('Native target unavailable');
  const id=result[0].documentID,refs=result[1].targetLayersIDs,active=result[2].layerID;
  if(!Number.isInteger(id)||id<=0||!Array.isArray(refs)||!refs.length||refs.some(x=>x?._ref!=='layer'||!Number.isInteger(x._id)||x._id<=0))throw Error('Invalid native target');
  const ids=refs.map(x=>x._id).sort((a,b)=>a-b);
  if(new Set(ids).size!==ids.length||!ids.includes(active))throw Error('Invalid native active layer');
  const after=await ps.action.batchPlay([property('documentID'),property('targetLayersIDs')],{});
  if(after?.[0]?.documentID!==id||!Array.isArray(after[1]?.targetLayersIDs)||after[1].targetLayersIDs.map(x=>x._id).sort((a,b)=>a-b).join(',')!==ids.join(','))throw Error('Target changed during native capture');
  return {session,document_id:id,active_layer_id:active,layer_ids:ids};
}
