// Run the production synchronous native reader against changing host snapshots.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const src=fs.readFileSync('jsx/legacy_shape_preview.jsx','utf8');
const code=src.slice(src.indexOf('        function desc('),src.indexOf('        function batchPath('));
function fixture(background=false){
 const rows=[{id:9,parent:-1,section:'layerSectionStart'}, {id:8,parent:9,section:'layerSectionContent'},
  {id:7,parent:9,section:'layerSectionStart'}, {id:6,parent:7,section:'layerSectionContent'},
  {id:5,parent:7,section:'layerSectionEnd'}, {id:4,parent:9,section:'layerSectionEnd'},
  {id:3,parent:-1,section:'layerSectionContent'}];
 if(background)rows.push({id:2,parent:-1,section:'layerSectionContent',background:true});
 const locks=['protectAll','protectComposite','protectPosition','protectTransparency'];let reads=0,identities=0;
 const first=background?0:1;
 class Ref{putProperty(k,v){this.property=v;}putIdentifier(k,v){this[k]=v;}putIndex(k,v){this.index=v;}}
 const descriptor=row=>({getInteger(k){if(k==='layerID')return row.id;if(k==='parentLayerID')return row.parent;if(k==='itemIndex')return row.index??rows.length-rows.indexOf(row);throw Error(k);},
  getEnumerationValue(k){assert.equal(k,'layerSection');return row.section;},getObjectValue(k){assert.equal(k,'layerLocking');return {getBoolean:k=>{assert(locks.includes(k));return !!row[k];}};},getBoolean(k){assert.equal(k,'background');return !!row.background;}});
 const doc={};Object.defineProperty(doc,'backgroundLayer',{get(){if(!background)throw Error('No background');return {};}});
 const box={s:v=>v,c:v=>v,name:v=>v,request:{target:{document_id:12}},doc,ids:[8,6,3],records:[8,6,3].map(id=>({original:{id}})),ActionReference:Ref,
  batchIdentity(){identities++;},executeActionGet(ref){reads++;if(ref.property)return {getInteger:k=>{assert.equal(k,'numberOfLayers');return rows.length-(background?1:0);}};
   assert(ref.document===12 || ref['Lyr ']);const row=ref.index===undefined?rows.find(x=>x.id===ref['Lyr ']):rows[rows.length-1-(ref.index-first)];if(!row)throw Error('Missing');return descriptor(row);}};
 vm.createContext(box);vm.runInContext(code+'this.read=nativeTree;this.locks=nativeLocks;',box);
 return {rows,box,read:()=>box.read(),locks:()=>box.locks(null),stats:()=>({reads,identities})};
}
for(const background of [false,true]){
 const f=fixture(background),a=f.read();assert.deepEqual([...a.orders.pnull],background?[9,3,2]:[9,3]);assert.deepEqual([...a.orders.p9],[8,7]);assert.equal(a.tree[6].parent,7);
 assert(!a.tree[5]);const previous=f.stats().reads;f.read();assert.equal(f.stats().reads,previous*2);assert.equal(f.stats().identities,2); // every validation reads all rows
 f.rows[1].protectPosition=true;assert.throws(f.read,/locked/);f.rows[1].protectPosition=false;
 f.rows[0].protectAll=true;assert.throws(f.read,/locked/);f.rows[0].protectAll=false;
 f.rows[2].protectAll=true;assert.throws(f.locks,/locked/);f.rows[2].protectAll=false;
 f.rows[2].protectPosition=true;f.read(); // original DOM group rule is allLocked only
 f.rows[3].parent=9;assert.throws(f.read,/parent/);f.rows[3].parent=7;
 f.rows[3].index=999;assert.throws(f.read,/index/);delete f.rows[3].index;
 f.rows[3].id=8;assert.throws(f.read,/tree/);f.rows[3].id=6;
 f.rows[4].parent=9;assert.throws(f.read,/Unbalanced/);f.rows[4].parent=7;
 f.box.ids=[999];assert.throws(f.read,/missing/);
}
for(const key of ['protectAll','protectComposite','protectPosition','protectTransparency','background']){
 const f=fixture();f.rows[3][key]=true;assert.throws(f.read,/locked/);assert.throws(f.locks,/locked/);
}
{
 const f=fixture();f.rows[0].parent=7;assert.throws(f.locks,/ancestry/);
}
console.log('PASS native tree: fresh complete rows, nested parents/siblings, section ends/background, ancestor locks, exact membership/index checks, fresh per-batch lock reads');
