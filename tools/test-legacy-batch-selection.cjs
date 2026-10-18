// Execute the production guard against changing live descriptor snapshots.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('jsx/legacy_shape_preview.jsx','utf8');
const guard=source.slice(source.indexOf('        var selectionStream='),source.indexOf('        function unlocked('));
function fixture(n=128){
 const ids=Array.from({length:n},(_,i)=>i+3);let live=ids.slice(),encoding='A',reads=0,decoded=0,fail=false;
 const context={ids,request:{target:{document_id:7,active_layer_id:3}},app:{documents:[{}],activeDocument:{id:7}},doc:{activeLayer:{id:3}},
  s:v=>v,ActionReference:class{putProperty(){}putEnumerated(){}},executeActionGet(){reads++;if(fail)throw Error('Read failed');
   const snapshot=live.slice(),bytes=encoding+':'+snapshot.join(',');return {toStream:()=>bytes,getList:()=>({count:snapshot.length,getReference:i=>{decoded++;return {getIdentifier:()=>snapshot[i]};}})};
  }};
 vm.createContext(context);vm.runInContext(guard+'this.check=batchIdentity;',context);
 return {context,check:context.check,set(v,e='A'){live=v;encoding=e;},fail(){fail=true;},ids,stats:()=>({reads,decoded})};
}
{
 const f=fixture();f.check();for(let i=0;i<256;i++)f.check();
 assert.deepEqual(f.stats(),{reads:257,decoded:128}); // every write still reads host
 f.set(f.ids.slice().reverse(),'B');f.check();f.check();
 assert.deepEqual(f.stats(),{reads:259,decoded:256}); // equivalent reordered set
 f.set(f.ids.slice(1));assert.throws(f.check,/selection changed/);
 f.set([...f.ids.slice(0,-1),999]);assert.throws(f.check,/selection changed/);
 f.set([...f.ids.slice(0,-1),3]);assert.throws(f.check,/selection changed/);
 f.set(f.ids,'C');f.check();f.fail();assert.throws(f.check,/Read failed/);
}
for(const kind of ['document','active','closed']){
 const f=fixture(2);f.check();
 if(kind==='document')f.context.app.activeDocument.id=8;
 if(kind==='active')f.context.doc.activeLayer.id=4;
 if(kind==='closed')f.context.app.documents=[];
 assert.throws(f.check,/selection changed/);assert.equal(f.stats().reads,1);
}
// Fresh stream mismatch never modifies the previously verified identity.
{
 const f=fixture(2);f.check();f.set([3,9]);assert.throws(f.check);
 f.set([3,4]);f.check();assert.equal(f.stats().decoded,4);
}
console.log('PASS legacy batch selection: live reads, exact stream equality, reorder revalidation, changed/duplicate/missing IDs, document/active/close and read failure');

// The native invariant snapshot keeps presence, type, units and nested values.
{
 const types=['OBJECTTYPE','LISTTYPE','ENUMERATEDTYPE','UNITDOUBLE','DOUBLETYPE','INTEGERTYPE','BOOLEANTYPE','STRINGTYPE'];
 class Descriptor {
  constructor(){this.values={};}
  hasKey(k){return Object.hasOwn(this.values,k);}getType(k){return this.values[k][0];}
  toStream(){return JSON.stringify(this.values);}
 }
 for(const [name,type] of [['Object','OBJECTTYPE'],['List','LISTTYPE'],['Enumerated','ENUMERATEDTYPE'],['UnitDouble','UNITDOUBLE'],['Double','DOUBLETYPE'],['Integer','INTEGERTYPE'],['Boolean','BOOLEANTYPE'],['String','STRINGTYPE']]){
  Descriptor.prototype['put'+name]=function(k,...v){this.values[k]=[type,...v];};
  Descriptor.prototype['get'+name]=function(k){return this.values[k][1];};
 }
 for(const [name,pos] of [['ObjectType',1],['ObjectValue',2],['EnumerationType',1],['EnumerationValue',2],['UnitDoubleType',1],['UnitDoubleValue',2]])Descriptor.prototype['get'+name]=function(k){return this.values[k][pos];};
 const keys=types.map((_,i)=>'k'+i),box={keys,s:v=>v,DescValueType:Object.fromEntries(types.map(t=>[t,t])),ActionDescriptor:Descriptor};
 const code=source.slice(source.indexOf('        function contentStream('),source.indexOf('        // Reuse only local DOM'));
 vm.runInNewContext(code+'this.capture=contentStream;',box);
 const d=new Descriptor();d.putObject('k0','shape',{rgb:[1,2,3]});d.putList('k1',[{nested:[1,2]}]);d.putEnumerated('k2','kind','x');d.putUnitDouble('k3','px',3.5);d.putDouble('k4',2.5);d.putInteger('k5',2);d.putBoolean('k6',false);d.putString('k7','测试');
 assert.equal(box.capture(d),d.toStream());const original=box.capture(d);
 d.putDouble('vectorMaskFeather',8);assert.equal(box.capture(d),original); // editable field excluded
 for(const k of keys){const saved=d.values[k];delete d.values[k];assert.notEqual(box.capture(d),original);d.values[k]=saved;}
 d.putUnitDouble('k3','percent',3.5);assert.notEqual(box.capture(d),original);
 d.values.k0=['RAWTYPE','unsupported'];assert.throws(()=>box.capture(d),/Unsupported/);
}
{
 const code=source.slice(source.indexOf('        function sameMember('),source.indexOf('        function verify(wanted)'));
 const box={same:(a,b)=>JSON.stringify(a)===JSON.stringify(b),maskClose:(a,b)=>a.feather===b.feather&&a.density===b.density};
 vm.runInNewContext(code+'this.compare=sameMember;',box);
 const b={id:3,mask:{feather:2,density:50},content:{x:1},path:[1,2],content_bytes:'c\u0000x',path_bytes:'p\u0000x',parent_id:4,order:[3,5]};
 assert(box.compare({...b,content:null,path:null},b,b.mask));
 for(const changes of [{id:5},{content_bytes:'c\u0000y'},{path_bytes:'p\u0000y'},{parent_id:7},{order:[5,3]},{mask:{feather:3,density:50}}])assert(!box.compare({...b,...changes},b,b.mask));
 const semantic={...b};delete semantic.content_bytes;delete semantic.path_bytes;
 assert(box.compare(b,semantic,b.mask));assert(!box.compare({...b,path:[9]},semantic,b.mask));
}
console.log('PASS legacy invariant snapshots: complete typed fields, nested values, presence, units, exact bytes, initial semantic comparison and structural guards');
