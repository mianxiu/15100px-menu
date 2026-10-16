import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const current=require('../../uxp/offline-probe/labels.js');
const reference=require('../../tools/fixtures/selection-context-0.3.18.cjs');
const k={NORMAL:'pixel',GROUP:'group',TEXT:'text',SMARTOBJECT:'smart',SOLIDFILL:'fill',GRADIENTFILL:'gradient',PATTERNFILL:'pattern',CURVES:'curves',LEVELS:'levels',VIDEO:'video'};
function host(layers){
 const doc={id:10,layers,activeLayers:[],mode:'RGB',bitsPerChannel:8};
 const ps={constants:{LayerKind:k,DocumentMode:{RGB:'RGB',CMYK:'CMYK',LAB:'LAB',GRAYSCALE:'GRAY'},BitsPerChannelType:{EIGHT:8,SIXTEEN:16}},app:{documents:[doc],activeDocument:doc},action:{batchPlay(){throw Error('No AM calls on snapshot path');}}};
 return {doc,ps,old:reference(ps,'s'),next:current(ps,'s')};
}
function equal(h,quick=false){assert.deepEqual(h.next.selectionContext(quick),h.old.selectionContext(quick));}

test('optimized snapshots match frozen UXP18 fields for all root selections, locks, kinds and background positions',()=>{
 let comparisons=0;
 for(let background=-1;background<6;background++)for(let lock=0;lock<4;lock++)for(let variant=0;variant<3;variant++){
  const layers=Array.from({length:6},(_,i)=>({id:100+i,kind:['pixel','text','smart','fill','curves','group'][(i+variant)%6],layers:i%2?[{id:500+i}]:[],isBackgroundLayer:i===background,allLocked:lock===1 && i===2,positionLocked:lock===2 && i===3,parent:null}));
  const h=host(layers);h.doc.mode=lock===3?'CMYK':'RGB';h.doc.bitsPerChannel=variant===2?32:8;
  for(let bits=1;bits<64;bits++){
   h.doc.activeLayers=layers.filter((_,i)=>bits&(1<<i));equal(h);equal(h,true);comparisons+=2;
  }
 }
 assert.equal(comparisons,10584);
});

test('nested, cross-parent, missing membership, unknown type and quick-only results remain identical',()=>{
 const outer={id:1,kind:'group',allLocked:false},inner={id:2,kind:'group',parent:outer},a={id:3,kind:'pixel',parent:inner},b={id:4,kind:'text',parent:inner},outside={id:5,kind:'gradient'};
 inner.layers=[a,b];outer.layers=[inner];const h=host([outer,outside]);
 for(const locked of [false,true])for(const pos of [false,true]){
  outer.allLocked=locked;inner.positionLocked=pos;
  for(const selected of [[outer],[inner],[a],[b],[a,b],[a,outside],[{id:90,kind:'pixel',parent:inner}],[{id:91,kind:'unknown'}]]){
   h.doc.activeLayers=selected;equal(h);equal(h,true);
  }
 }
 h.ps.app.documents=[];equal(h);
});

test('single position reuse and multi prefix stop reduce host ID reads without changing results',()=>{
 for(const indices of [[0],[150],[299],[50,51],[50,150],[0,299]]){
  let reads=0;
  const layers=Array.from({length:300},(_,i)=>({get id(){reads++;return i+1;},kind:'pixel',parent:null}));
  const h=host(layers);h.doc.activeLayers=indices.map(i=>layers[i]);
  const expected=h.old.selectionContext(),before=reads;reads=0;
  assert.deepEqual(h.next.selectionContext(),expected);const after=reads;
  assert.ok(after<=before,JSON.stringify({indices,before,after}));
  if(indices.at(-1)<299)assert.ok(after<before*.65,JSON.stringify({indices,before,after}));
 }
});

test('later snapshots immediately observe lock, parent, order, type, mode and depth changes',()=>{
 const a={id:1,kind:'pixel',parent:null},b={id:2,kind:'pixel',parent:null},c={id:3,kind:'pixel',parent:null};
 const h=host([a,b,c]);h.doc.activeLayers=[b];equal(h);
 for(const change of [()=>b.positionLocked=true,()=>b.positionLocked=false,()=>h.doc.layers=[b,a,c],()=>b.kind='smart',()=>h.doc.mode='CMYK',()=>h.doc.bitsPerChannel=32,()=>h.doc.activeLayers=[a,c],()=>h.doc.layers=[a,c]]){change();equal(h);equal(h,true);}
});

test('fresh sibling collections preserve results while materializing only required DOM objects',()=>{
 const layers=Array.from({length:300},(_,i)=>({id:i+1,kind:'pixel',parent:null}));
 let lengths=0,indices=0;
 const collection=new Proxy({},{get(_,key){
  if(key===Symbol.iterator)return Array.prototype[Symbol.iterator];
  if(key==='length'){lengths++;return layers.length;}
  if(typeof key==='string' && /^\d+$/.test(key)){indices++;return layers[Number(key)];}
 }});
 const h=host(collection);h.doc.activeLayers=[layers[150]];
 const expected=h.old.selectionContext();assert.equal(indices,300);assert.ok(lengths>=300);
 lengths=0;indices=0;
 assert.deepEqual(h.next.selectionContext(),expected);assert.equal(lengths,1);assert.ok(indices<160);
 h.doc.activeLayers=[layers[299]];lengths=0;indices=0;
 equal(h);assert.ok(indices<305); // old full copy + new endpoint/neighbor objects
});

test('document or selection change during a snapshot still rejects the result',()=>{
 for(const factory of [reference,current])for(const changeDocument of [false,true]){
  const a={id:1,kind:'pixel'},b={id:2,kind:'pixel'},h=host([a,b]);let read=0;
  Object.defineProperty(h.doc,'activeLayers',{get(){read++;return read===1 || changeDocument?[a]:[b];}});
  if(changeDocument){let calls=0;Object.defineProperty(h.ps.app,'activeDocument',{get(){return ++calls===1?h.doc:{...h.doc,id:20};}});}
  assert.throws(()=>factory(h.ps,'s').selectionContext(),/changed during read/);
 }
});

test('tiny lists and majority selections retain the original ordered host property reads',()=>{
 for(const [count,selected] of [[4,1],[20,15]]){
  let trace=[];
  const layers=Array.from({length:count},(_,i)=>new Proxy({id:i+1,kind:'pixel',parent:null},{get(target,key){trace.push(i+':'+String(key));return target[key];}}));
  const h=host(layers);h.doc.activeLayers=layers.slice(1,selected+1);
  const expected=h.old.selectionContext(),before=trace;trace=[];
  assert.deepEqual(h.next.selectionContext(),expected);assert.deepEqual(trace,before);
 }
});
