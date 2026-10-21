import {test} from 'node:test';
import assert from 'node:assert/strict';
import {Client} from '../src/client.mjs';

class FakeSocket {
  static instances = [];
  readyState = 0;
  constructor() { FakeSocket.instances.push(this); }
  send(data) { this.sent = JSON.parse(data); }
  close() { this.readyState = 3; this.onclose?.(); }
  open() { this.readyState = 1; this.onopen?.(); }
  receive(data) { this.onmessage?.({data: JSON.stringify(data)}); }
}
globalThis.WebSocket = FakeSocket;

test('only bounded text split batch gets the longer response wait', async()=>{
  const original=globalThis.setTimeout,delays=[],client=new Client('ws://localhost',()=>{},()=>{});
  globalThis.setTimeout=(_,delay)=>{delays.push(delay);return {};};
  try {
    client.connect();client.socket.open();
    for(const action of ['text.split','text.replace','action.execute']){
      const pending=client.request(action);client.socket.receive({type:'response',id:client.socket.sent.id,ok:true,data:{}});await pending;
    }
    assert.deepEqual(delays,[175000,50000,50000]);assert.equal(client.pending.size,0);
  }finally{client.close();globalThis.setTimeout=original;}
});

test('app installation disconnect is reported separately and never replayed', async () => {
  const client=new Client('ws://localhost',()=>{},()=>{});
  client.connect();client.socket.open();const old=client.socket;
  const result=client.request('application.update.install');
  const rejected=assert.rejects(result,/不会重复安装/);
  old.close();await rejected;clearTimeout(client.reconnect);
  client.connect();client.socket.open();
  assert.equal(client.socket.sent,undefined);
  assert.equal(client.pending.size,0);client.close();
});

test('correlates replies and rejects interrupted operations without replay', async () => {
  const client = new Client('ws://localhost', () => {}, () => {});
  client.connect(); const socket = client.socket; socket.open();
  const request = client.request('status');
  socket.receive({type: 'response', id: socket.sent.id, ok: true, data: {connected: true}});
  assert.deepEqual(await request, {connected: true});
  const pending = client.request('action.execute', {name: 'color'});
  const rejected = assert.rejects(pending, /结果未知/);
  socket.close(); await rejected;
  assert.equal(client.pending.size, 0);
  client.close();
});

test('closed transport rejects requests and ignores old-socket events', async () => {
  const events = [];
  const client = new Client('ws://localhost', () => {}, e => events.push(e));
  await assert.rejects(client.request('status'), /未连接/);
  client.connect(); const old = client.socket; old.close();
  clearTimeout(client.reconnect); client.connect(); client.socket.open();
  old.receive({type: 'notice'});
  assert.equal(events.length, 0);
  client.close();
});
