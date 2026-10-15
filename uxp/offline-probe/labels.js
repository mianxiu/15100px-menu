// Experimental executor: only fixed-target labels, no arbitrary scripts.
module.exports = function createLabels(ps, session) {
  const caps=createCapsActions(ps,session,capture,selectionContext);
  const colors = new Set(['none','red','orange','yellowColor','grain','blue','violet','gray']);
  const shapePaint=createShapePaint(ps,session,capture,selectionContext);
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
    if(caps.commands.includes(request.command))return caps.execute(request);
    if(request.command==='shape.paint')return shapePaint.apply(request);
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
  let interfaceState={ui_theme:'dark',ui_font_size:'small'};
  async function interfacePreferences() {
    // Only UXP DOM/get reads. Never execute JSX or enter a modal to observe UI.
    try {
      const value=ps.app.preferences.interface.textFontSize, sizes=ps.constants.FontSize || {};
      for(const key of ['SMALL','MEDIUM','LARGE'])if(sizes[key]!==undefined && value===sizes[key])
        interfaceState.ui_font_size=key.toLowerCase();
    } catch(_) {}
    try {
      const [value]=await ps.action.batchPlay([{_obj:'get',_target:[
        {_ref:'property',_property:'interfacePrefs'},{_ref:'application',_enum:'ordinal',_value:'targetEnum'}],
        _options:{dialogOptions:'dontDisplay'}}],{});
      const raw=value?.interfacePrefs?.kuiBrightnessLevel;
      const name=typeof raw==='string'?raw:raw?._value;
      const theme={kPanelBrightnessOriginal:'light',kPanelBrightnessLightGray:'light-gray',
        kPanelBrightnessMediumGray:'dark-gray',kPanelBrightnessDarkGray:'dark'}[name];
      if(theme)interfaceState.ui_theme=theme;
    } catch(_) {}
    return {...interfaceState};
  }
  return {capture,setLabel,documentTarget,createDocument,selectionContext,selectionMatches,interfacePreferences,observeShape:shapePaint.observe};
};


// Cached vector-paint metadata and one-transaction writes. No JSX or previews.
function createShapePaint(ps,session,capture,selectionContext) {
  let cache=null,serial=0,catalog=[],catalogAt=0,catalogInfo={};
  const clone=value=>JSON.parse(JSON.stringify(value));
  const rgb=color=>color?._obj==='RGBColor'?[color.red,color.grain??color.green,color.blue].map(v=>Math.round(Number(v))):null;
  function paint(raw) {
    if(raw?._obj==='solidColorLayer') {const c=rgb(raw.color);return c && c.every(v=>Number.isFinite(v))?{kind:'solid',rgb:c}:null;}
    if(raw?._obj==='gradientLayer') {
      const colors=raw.gradient?.colors;
      if(!Array.isArray(colors) || colors.length<2 || colors.length>32)return null;
      const stops=colors.map(v=>({rgb:rgb(v.color),location:Math.round(v.location)}));
      return stops.every(v=>v.rgb && v.rgb.every(Number.isFinite))?{kind:'gradient',stops}:null;
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
  async function readCore(doc,id) {
    const keys=['layerKind','hasVectorMask','adjustment','AGMStrokeStyleInfo'];
    const result=await ps.action.batchPlay(keys.map(key=>({_obj:'get',_target:[{_ref:'property',_property:key},
      {_ref:'layer',_id:id},{_ref:'document',_id:doc.id}],_options:{dialogOptions:'dontDisplay'}})),{});
    const vector=result[1]?.hasVectorMask===true;
    const fill=result[2]?.adjustment?.[0],stroke=result[3]?.AGMStrokeStyleInfo;
    if(!paint(fill))return null;
    const defaultStroke={_obj:'strokeStyle',strokeStyleVersion:2,strokeEnabled:false,fillEnabled:true,
      strokeStyleLineWidth:{_unit:'pixelsUnit',_value:1},strokeStyleContent:{_obj:'solidColorLayer',color:{_obj:'RGBColor',red:0,grain:0,blue:0}}};
    const actualStroke=vector?(stroke || defaultStroke):defaultStroke;
    if(actualStroke.strokeStyleLineWidth && !['pixelsUnit','pointsUnit'].includes(actualStroke.strokeStyleLineWidth._unit))return null;
    if(!paint(actualStroke.strokeStyleContent))return null;
    return {fill,stroke:actualStroke,vector};
  }
  async function observe(context,force=false) {
    if(context.kind!=='shape-fill' || context.layer_ids?.length!==1 || context.locked || !ps.app.documents.length)
      return {available:false};
    const doc=ps.app.activeDocument,id=context.layer_ids[0],key=doc.id+':'+id;
    if(!force && cache?.key===key && Date.now()-cache.at<500)return cache.data;
    if(doc.mode!==ps.constants.DocumentMode.RGB || ![ps.constants.BitsPerChannelType.EIGHT,ps.constants.BitsPerChannelType.SIXTEEN].includes(doc.bitsPerChannel))
      return {available:false};
    const raw=await readCore(doc,id);
    if(!raw) {cache={key,at:Date.now(),data:{available:false}};return cache.data;}
    if(ps.app.activeDocument.id!==doc.id || doc.activeLayers.length!==1 || doc.activeLayers[0].id!==id)
      return {available:false};
    const signature=JSON.stringify(raw),revision=cache?.key===key && cache.signature===signature?cache.data.revision:session+':'+(++serial);
    const fill={...paint(raw.fill),enabled:raw.stroke.fillEnabled!==false};
    const stroke={...paint(raw.stroke.strokeStyleContent),enabled:!!raw.stroke.strokeEnabled,
      width:Number(raw.stroke.strokeStyleLineWidth?._value ?? 1)*(raw.stroke.strokeStyleLineWidth?._unit==='pointsUnit'?doc.resolution/72:1)};
    const data={available:true,vector:raw.vector,revision,fill,stroke,patterns:await patterns(),pattern_catalog:catalogInfo};
    cache={key,at:Date.now(),signature,raw,data};return data;
  }
  function validatePaint(value) {
    if(!value || !['solid','gradient','pattern'].includes(value.kind) || typeof value.enabled!=='boolean')throw Error('Invalid paint type');
    const color=c=>Array.isArray(c) && c.length===3 && c.every(v=>typeof v==='number' && Number.isFinite(v) && v>=0 && v<=255);
    if(value.kind==='solid' && !color(value.rgb))throw Error('Invalid RGB color');
    if(value.kind==='gradient' && (!Array.isArray(value.stops) || value.stops.length<2 || value.stops.length>32 ||
      value.stops.some((s,i)=>!color(s.rgb) || !Number.isInteger(s.location) || s.location<0 || s.location>4096 || i && s.location<value.stops[i-1].location)))throw Error('Invalid gradient stops');
    if(value.kind==='pattern' && (typeof value.name!=='string' || !value.name || value.name.length>128))throw Error('Invalid pattern name');
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
    return actual.stops.length===wanted.stops.length && actual.stops.every((s,i)=>s.location===wanted.stops[i].location && close(s.rgb,wanted.stops[i].rgb));
  }
  async function apply(request) {
    const params=request.paint;
    if(!params || typeof params.revision!=='string' || params.revision.length>128)throw Error('Missing shape revision');
    validatePaint(params.fill);validatePaint(params.stroke);
    if(typeof params.stroke.width!=='number' || !Number.isFinite(params.stroke.width) || params.stroke.width<0 || params.stroke.width>1000)throw Error('Invalid stroke width');
    return ps.core.executeAsModal(async context=>{
      if(context.isCancelled || Date.now()>request.expires_at_ms)throw Error('Cancelled or expired');
      const actual=await capture(),expected=request.target;
      if(expected?.session!==session || actual.document_id!==expected.document_id || actual.active_layer_id!==expected.active_layer_id || actual.layer_ids.join(',')!==expected.layer_ids?.join(','))throw Error('Document or layer target changed');
      const eligibility=selectionContext(),before=await observe(eligibility,true);
      if(!before.available || before.revision!==params.revision)throw Error('填充／描边已改变，请重新打开菜单；本次未修改');
      if(!before.vector && params.fill.kind!==before.fill.kind)throw Error('普通填充层保持PS原生类型；本次未修改');
      if(!before.vector && (!params.fill.enabled || params.stroke.kind!==before.stroke.kind || params.stroke.enabled!==before.stroke.enabled
          || params.stroke.width!==before.stroke.width || JSON.stringify(params.stroke.rgb)!==JSON.stringify(before.stroke.rgb)))
        throw Error('普通填充层不支持形状描边或禁用填充；本次未修改');
      const original=cache.raw,doc=ps.app.activeDocument,anchor=doc.activeLayers[0];
      const parent=anchor.parent,parentId=parent?.id ?? null,order=Array.from(parent?parent.layers:doc.layers,l=>l.id);
      const to=before.vector?{_obj:'shapeStyle',fillContents:build(params.fill,original.fill),strokeStyle:{...clone(original.stroke),
        strokeStyleVersion:2,fillEnabled:params.fill.enabled,strokeEnabled:params.stroke.enabled,
        strokeStyleLineWidth:{_unit:'pixelsUnit',_value:params.stroke.width},
        strokeStyleContent:build(params.stroke,original.stroke.strokeStyleContent)}}:build(params.fill,original.fill);
      if(context.isCancelled || Date.now()>request.expires_at_ms)throw Error('Cancelled or expired');
      const history=await context.hostControl.suspendHistory({documentID:doc.id,name:'Menu shape paint'});
      try {
        const [response]=await ps.action.batchPlay([{_obj:'set',_target:[{_ref:'contentLayer',_enum:'ordinal',_value:'targetEnum'}],
          to,_options:{dialogOptions:'dontDisplay'}}],{});
        if(response?._obj==='error')throw Error(response.message || 'Photoshop 拒绝修改形状颜色');
        const after=await observe(selectionContext(),true);
        if(!after.available || after.vector!==before.vector || !samePaint(after.fill,params.fill) || !samePaint(after.stroke,params.stroke) || Math.abs(after.stroke.width-params.stroke.width)>.01 ||
          doc.activeLayers.length!==1 || doc.activeLayers[0].id!==anchor.id || (anchor.parent?.id ?? null)!==parentId ||
          Array.from(parent?parent.layers:doc.layers,l=>l.id).join(',')!==order.join(','))throw Error('形状颜色／图层身份读回不符，已回滚');
        await context.hostControl.resumeHistory(history,true);
        return {count:1,verified:true,placement_moves:0,fill_kind:after.fill.kind,stroke_kind:after.stroke.kind,selection_context:selectionContext()};
      } catch(error) {
        try {await context.hostControl.resumeHistory(history,false);cache=null;}
        catch(_) {error.resultUnknown=true;}
        throw error;
      }
    },{commandName:'Menu shape paint',timeOut:0});
  }
  return {observe,apply};
}

// Fixed reference-Caps actions. No menu letters, synthetic keys or IME changes.
function createCapsActions(ps,session,capture,selectionContext) {
  const commands=['selectAbove','selectBelow','moveUp','moveDown','copyStyle','pasteStyle','editStyle'];
  async function execute(request) {
    const command=request.command,expected=request.target;
    if(!commands.includes(command) || expected?.session!==session)throw Error('Unsupported Caps command/session');
    return ps.core.executeAsModal(async context=>{
      if(context.isCancelled || Date.now()>request.expires_at_ms)throw Error('Cancelled or expired');
      const actual=await capture();
      if(actual.document_id!==expected.document_id || actual.active_layer_id!==expected.active_layer_id || actual.layer_ids.join(',')!==expected.layer_ids?.join(','))throw Error('Caps target changed');
      const doc=ps.app.activeDocument;
      function walk(layers){return Array.from(layers).flatMap(l=>[l,...(l.kind===ps.constants.LayerKind.GROUP?walk(l.layers):[])]);}
      const before=walk(doc.layers),order=before.map(l=>l.id),active=before.find(l=>l.id===actual.active_layer_id);
      const selected=before.filter(l=>actual.layer_ids.includes(l.id));
      if(!active || selected.length!==actual.layer_ids.length)throw Error('Caps target missing');
      if(['selectAbove','selectBelow','copyStyle','editStyle'].includes(command) && selected.length!==1)throw Error('此操作需要单选图层');
      const mutate=!['selectAbove','selectBelow','copyStyle'].includes(command);
      if(mutate && selected.some(l=>l.isBackgroundLayer || l.allLocked || l.positionLocked))throw Error('请先解锁目标图层');
      async function batch(descriptors){const values=await ps.action.batchPlay(descriptors,{});if(values.some(v=>v._obj==='error')){const v=values.find(v=>v._obj==='error');const e=Error(v.message || 'Photoshop rejected command');e.cancelled=v.result===-128;throw e;}return values;}
      async function effects(){const [v]=await batch([{_obj:'get',_target:[{_ref:'layer',_id:active.id},{_ref:'document',_id:doc.id}],_options:{dialogOptions:'dontDisplay'}}]);return v.layerEffects;}
      let history=null;
      if(mutate && command!=='editStyle')history=await context.hostControl.suspendHistory({documentID:doc.id,name:'Menu '+command});
      try {
        if(command==='selectAbove' || command==='selectBelow') {
          await batch([{_obj:'select',_target:[{_ref:'layer',_enum:'ordinal',_value:command==='selectAbove'?'forwardEnum':'backwardEnum'}],makeVisible:false,_options:{dialogOptions:'dontDisplay'}}]);
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
        const after=await capture(),now=walk(doc.layers).map(l=>l.id);
        if(after.document_id!==actual.document_id || now.length!==order.length || now.some(id=>!order.includes(id)))throw Error('Caps document/layer identity changed');
        if(!['selectAbove','selectBelow'].includes(command) && after.layer_ids.join(',')!==actual.layer_ids.join(','))throw Error('Caps selection changed');
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
