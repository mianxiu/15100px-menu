// Frozen v0.4.147 / UXP0.3.18 reference for differential tests.
// labels.js SHA256: 8b47932652d88afba0ad793b3da7ad323516a9857be70dd4aa4b44fc05d0743b
module.exports=function(ps,session){
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
return {selectionContext};
};
