import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../../uxp/offline-probe/labels.js',import.meta.url),'utf8');
function setup(){
 const state={selected:2,order:[1,2,3],writes:[],history:[],effects:{_obj:'layerEffects',scale:{_unit:'percentUnit',_value:100},stroke:{enabled:true}},cancel:false,failPaste:false};
 const doc={id:10,get layers(){return state.order.map(id=>layers[id]);},get activeLayers(){return [layers[state.selected]];}};
 const layers={};for(const id of state.order)layers[id]={id,parent:null,kind:'normal',isBackgroundLayer:false,allLocked:false,positionLocked:false,move:async(anchor,where)=>{state.writes.push('move');state.order=state.order.filter(v=>v!==id);state.order.splice(state.order.indexOf(anchor.id)+(where==='before'?0:1),0,id);}};
 const target=()=>({session:'s',document_id:10,active_layer_id:state.selected,layer_ids:[state.selected]});
 const ps={app:{activeDocument:doc},constants:{LayerKind:{GROUP:'group'},ElementPlacement:{PLACEBEFORE:'before',PLACEAFTER:'after'}},core:{executeAsModal:async(fn,options)=>{state.options=options;return fn({hostControl:{suspendHistory:async()=>{state.history.push('begin');return 4;},resumeHistory:async(_,ok)=>state.history.push(ok?'commit':'rollback')}});}},action:{batchPlay:async(ds)=>ds.map(d=>{
  if(d._obj==='get')return {layerEffects:structuredClone(state.effects)};
  state.writes.push(d._obj);
  if(d._obj==='select')state.selected=d._target[0]._value==='forwardEnum'?1:3;
  if(d._obj==='set'){state.display=d;if(state.cancel)return {_obj:'error',result:-128};}
  if(d._obj==='pasteEffects' && state.failPaste)state.effects=null;
  return {};
 })}};
 const factory=vm.runInNewContext(source.slice(source.indexOf('function createCapsActions'))+'\ncreateCapsActions;');
 const capture=async()=>target();
 const caps=factory(ps,'s',capture,()=>({document_id:10,layer_ids:[state.selected]}),undefined,capture);
 return {state,run:command=>caps.execute({command,target:target(),expires_at_ms:Date.now()+10000}),caps};
}
test('Caps select preserves layer topology and copy does not add document history',async()=>{
 const {state,run}=setup();await run('selectAbove');assert.equal(state.selected,1);assert.deepEqual(state.order,[1,2,3]);
 await run('copyStyle');assert.deepEqual(state.history,[]);assert.ok(state.writes.includes('copyEffects'));
});
test('Caps step movement and paste each commit one history transaction; failure rolls back',async()=>{
 const {state,run}=setup();await run('moveUp');assert.deepEqual(state.order,[2,1,3]);assert.deepEqual(state.history,['begin','commit']);
 state.history=[];await run('pasteStyle');assert.deepEqual(state.history,['begin','commit']);
 state.history=[];state.failPaste=true;await assert.rejects(run('pasteStyle'));assert.deepEqual(state.history,['begin','rollback']);
});
test('native style dialog receives existing effects intact and cancellation is non-mutating feedback',async()=>{
 const {state,run}=setup();const original=structuredClone(state.effects);state.cancel=true;
 const value=await run('editStyle');assert.equal(value.cancelled,true);assert.equal(state.options.interactive,true);
 assert.deepEqual(state.display.to,original);assert.equal(state.display._options.dialogOptions,'display');assert.deepEqual(state.history,[]);
});
test('changed identity and locked targets reject before mutations',async()=>{
 const {state,caps}=setup();await assert.rejects(caps.execute({command:'pasteStyle',target:{session:'s',document_id:10,active_layer_id:99,layer_ids:[99]},expires_at_ms:Date.now()+10000}));
 assert.deepEqual(state.writes,[]);assert.deepEqual(state.history,[]);
});
