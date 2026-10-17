// Disposable read-only host experiment. Optional modal owns reads only;
// no history suspension, writes, dialogs or arbitrary script entry.
const ps=require('photoshop'),uxp=require('uxp');let running=false,seen='';
function domTree(){const out=[],k=ps.constants.LayerKind,knownKinds=new Map();function allIds(layers,parent){return Array.from(layers).flatMap(l=>{const id=l.id,kind=knownKinds.has(id)?knownKinds.get(id):l.kind;knownKinds.set(id,kind);out.push({id,parent,group:kind===k.GROUP});return [id,...(kind===k.GROUP?allIds(l.layers,id):[])];});}allIds(ps.app.activeDocument.layers,null);return out;}
async function batchTree(){
 const d=ps.app.activeDocument,target=[{_ref:'document',_id:d.id}];
 const [n]=await ps.action.batchPlay([{_obj:'get',_target:[{_ref:'property',_property:'numberOfLayers'},...target],_options:{dialogOptions:'dontDisplay'}}],{});
 const count=n.numberOfLayers;if(!Number.isInteger(count)||count<1||count>4096)throw Error('Bound exceeded');
 const hasBackground=d.layers[d.layers.length-1].isBackgroundLayer;
 const [r]=await ps.action.batchPlay([{_obj:'multiGet',_target:{_ref:target},extendedReference:[['layerID','parentLayerID','layerSection','itemIndex'],{_obj:'layer',index:hasBackground?0:1,count:count+(hasBackground?1:0)}],options:{failOnMissingProperty:false,failOnMissingElement:false},_options:{dialogOptions:'dontDisplay'}}],{});
 if(!r||!Array.isArray(r.list)||r.list.length!==count+(hasBackground?1:0))throw Error('Incomplete native range');
 if(r.list.some(x=>!x||!x.layerSection||!['layerSectionContent','layerSectionStart','layerSectionEnd'].includes(x.layerSection._value)))throw Error('Missing native section');
 const rows=r.list.filter(x=>x.layerSection._value!=='layerSectionEnd');
 rows.sort((a,b)=>b.itemIndex-a.itemIndex);const seenIds=new Set(),seenIndices=new Set();
 return rows.map(x=>{
  const section=x.layerSection._value;
  if(!Number.isInteger(x.layerID)||x.layerID<=0||!Number.isInteger(x.parentLayerID)||x.parentLayerID===x.layerID||!Number.isInteger(x.itemIndex)||x.itemIndex<0||seenIds.has(x.layerID)||seenIndices.has(x.itemIndex)||!['layerSectionContent','layerSectionStart'].includes(section))throw Error('Invalid native scalar row');
  seenIds.add(x.layerID);seenIndices.add(x.itemIndex);
  return {id:x.layerID,parent:x.parentLayerID>0?x.parentLayerID:null,group:section==='layerSectionStart'};
 });
}
async function poll(){if(running)return;running=true;try{
 const f=await uxp.storage.localFileSystem.getDataFolder();let q;try{q=JSON.parse(await(await f.getEntry('request.json')).read());}catch(_){return;}
 if(!/^[a-f0-9]{32}$/.test(q.id)||q.id===seen||q.operation!=='compare-tree'||q.expires<Date.now()||q.expires>Date.now()+30000)return;
 seen=q.id;const out={id:q.id,read_only:true,samples:[]};
 try{
  const d=ps.app.activeDocument;if(d.id!==q.document_id||!d.title.startsWith('Diverse owned '))throw Error('Only matching owned scratch documents');
  const ids=Array.from(d.activeLayers,l=>l.id).sort().join(',');
  async function compare(){
  if(ps.app.activeDocument.id!==q.document_id)throw Error('Identity changed before read scope');
  for(let i=0;i<3;i++){
   const pair={},values={};for(const mode of ((i+q.round)%2?['batch','dom']:['dom','batch'])){const t=Date.now();values[mode]=mode==='dom'?domTree():await batchTree();pair[mode]=Date.now()-t;}
   if(JSON.stringify(values.dom)!==JSON.stringify(values.batch)){out.dom=values.dom;out.batch=values.batch;throw Error('Tree ID/parent/order/group mismatch');}
   if(ps.app.activeDocument.id!==q.document_id||Array.from(d.activeLayers,l=>l.id).sort().join(',')!==ids)throw Error('Identity changed');
   out.samples.push(pair);out.count=values.dom.length;
  }}
  if(q.modal===true)await ps.core.executeAsModal(compare,{commandName:'Owned read-only tree study',timeOut:0});else await compare();
  out.equal=true;out.scope=q.modal===true?'modal-read-only':'read-only';
 }catch(e){out.error=String(e);}
 await(await f.createFile('result.json',{overwrite:true})).write(JSON.stringify(out));
}finally{running=false;}}
uxp.entrypoints.setup({commands:{noop(){}}});setInterval(()=>poll().catch(()=>{}),30);
