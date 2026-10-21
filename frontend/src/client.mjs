export class Client {
  constructor(url, status, event) {
    this.url = url; this.status = status; this.event = event;
    this.pending = new Map(); this.sequence = 0; this.stopped = false;
  }
  connect() {
    if (this.stopped || this.socket?.readyState === 0 || this.socket?.readyState === 1) return;
    this.status('connecting');
    const socket = this.socket = new WebSocket(this.url);
    socket.onopen = () => { if (this.socket === socket) this.status('connected'); };
    socket.onmessage = e => {
      if (this.socket !== socket) return;
      let message;
      try { message = JSON.parse(e.data); } catch { return; }
      if (message.type !== 'response') { this.event(message); return; }
      const request = this.pending.get(message.id);
      if (!request) return;
      clearTimeout(request.timer); this.pending.delete(message.id);
      message.ok ? request.resolve(message.data) : request.reject(new Error(message.error || '操作失败'));
    };
    socket.onerror = () => socket.close();
    socket.onclose = () => {
      if (this.socket !== socket) return;
      this.status('disconnected');
      this.rejectPending('连接断开，操作结果未知；请检查 Photoshop 后再试');
      if (!this.stopped) this.reconnect = setTimeout(() => this.connect(), 2000);
    };
  }
  request(action, args = {}) {
    if (this.socket?.readyState !== 1) return Promise.reject(new Error('后台服务未连接'));
    const id = String(++this.sequence);
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error('响应超时，操作结果未知；请检查 Photoshop，避免重复执行'));
      }, action==='text.split'?175000:50000);
      this.pending.set(id, {resolve, reject, timer, action});
      try { this.socket.send(JSON.stringify({id, action, args})); }
      catch (error) { clearTimeout(timer); this.pending.delete(id); reject(error); }
    });
  }
  rejectPending(message) {
    for (const request of this.pending.values()) {
      clearTimeout(request.timer);
      request.reject(new Error(request.action.startsWith('application.update.') ? '应用更新连接断开，请重新连接查看更新状态；不会重复安装' : message));
    }
    this.pending.clear();
  }
  close() {
    this.stopped = true; clearTimeout(this.reconnect);
    this.rejectPending('连接已关闭');
    this.socket?.close();
  }
}
