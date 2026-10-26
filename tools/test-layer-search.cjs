const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require.resolve('../uxp/offline-probe/labels.js'),'utf8');
let activeDoc=1,selected=[11,12],active=12,writes=0,failSelect=false,failRestore=false,badList=false;
const row=(id,name,kind=1,extra={})=>({layerID:id,name,layerKind:kind,parentLayerID:0,layerSection:{_value:'layerSectionContent'},...extra});
let docs=[{id:1,title:'原稿.psd',rows:[row(11,'重名'),row(12,'重名',3)]},{id:2,title:'目标.psd',rows:[row(21,'重名',4,{hasVectorMask:true}),row(22,'填充',4)]}];
const capture=async()=>({session:'s',document_id:activeDoc,active_layer_id:active,layer_ids:[...selected].sort((a,b)=>a-b)});
const ps={core:{executeAsModal:async fn=>fn({isCancelled:false})},action:{batchPlay:async commands=>commands.map(c=>{
  const ref=c._target?._ref||c._target,docRef=ref.find(r=>r._ref==='document'),doc=docRef?docs.find((d,i)=>docRef._id?d.id===docRef._id:i+1===docRef._index):docs.find(d=>d.id===activeDoc);
  if(c._obj==='get'){
    assert.equal(c._options.dialogOptions,'silent');
    if(!doc)return {_obj:'error'};
    return {[ref[0]._property]:({documentID:doc.id,title:doc.title,numberOfLayers:doc.rows.length,hasBackgroundLayer:false,mode:{_value:'RGBColor'}})[ref[0]._property]};
  }
  if(c._obj==='multiGet'){
    assert.equal(c._options.dialogOptions,'silent');
    if(!doc)return {_obj:'error'};
    if(c.extendedReference[1]){const {index,count}=c.extendedReference[1];return {list:badList?[]:doc.rows.slice(index-1,index-1+count)};}
    return doc.rows.find(r=>r.layerID===ref[0]._id)||{_obj:'error'};
  }
  if(c._obj==='select'){
    writes++;assert.equal(c._options.dialogOptions,'silent');
    if(docRef){if(!doc)return {_obj:'error'};activeDoc=doc.id;return {};}
    assert.equal(c.makeVisible,false);
    if(failSelect&&ref[0]._id===21||failRestore&&ref[0]._id===11)return {_obj:'error'};
    active=ref[0]._id;selected=c.selectionModifier?[...selected,active]:[active];return {};
  }
  throw Error('Unexpected command '+c._obj);
})}};
const context={ps,capture,session:'s',nativeDocumentCount:async()=>docs.length};
vm.createContext(context);vm.runInContext(source.slice(source.lastIndexOf('function createLayerSearch('))+'\nthis.search=createLayerSearch(ps,session,capture);',context);
const search=context.search,query={name:'重名',document:'',type:'all'};
(async()=>{
  let checks=0;
  const result=await search.search(query,async()=>checks++);
  assert.equal(result.items.length,3);assert.equal(checks,12);assert.equal(writes,0);
  assert.deepEqual(Array.from(result.items,r=>r.type),['pixel','text','shape']);
  let disposed=0;const original=JSON.stringify(await capture());
  const tile={width:2,height:1,components:4,componentSize:8,getData:async()=>new Uint8Array([255,0,0,255,0,255,0,128]),dispose:()=>disposed++};
  assert.equal((await search.preview(result.items[0])).available,false);
  ps.imaging={getPixels:async options=>{assert.equal(options.layerID,11);assert.equal(options.targetSize.width,128);return {imageData:tile};}};
  const image=await search.preview(result.items[0]);assert.deepEqual(Array.from(image.pixels),[255,0,0,255,0,255,0,128]);assert.equal(disposed,1);
  assert.equal(JSON.stringify(await capture()),original);assert.equal(writes,0);
  tile.getData=async()=>{throw Error('pixels failed');};await assert.rejects(search.preview(result.items[0]),/pixels failed/);assert.equal(disposed,2);
  tile.getData=async()=>new Uint8Array(8);ps.imaging.getPixels=async()=>{docs[0].rows[0].name='changed';return {imageData:tile};};
  await assert.rejects(search.preview(result.items[0]),/已改变/);assert.equal(disposed,3);docs[0].rows[0].name='重名';
  assert.equal((await search.search({...query,document:'目标',type:'shape'})).items[0].layer_id,21);
  assert.equal((await search.search({...query,name:'',type:'fill'})).items[0].layer_id,22);
  await assert.rejects(search.search({...query,type:'bad'}),/无效/);
  badList=true;await assert.rejects(search.search(query),/列表已改变/);badList=false;
  await assert.rejects(search.search(query,()=>{throw Error('yield');}),/yield/);assert.equal(writes,0);
  const destination=result.items[2],request={target:await capture(),destination,expires_at_ms:Date.now()+5000};
  await assert.rejects(search.focus({...request,destination:{...destination,name:'changed'}}),/已改变/);assert.equal(writes,0);
  failSelect=true;await assert.rejects(search.focus(request),/读取失败/);assert.deepEqual(await capture(),request.target);
  failRestore=true;await assert.rejects(search.focus(request),error=>error.resultUnknown===true);failRestore=false;failSelect=false;
  activeDoc=1;selected=[11,12];active=12;
  await search.focus(request);assert.equal(activeDoc,2);assert.deepEqual(selected,[21]);
  await assert.rejects(search.focus(request),/当前选择已改变/);
  docs=[{id:1,title:'Large.psd',rows:Array.from({length:600},(_,i)=>row(i+1,'x'))}];
  const limited=await search.search({...query,name:''});assert.equal(limited.items.length,500);assert.equal(limited.truncated,true);

  docs=[{id:1,title:'原稿.psd',rows:[row(11,'重名'),row(12,'重名',3)]}];activeDoc=1;selected=[11,12];active=12;
  // The old-host path owns only its temporary document and file.
  const bmp=new ArrayBuffer(62),bmpView=new DataView(bmp);
  bmpView.setUint16(0,0x4d42,true);bmpView.setUint32(10,54,true);bmpView.setInt32(18,2,true);bmpView.setInt32(22,1,true);bmpView.setUint16(28,24,true);
  new Uint8Array(bmp).set([0,0,255,0,255,0,0,0],54);
  let removed=0,closed=0,created=0,failSave=false,failClose=false;
  const sourceDoc={id:1,layers:[],activeLayers:[{id:11},{id:12}],activeHistoryState:{id:7},mode:'RGB',bitsPerChannel:8,width:2,height:1,resolution:72,colorProfileName:'sRGB'};
  const sourceLayer={id:11,duplicate:async temp=>({visible:false,bounds:{left:0,top:0,right:2,bottom:1}})};sourceDoc.layers=[sourceLayer];
  ps.constants={DocumentMode:{RGB:'RGB'},BitsPerChannelType:{EIGHT:8},NewDocumentMode:{RGB:'RGB'},DocumentFill:{TRANSPARENT:'transparent'},ElementPlacement:{PLACEATBEGINNING:'beginning'},TrimType:{TRANSPARENT:'transparent'},BMPDepthType:{TWENTYFOUR:24}};
  const appDocs=[sourceDoc],file={read:async()=>bmp,delete:async()=>removed++};
  ps.app={documents:appDocs,createDocument:async options=>{
    assert.equal(options.width,2);assert.equal(options.depth,8);created++;activeDoc=900;
    const temp={id:900,width:2,height:1,trim:async()=>{},flatten:async()=>{},resizeImage:async(w,h)=>{assert.equal(w,2);assert.equal(h,1);},
      saveAs:{bmp:async(entry,options)=>{assert.equal(entry,file);assert.equal(options.depth,24);if(failSave)throw Error('save failed');}},
      closeWithoutSaving:async()=>{if(failClose)throw Error('close failed');appDocs.splice(1);closed++;}};
    appDocs.push(temp);return temp;
  }};
  context.require=()=>({storage:{formats:{binary:'binary'},localFileSystem:{getTemporaryFolder:async()=>({createFile:async()=>file})}}});
  ps.core.executeAsModal=async fn=>fn({isCancelled:false,hostControl:{registerAutoCloseDocument:async id=>assert.equal(id,900)}});
  const thumbnailRequest={id:'a'.repeat(32),target:await capture(),destination:result.items[0],expires_at_ms:Date.now()+5000};
  const beforePreview=JSON.stringify(await capture());
  const legacy=await search.thumbnail(thumbnailRequest);
  assert.deepEqual(Array.from(legacy.pixels),[255,0,0,255,0,255,0,255]);assert.equal(legacy.legacy,true);
  assert.equal(JSON.stringify(await capture()),beforePreview);assert.equal(appDocs.length,1);assert.equal(removed,1);assert.equal(closed,1);
  failSave=true;await assert.rejects(search.thumbnail(thumbnailRequest),/save failed/);failSave=false;
  assert.equal(appDocs.length,1);assert.equal(removed,2);assert.equal(closed,2);assert.equal(JSON.stringify(await capture()),beforePreview);
  await assert.rejects(search.thumbnail({...thumbnailRequest,destination:{...result.items[0],name:'stale'}}),/已改变/);assert.equal(created,2);
  failSave=failClose=true;await assert.rejects(search.thumbnail(thumbnailRequest),error=>error.resultUnknown===true);
  assert.equal(created,3);assert.equal(removed,3);assert.equal(closed,2);
  appDocs.splice(1);activeDoc=1;failSave=failClose=false;
  console.log('Legacy thumbnail: RGB pixels, bounded BMP, temporary cleanup, original selection, stale refusal and cleanup unknown passed');
  console.log('Layer search: name/file/type, native chunks, limits, yield, stale, cross-document, rollback and unknown passed');
  const worker=fs.readFileSync('uxp/offline-probe/main.js','utf8'),files=new Map(),id='a'.repeat(32);
  let calls=0;
  const mailbox={token:'t',session:'s',searchRefreshId:'',Date,
    labels:{searchLayers:async(query,tick)=>{calls++;await tick();return {items:[]};}},
    record:async(_,name,value)=>files.set(name,JSON.stringify(value))};
  vm.createContext(mailbox);
  vm.runInContext(worker.slice(worker.indexOf('async function refreshLayerSearch('),worker.indexOf('async function finishResponse(')),mailbox);
  const folder={getEntry:async name=>{if(!files.has(name))throw Error('missing');return {read:async()=>files.get(name)};}};
  files.set('layer-search-request.json',JSON.stringify({id,token:'t',session:'s',query,expires_at_ms:Date.now()+1000}));
  await mailbox.refreshLayerSearch(folder,Date.now(),async()=>{const error=Error('priority');error.menuReadInterrupted=true;throw error;});
  assert.match(JSON.parse(files.get('layer-search-result.json')).error,/优先/);
  assert.equal(await mailbox.refreshLayerSearch(folder,Date.now(),async()=>{}),false);assert.equal(calls,1);
  console.log('Search mailbox: priority interruption and no replay passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
