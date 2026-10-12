const assert=require('node:assert/strict');
const create=require('../uxp/offline-probe/labels.js');
(async()=>{
  let made=0,rolledBack=0;
  const app={documents:[],createDocument:async options=>{
    assert.equal(JSON.parse(options.presetJSON).units,'millimetersUnit');made++;
    const doc={id:99,title:'A4',width:2480,height:3508,resolution:300,
      closeWithoutSaving:async()=>{rolledBack++;app.documents=[];}};
    app.documents=[doc];app.activeDocument=doc;return doc;
  }};
  const api=create({app,core:{executeAsModal:async fn=>fn({isCancelled:false})}},'session');
  const target=api.documentTarget();
  const request={target,preset:{width:210,height:297,units:'millimetersUnit',resolution:'print'},expires_at_ms:Date.now()+5000};
  for(const changed of [{...target,session:'stale'},{...target,document_ids:[1]}, {...target,active_document_id:4}])
    await assert.rejects(api.createDocument({...request,target:changed}));
  await assert.rejects(api.createDocument({...request,expires_at_ms:0}));
  await assert.rejects(api.createDocument({...request,preset:{...request.preset,width:-1}}));
  assert.equal(made,0);
  assert.equal((await api.createDocument(request)).document_id,99);
  await assert.rejects(api.createDocument(request));assert.equal(made,1);assert.equal(rolledBack,0);
  console.log('PASS: preset JSON unchanged; session/document-set/active/expiry/size fences; no repeat');
})().catch(error=>{console.error(error);process.exitCode=1;});
