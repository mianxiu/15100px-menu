// Production mailbox, no real Photoshop or system input language changes.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('uxp/offline-probe/main.js','utf8');
const settle=async()=>{for(let i=0;i<30;i++)await new Promise(resolve=>setImmediate(resolve));};
async function host(){
  const files=new Map(),timers=new Map(),state={reads:0,tool:{classID:'typeCreateOrEditTool',isModal:false}};
  const folder={getEntry:async name=>{if(!files.has(name))throw Error('missing');return {read:async()=>files.get(name)};},
    createFile:async name=>({write:async text=>files.set(name,text)})};
  const ps={app:{documents:[]},core:{getActiveTool:async()=>{state.reads++;if(state.wait)await state.wait;if(state.error)throw Error('unavailable');return state.tool;}},
    action:{addNotificationListener(){}}};
  const sandbox={module:{exports:{}},console,Date,setTimeout,clearTimeout,setInterval(fn,ms){timers.set(ms,fn);},
    require(name){
      if(name==='photoshop')return ps;
      if(name==='uxp')return {host:{version:'24.0.1'},versions:{uxp:'6'},storage:{localFileSystem:{getDataFolder:async()=>folder,getPluginFolder:async()=>{throw Error('optional');}}}};
      if(name==='./probe-config.js')return 'private-test-token';
      if(name==='./labels.js')return (ps,session)=>{state.session=session;return {interfacePreferences:async()=>({}),selectionContextFresh:async()=>({})};};
      throw Error(name);
    }};
  vm.runInNewContext(source,sandbox);await settle();
  return {files,state,poll:async()=>{timers.get(16)();await settle();},
    request(changes={}){const request={schema:1,id:'a'.repeat(32),token:'private-test-token',session:state.session,expires_at_ms:Date.now()+1000,...changes};files.set('input-tool-request.json',JSON.stringify(request));return request;},
    response:()=>JSON.parse(files.get('input-tool-response.json'))};
}
(async()=>{
  for(const change of [{schema:2},{token:'other'},{session:'other'},{id:'invalid'},{expires_at_ms:Date.now()-1000},{expires_at_ms:Date.now()+90000}]){
    const h=await host();h.request(change);await h.poll();assert.equal(h.state.reads,0);assert.equal(h.files.has('input-tool-response.json'),false);
  }
  const h=await host();const request=h.request();await h.poll();
  assert.equal(h.state.reads,1);assert.deepEqual(h.response(),{schema:1,id:request.id,session:request.session,token:request.token,phase:'completed',classID:'typeCreateOrEditTool',isModal:false,completed_at_ms:h.response().completed_at_ms});
  await h.poll();assert.equal(h.state.reads,1,'Do not re-run the consumed observation');
  h.state.tool.isModal=true;h.request({id:'b'.repeat(32)});await h.poll();assert.equal(h.response().isModal,true);
  let release;h.state.wait=new Promise(resolve=>release=resolve);h.request({id:'c'.repeat(32)});await h.poll();await h.poll();assert.equal(h.state.reads,3,'Only one tool read may be in flight');
  release();await settle();assert.equal(h.response().id,'c'.repeat(32));h.state.wait=null;
  for(const [i,tool] of [{classID:'x',isModal:0},{classID:'',isModal:false},{classID:'moveTool',isModal:null}].entries()){
    h.state.tool=tool;h.request({id:String(i+4).repeat(32)});await h.poll();assert.equal(h.response().phase,'failed');
  }
  h.state.error=true;h.request({id:'f'.repeat(32)});await h.poll();assert.equal(h.response().phase,'failed');
  assert.equal(h.files.has('probe-request.json'),false);assert.equal(h.files.has('probe-response.json'),false);
  console.log('PASS: authenticated read-only tool state / idle Type tool / modal editing / one in flight / no replay or document mutation');
})().catch(error=>{console.error(error);process.exitCode=1;});
