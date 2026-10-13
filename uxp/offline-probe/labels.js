// Experimental executor: only fixed-target labels, no arbitrary scripts.
module.exports = function createLabels(ps, session) {
  const colors = new Set(['none','red','orange','yellowColor','grain','blue','violet','gray']);
  const quickCommands=['layer.new','layer.solid','layer.group','adjustment.curves',
    'adjustment.hueSaturation','adjustment.colorBalance','adjustment.blackWhite'];
  // DOM-only, read-only metadata. No batchPlay, executeAsModal, pixels or
  // thumbnails on the menu path. The executor uses this same eligibility rule.
  function selectionContext(quickOnly=false) {
    if (!ps.app.documents.length) return {session,document_id:null,layer_ids:[],kind:'none',mask:0};
    const doc=ps.app.activeDocument,selected=Array.from(doc.activeLayers),k=ps.constants.LayerKind;
    // Host-backed DOM getters are costly. Reuse reads only within this one
    // snapshot, never across requests or the final selection identity check.
    const properties=new Map(),siblingLists=new Map();
    function read(layer,key) {
      let values=properties.get(layer);
      if(!values) {values=Object.create(null);properties.set(layer,values);}
      if(!Object.prototype.hasOwnProperty.call(values,key))values[key]=layer[key];
      return values[key];
    }
    function siblings(parent) {
      if(!siblingLists.has(parent))siblingLists.set(parent,Array.from(parent?read(parent,'layers'):doc.layers));
      return siblingLists.get(parent);
    }
    const kinds=selected.map(layer=>{
      if(read(layer,'isBackgroundLayer'))return 'background';
      const kind=read(layer,'kind');
      for(const [key,name] of [['NORMAL','pixel'],['GROUP','group'],['TEXT','text'],['SMARTOBJECT','smart'],
          ['SOLIDFILL','shape-fill'],['GRADIENTFILL','shape-fill'],['PATTERNFILL','shape-fill']])
        if(k[key]!==undefined && kind===k[key])return name;
      const adjustment=['BLACKANDWHITE','BRIGHTNESSCONTRAST','CHANNELMIXER','COLORBALANCE','COLORLOOKUP',
        'CURVES','EXPOSURE','GRADIENTMAP','HUESATURATION','INVERSION','LEVELS','PHOTOFILTER',
        'POSTERIZE','SELECTIVECOLOR','THRESHOLD','VIBRANCE','GRAIN','CLARITY'];
      if(adjustment.some(key=>k[key]!==undefined && kind===k[key]))return 'adjustment';
      return Object.values(k).includes(kind)?'other':'unknown';
    });
    const ids=selected.map(l=>read(l,'id')).sort((a,b)=>a-b),background=kinds.includes('background');
    const parents=selected.map(l=>read(l,'parent'));
    const parentIds=parents.map(parent=>parent?read(parent,'id'):null);
    const sameParent=parentIds.every(id=>id===parentIds[0]);
    let locked=false,parentLocked=false;
    for(const layer of selected) {
      for(let node=layer,depth=0;node && depth<=64;node=read(node,'parent'),depth++) {
        const allLocked=read(node,'allLocked');
        if(depth<64 && (allLocked || read(node,'positionLocked')))locked=true;
        if(depth>0 && allLocked)parentLocked=true;
      }
    }
    let mask=0;
    if(!quickOnly && selected.length && !kinds.includes('unknown')) {
      if(!background)mask|=2;
      if(selected.length===1) {
        const active=selected[0],order=siblings(parents[0]);
        if(read(active,'kind')===k.GROUP) {if(read(active,'layers').length)mask|=1;}
        else {
          const index=order.findIndex(l=>read(l,'id')===ids[0]);
          if(index>=0 && ((index>0 && read(order[index-1],'kind')!==k.GROUP) ||
              (index+1<order.length && read(order[index+1],'kind')!==k.GROUP)))mask|=1;
        }
      }
      if(!background && !locked && sameParent) {
        const order=siblings(parents[0]),chosen=order.filter(l=>ids.includes(read(l,'id')));
        if(chosen.length===ids.length) {
          // To establish an edge, stop at the first unselected non-background
          // layer. There is no need to query every sibling's expensive
          // isBackgroundLayer getter; unusual background positions still work.
          function atEdge(bottom) {
            let count=0;
            for(let i=bottom?order.length-1:0;i>=0 && i<order.length;i+=bottom?-1:1) {
              const layer=order[i];
              if(ids.includes(read(layer,'id'))) {if(++count===ids.length)return true;}
              else if(!read(layer,'isBackgroundLayer'))return false;
            }
            return false;
          }
          if(!atEdge(false))mask|=4;
          if(!atEdge(true))mask|=8;
        }
      }
    }
    if(ps.app.activeDocument.id!==doc.id || Array.from(doc.activeLayers,l=>l.id).sort((a,b)=>a-b).join(',')!==ids.join(','))
      throw Error('Layer context changed during read');
    const modes=ps.constants.DocumentMode || {},depths=ps.constants.BitsPerChannelType || {};
    const mode=doc.mode,depth=doc.bitsPerChannel;
    const layered=['RGB','CMYK','LAB','GRAYSCALE'].some(key=>modes[key]!==undefined && mode===modes[key]);
    let quickMask=layered && ids.length && !parentLocked && !kinds.includes('unknown')?3:0;
    if(quickMask && !background && !locked && sameParent)quickMask|=4;
    const adjustmentDepth=[depths.EIGHT,depths.SIXTEEN].some(v=>v!==undefined && depth===v);
    if(quickMask && adjustmentDepth) {
      quickMask|=8;
      if(mode===modes.RGB)quickMask|=112;
    }
    return {session,document_id:doc.id,layer_ids:ids,selection_count:ids.length,
      kind:kinds.every(kind=>kind===kinds[0])?(kinds[0] || 'none'):'mixed',
      types:[...new Set(kinds)],background,locked,same_parent:sameParent,mask,quick_mask:quickMask};
  }
  async function capture() {
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
  function selectionMatches(value) {
    if(!value || value.session!==session || !Array.isArray(value.layer_ids) || !ps.app.documents.length)return false;
    const doc=ps.app.activeDocument;
    const ids=Array.from(doc.activeLayers,l=>l.id).sort((a,b)=>a-b);
    return ps.app.activeDocument.id===doc.id && doc.id===value.document_id && ids.join(',')===value.layer_ids.join(',');
  }
  async function setLabel(request) {
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
          const knownKinds=new Map(),knownLayers=new Map();
          function allIds(layers) {return Array.from(layers).flatMap(l=>{
            const id=l.id,kind=knownKinds.has(id)?knownKinds.get(id):l.kind;
            knownKinds.set(id,kind);knownLayers.set(id,l);
            return [id,...(kind===k.GROUP?allIds(l.layers):[])];
          });}
          const before=allIds(doc.layers);
          const anchor=knownLayers.get(actual.active_layer_id);
          if(!anchor)throw Error('新建图层目标已改变');
          // A selected group receives its new layer inside, like native PS.
          const insideGroup=command!=='layer.group' && knownKinds.get(anchor.id)===k.GROUP;
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
            placement_moves:placementMoves,placeholder_used:placeholderUsed};
          timings.verify_ms=Date.now()-stageStarted;stageStarted=Date.now();
          // Read the new state while the same PS modal still owns the target.
          // Metadata failure cannot undo a successfully verified creation:
          // the caller falls back to its normal full post-operation snapshot.
          try {result.selection_context=selectionContext();}catch(_) {}
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
  return {capture,setLabel,documentTarget,createDocument,selectionContext,selectionMatches};
};

