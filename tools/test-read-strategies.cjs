const assert=require('node:assert/strict');
const create=require('./fixtures/read-strategies-0.3.11/labels.js');
const k={NORMAL:'pixel',GROUP:'group',TEXT:'text',SMARTOBJECT:'smart',SOLIDFILL:'fill',CURVES:'curves',LEVELS:'levels',VIDEO:'video',LAYER3D:'3d',GRADIENTFILL:'gradient',PATTERNFILL:'pattern'};
const background={id:1,kind:k.NORMAL,isBackgroundLayer:true,positionLocked:true};
const a={id:2,kind:k.NORMAL},b={id:3,kind:k.TEXT},g={id:4,kind:k.GROUP,layers:[],allLocked:false};
const child={id:5,kind:k.SMARTOBJECT,parent:g};g.layers=[child];
const all=[background,a,b,g,child];const doc={id:10,title:'Read strategy benchmark scratch unit',layers:[a,b,g,background],activeLayers:[b],mode:'RGB',bitsPerChannel:8};
const special=['fill','gradient','pattern','curves','levels','video','3d'].map((kind,i)=>({id:20+i,kind}));
special.push({id:30,kind:k.SOLIDFILL,amKind:4}); // true shape vs pure fill (11)
all.push(...special);doc.layers.splice(3,0,...special);
let malformed=false,change=false,calls=0;
const ps={app:{documents:[doc],activeDocument:doc},constants:{LayerKind:k,DocumentMode:{RGB:'RGB'},BitsPerChannelType:{EIGHT:8,SIXTEEN:16}},action:{
  async batchPlay(descriptors,options){
    calls++;assert.equal(options.synchronousExecution,undefined);
    const result=descriptors.map(d=>{
      assert.ok(['get','multiGet'].includes(d._obj),'read only');
      const refs=d._target._ref || d._target;
      const id=refs.find(r=>r._ref==='layer')._id;
      assert.equal(refs.find(r=>r._ref==='document')._id,10);
      const layer=all.find(l=>l.id===id),map={pixel:1,curves:2,levels:2,text:3,fill:11,smart:5,video:6,group:7,'3d':8,gradient:9,pattern:10};
      const data={layerKind:layer.isBackgroundLayer?12:(layer.amKind || map[layer.kind]),background:!!layer.isBackgroundLayer,
        layerLocking:{protectAll:!!layer.allLocked,protectPosition:!!layer.positionLocked}};
      const fields=d._obj==='get'?[refs.find(r=>r._ref==='property')._property]:d.extendedReference[0];
      assert.ok(fields.length && fields.every(p=>p in data),'directed properties only');
      return Object.fromEntries(fields.filter(p=>!malformed || p!=='layerLocking').map(p=>[p,data[p]]));
    });
    if(change)doc.activeLayers=[a];
    return result;
  }
}};
const api=create(ps,'s');
async function main(){
  let checked=0;
  for(const selection of [[a],[b],[g],[child],[background],[a,b],[a,child],...special.map(l=>[l])]) {
    for(const locked of [false,true]) {
      g.allLocked=locked;doc.activeLayers=selection;
      const expected=api.selectionContext();
      for(const mode of ['get','multiget']) {assert.deepEqual(await api.selectionContextAsync(false,mode),expected);checked++;}
      const quick=api.selectionContext(true);
      for(const mode of ['get','multiget']) {assert.deepEqual(await api.selectionContextAsync(true,mode),quick);checked++;}
    }
  }
  doc.activeLayers=[b];malformed=true;
  await assert.rejects(api.selectionContextAsync(false,'multiget'),/Incomplete/);malformed=false;
  change=true;await assert.rejects(api.selectionContextAsync(false,'get'),/changed/);change=false;
  doc.activeLayers=[b];api.configureReads({mode:'multiget',refresh:'events',document_id:10});
  assert.equal(api.readPolicy().mode,'multiget');
  const now=Date.now;Date.now=()=>now()+91000;
  try {assert.equal(api.readPolicy().mode,'dom');}finally {Date.now=now;}
  assert.throws(()=>api.configureReads({mode:'arbitrary',refresh:'poll',document_id:10}),/disposable/);
  assert.throws(()=>api.configureReads({mode:'get',refresh:'poll',document_id:999}),/disposable/);
  doc.title='User document';assert.equal(api.readPolicy().mode,'dom');
  assert.throws(()=>api.configureReads({mode:'get',refresh:'poll',document_id:10}),/disposable/);
  api.configureReads(null);assert.equal(api.readPolicy().refresh,'poll');
  console.log('PASS '+checked+' full/quick DOM/get/multiGet capability comparisons, async identity/missing-field rejection, scoped expiring diagnostic policy; '+calls+' AM calls');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
