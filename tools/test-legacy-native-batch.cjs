// Execute production batching helpers. Host integration is tested separately.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const src=fs.readFileSync('jsx/legacy_shape_preview.jsx','utf8');
const code=src.slice(src.indexOf('        function setter('),src.indexOf('        function applyBatch('));
function fixture(fault=''){
 const events=[],files=new Map(),abort={},records=[{layer:{id:9},original:{id:9},touched:false}];
 class Ref { constructor(){this.ids=[];}putIdentifier(...v){this.ids.push(v);}putName(...v){this.name=v;} }
 class Desc {constructor(){this.values={};}putReference(k,v){this.values[k]=v;}putUnitDouble(k,...v){this.values[k]=v;}putObject(k,...v){this.values[k]=v;}toStream(){return '\0\0\0\x10'+JSON.stringify(this.values);} }
 class File {constructor(path){this.path=path;}get exists(){return files.has(this.path);}open(){events.push('open');return fault!=='open';}write(v){files.set(this.path,v);return fault!=='write';}close(){}remove(){events.push('remove');files.delete(this.path);return true;} }
 const box={request:{id:'owned',session:'session',token:'secret',target:{document_id:7}},folder:'test',progressFrame:3,
  nativeReads:false,s:v=>v,c:v=>v,ActionReference:Ref,ActionDescriptor:Desc,File,DialogModes:{NO:0},records,batchChanged:false,batchNativeCalls:0,actionResidue:'',batchAbort:abort,
  range:(v,lo,hi)=>typeof v==='number'&&v>=lo&&v<=hi,
  batchIdentity(){events.push('identity');if(fault==='identity')throw Error('changed');},
  unlocked(){events.push('lock');if(fault==='lock')throw Error('locked');},
  app:{load(){events.push('load');if(fault==='load')throw Error('load failed');},doAction(action,set){events.push('play');assert.equal(action,'Apply');assert.equal(set,'PSMenuPreview_owned_3_0');if(fault==='play')throw Error('partial execution');}},
  executeAction(op,d){events.push(op);if(op==='delete'){assert.deepEqual(d.values.null.name,['actionSet','PSMenuPreview_owned_3_0']);if(fault==='delete')throw Error('cleanup failed');}},
  readControl:()=>null};
 vm.createContext(box);vm.runInContext(code+'this.make=setter;this.bytes=actionBytes;this.run=nativeBatch;',box);
 return {box,events,files,records,abort,command:()=>box.make(9,'feather',12.5),run(){return box.run([this.command()],[0],0);}};
}
{
 const f=fixture(),d=f.command();assert.deepEqual(d.values.null.ids,[['Lyr ',9],['document',7]]);
 assert.deepEqual(d.values['T   '][1].values,{vectorMaskFeather:['#Pxl',12.5]});
 const density=f.box.make(10,'density',42);assert.deepEqual(density.values['T   '][1].values,{vectorMaskDensity:['#Prc',42]});
 // Parse the actual ATN envelope independently, including Unicode and flags.
 const b=Buffer.from(f.box.bytes('测试',[d,density]),'latin1');let pos=0;
 const num=n=>{const x=b.readUIntBE(pos,n);pos+=n;return x;};
 const str=()=>{let n=num(4),s='';while(--n)s+=String.fromCharCode(num(2));assert.equal(num(2),0);return s;};
 assert.equal(num(4),16);assert.equal(str(),'测试');assert.equal(num(1),0);assert.equal(num(4),1);
 assert.equal(num(2),0);assert.equal(num(1),0);assert.equal(num(1),0);assert.equal(num(2),0);assert.equal(str(),'Apply');assert.equal(num(1),0);assert.equal(num(4),2);
 for(const command of [d,density]){assert.deepEqual([...b.subarray(pos,pos+4)],[0,1,0,0]);pos+=4;assert.equal(b.subarray(pos,pos+8).toString(),'longsetd');pos+=8;assert.equal(num(4),3);assert.equal(b.subarray(pos,pos+3).toString(),'Set');pos+=3;assert.equal(num(4),0xffffffff);const payload=command.toStream().slice(4);assert.equal(b.subarray(pos,pos+payload.length).toString(),payload);pos+=payload.length;}
 assert.equal(pos,b.length);assert.throws(()=>f.box.bytes('x',[]),/size/);assert.throws(()=>f.box.bytes('x',Array(33).fill(d)),/size/);assert.throws(()=>f.box.bytes('x',[{toStream:()=>'bad'}]),/stream/);
 f.run();assert.deepEqual(f.events,['open','load','identity','lock','play','delete','remove']);assert.equal(f.box.batchNativeCalls,1);assert.equal(f.box.actionResidue,'');assert.equal(f.files.size,0);assert.equal(f.records[0].touched,true);
}
for(const fault of ['open','write','load','identity','lock','play','delete']){
 const f=fixture(fault);assert.throws(()=>f.run());assert(f.events.filter(x=>x==='play').length<=1);
 if(['identity','lock','play'].includes(fault)){assert(f.events.includes('delete'));assert.equal(f.box.actionResidue,'');assert.equal(f.files.size,0);}
 if(['load','delete'].includes(fault))assert(f.box.actionResidue); // conservative unknown, no retry
 if(['open','write','load','identity','lock'].includes(fault))assert(!f.events.includes('play'));
}
{
 const f=fixture();f.box.nativeReads=true;
 f.box.nativeLocks=members=>{assert.deepEqual([...members],[0]);f.events.push('native-locks');};
 f.box.unlocked=()=>{throw Error('DOM must not be used on the native path');};
 f.run();assert(f.events.includes('native-locks'));assert(f.events.includes('play'));
 const blocked=fixture();blocked.box.nativeReads=true;blocked.box.nativeLocks=()=>{throw Error('fresh ancestor locked');};
 assert.throws(()=>blocked.run(),/ancestor locked/);assert(!blocked.events.includes('play'));assert.equal(blocked.box.actionResidue,'');
}
for(const invalid of ['', 'id','session','token','seq','lease']){
 const f=fixture();const p={id:'owned',session:'session',token:'secret',seq:4,lease_until_ms:Date.now()+2000,phase:'cancel'};
 if(invalid==='seq')p.seq=2;else if(invalid==='lease')p.lease_until_ms=0;else if(invalid)p[invalid]='wrong';
 f.box.readControl=()=>p;
 if(!invalid)assert.throws(()=>f.run(),e=>e===f.abort);else f.run();
 assert.equal(f.box.actionResidue,'');assert.equal(f.events.filter(x=>x==='play').length,1);assert.equal(f.files.size,0);
}
console.log('PASS native batch: bounded ATN, explicit document/layer, property isolation, cleanup, failures without replay, authenticated cancellation');

// Execute frame grouping: unchanged fields omitted; at most 16 layers/32 writes;
// readback happens before and after one redraw, and partial frames never advance.
for(const n of [2,7,8,17,128]){
 const records=Array.from({length:n},(_,i)=>({original:{id:i+1,mask:{feather:1,density:70+i%10}},layer:{id:i+1}}));
 records.mapMask=records.map(x=>({...x.original.mask}));const events=[],chunks=[];
 const box={records,request:{paint:{mask:{}}},batchUpdates:0,batchRedraws:0,
  batchValidate(){},verify(v){events.push('verify');assert.equal(v.length,n);},progress(){},batchIdentity(){},unlocked(){},
  setter:(id,key,value)=>({id,key,value}),set(id,key,value){events.push('set');},
  nativeBatch(commands,members,first){chunks.push({commands,members,first});assert(members.length<=16);assert(commands.length<=32);assert(commands.every(x=>x.key==='feather'));},
  app:{refresh(){events.push('redraw');}}};
 vm.runInNewContext(src.slice(src.indexOf('        function applyBatch('),src.indexOf('        function batchAck('))+'this.apply=applyBatch;',box);
 box.apply({mask:{feather:9}});assert.equal(box.batchUpdates,1);assert.equal(box.batchRedraws,1);
 assert.deepEqual(events.filter(x=>x!=='set'),['verify','verify','redraw','verify']);
 assert.equal(chunks.length,n<8?0:Math.ceil(n/16));
 records.mapMask.forEach((m,i)=>assert.deepEqual({...m},{feather:9,density:70+i%10}));
 const before=chunks.length;box.apply({mask:{feather:9}});assert.equal(chunks.length,before);assert.equal(box.batchRedraws,1);
 if(n>=8){
  const sentinel={};box.nativeBatch=()=>{throw sentinel;};const old=records.mapMask;
  assert.throws(()=>box.apply({mask:{feather:10}}),e=>e===sentinel);assert.equal(records.mapMask,old);assert.equal(box.batchUpdates,2);
 }
}
console.log('PASS frame batching: small direct path, threshold/tail/128, untouched density, no-op, one redraw, partial frame unacknowledged');
