import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const current=require('../../uxp/offline-probe/labels.js');
const reference=require('../../tools/fixtures/selection-context-0.3.18.cjs');
const previous=require('../../tools/fixtures/selection-context-0.3.20.cjs');
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

test('warm middle lookup uses fresh collections and bounded object construction for single and multi selection',()=>{
 for(const selection of [[150],[149,150,151]]) {
  const layers=Array.from({length:300},(_,i)=>({id:i+1,kind:'pixel',parent:null}));
  let materialized=0,collections=0;
  const h=host([]);Object.defineProperty(h.doc,'layers',{get(){collections++;return new Proxy(layers,{get(t,key){
   if(typeof key==='string' && /^\d+$/.test(key))materialized++;
   return Reflect.get(t,key);
  }});}});
  h.doc.activeLayers=selection.map(i=>layers[i]);
  h.next.selectionContext();materialized=0;collections=0;
  const actual=h.next.selectionContext();assert.equal(collections,1);assert.ok(materialized<=8,materialized);
  assert.deepEqual(actual,h.old.selectionContext());
  // The same identity must expose changed properties immediately on a hit.
  layers[150].positionLocked=true;equal(h);layers[150].positionLocked=false;
  layers[150].kind='text';equal(h);h.doc.bitsPerChannel=32;equal(h);
 }
});

test('stale position hints survive reorders, deletion, insertion, undo, groups and backgrounds without stale capabilities',()=>{
 const layers=Array.from({length:80},(_,i)=>({id:100+i,kind:'pixel',parent:null,isBackgroundLayer:i===79}));
 const group={id:900,kind:'group',parent:null,layers:[]};
 const h=host([...layers,group]);h.doc.activeLayers=[layers[40]];equal(h);
 for(const selected of [[layers[40]],[layers[39],layers[40]]]) {
  h.doc.activeLayers=selected;equal(h);
  for(const change of [
   ()=>h.doc.layers.reverse(),
   ()=>h.doc.layers.splice(10,0,{id:999,kind:'smart'}),
   ()=>h.doc.layers.splice(h.doc.layers.indexOf(layers[40]),1),
   ()=>h.doc.layers=[...layers,group],
   ()=>{group.layers=layers.slice(20,60);for(const l of group.layers)l.parent=group;h.doc.layers=[...layers.slice(0,20),group,...layers.slice(60)];},
   ()=>group.layers.reverse(),()=>group.allLocked=true,()=>group.allLocked=false,
   ()=>{for(const l of layers)l.parent=null;h.doc.layers=[...layers,group];},
  ]){change();equal(h);equal(h,true);}
 }
});

test('position hints remain advisory through thousands of selections and document identities',()=>{
 const layers=Array.from({length:70},(_,i)=>({id:i+1,kind:'pixel',parent:null})),h=host(layers);
 let seed=151;
 const random=n=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed%n;};
 for(let i=0;i<2300;i++) {
  if(i%70===0)h.doc.id++;
  if(i%3===0){const a=random(70),b=random(70);[layers[a],layers[b]]=[layers[b],layers[a]];}
  h.doc.activeLayers=[layers[random(70)]];
  if(i%5===0)h.doc.activeLayers.push(layers[(layers.indexOf(h.doc.activeLayers[0])+1)%70]);
  equal(h);
 }
});

test('a selection change during a warm hint read still fails the final identity check',()=>{
 const layers=Array.from({length:100},(_,i)=>({id:i+1,kind:'pixel',parent:null})),h=host(layers);
 h.doc.activeLayers=[layers[50]];h.next.selectionContext();
 let calls=0;Object.defineProperty(h.doc,'activeLayers',{get(){return ++calls===1?[layers[50]]:[layers[51]];}});
 assert.throws(()=>h.next.selectionContext(),/changed during read/);
});


test('warm hints preserve complete UXP20 fields across large selections and repeated reorder mutations',()=>{
 const layers=Array.from({length:100},(_,i)=>({id:200+i,kind:i%11===0?'group':'pixel',layers:[],parent:null,isBackgroundLayer:i===99}));
 const h=host(layers),old=previous(h.ps,'s');
 for(let round=0;round<120;round++) {
  h.doc.activeLayers=round%3===0?[layers[40],layers[41]]:[layers[50]];
  if(round%4===0)layers.reverse();
  layers[50].allLocked=round%7===0;
  assert.deepEqual(h.next.selectionContext(),old.selectionContext());
 }
});
