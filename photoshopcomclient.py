"""Compatibility client for the four legacy action names."""
import asyncio
import json
from tornado.httpclient import HTTPRequest
from tornado.websocket import websocket_connect

async def _send(action, port):
    origin = f"http://127.0.0.1:{port}"
    socket = await websocket_connect(HTTPRequest(origin.replace("http:", "ws:") + "/websocket", headers={"Origin": origin}))
    try:
        await socket.write_message(json.dumps({"id": "legacy", "action": "action.execute", "args": {"name": action}}))
        while True:
            raw = await asyncio.wait_for(socket.read_message(), 50)
            if raw is None:
                raise RuntimeError("服务连接已断开，操作结果未知")
            message = json.loads(raw)
            if message.get("id") == "legacy":
                if not message["ok"]:
                    raise RuntimeError(message["error"])
                return message["data"]
    finally:
        socket.close()

def sendSome(jsx: str, port=15151):
    return asyncio.run(_send(jsx, port))
