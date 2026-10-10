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
