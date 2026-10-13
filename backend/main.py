"""Local HTTP/WebSocket service and desktop application lifecycle."""
import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
import signal
import sys
import logging.handlers
from urllib.parse import urlparse

from tornado import web, websocket
from tornado.httpclient import AsyncHTTPClient, HTTPRequest
from .photoshop_bridge import ACTIONS, COMMANDS, PhotoshopBridge, load_scripts
from .uxp_bridge import UxpBridge
from .layer_labels import LABEL_COLORS
from .commands import command_contracts, validate_command
from .desktop import Desktop, Tray
from .control_window import ControlWindow
from .settings import Settings
from .plugins import Plugins, MAX_PACKAGE
from .paths import ROOT, runtime_dir
from .tasks import TaskStore, TaskCancelled
from .uxp_management import UxpManager
from .photoshop_launch import PhotoshopLauncher
from .language import read_language, save_language
from .recent_documents import RecentDocuments

APP_ID = "photoshop-menu"
from .version import APP_VERSION


def service_identity():
    return {"version": APP_VERSION, "pid": os.getpid(),
            "executable": str(Path(sys.executable).resolve()), "resource_root": str(ROOT)}


def allowed_origin(origin, port):
    try:
        parsed = urlparse(origin)
        return parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost") and parsed.port in (port, 3001)
    except ValueError:
        return False


class LocalHandler(web.RequestHandler):
    def prepare(self):
        if self.request.host.split(":", 1)[0] not in ("127.0.0.1", "localhost"):
            raise web.HTTPError(403)
        origin = self.request.headers.get("Origin")
        if origin and not allowed_origin(origin, self.application.port):
            raise web.HTTPError(403)


class HealthHandler(LocalHandler):
    def get(self):
        self.write({"ok": True, "app": APP_ID, **service_identity()})


class StatusHandler(LocalHandler):
    async def get(self):
        self.write(await self.application.dispatch("status", {}))


class TasksHandler(LocalHandler):
    def get(self):
        self.write(self.application.tasks.snapshot())


class ServiceHandler(LocalHandler):
    async def post(self):
        try:
            data = json.loads(self.request.body)
            if not isinstance(data, dict) or data.get("action") != "open":
                raise ValueError("未知的服务请求")
            self.write({"ok": True, "data": await self.application.dispatch("control.open", {})})
        except (ValueError, RuntimeError) as exc:
            self.set_status(400)
            self.write({"ok": False, "error": str(exc)})


class WSHandler(websocket.WebSocketHandler):
    def check_origin(self, origin):
        return allowed_origin(origin, self.application.port)

    def open(self):
        if self.request.host.split(":", 1)[0] not in ("127.0.0.1", "localhost"):
            self.close(1008, "Local connections only")
            return
        self.application.clients.add(self)
        self.write_message({"type": "connected", "actions": ACTIONS})

    async def on_message(self, message):
        request_id = None
        try:
            data = json.loads(message)
            if not isinstance(data, dict) or not isinstance(data.get("id"), str) or not isinstance(data.get("action"), str):
                raise ValueError("无效请求")
            request_id = data["id"]
            args = data.get("args", {})
            if not isinstance(args, dict):
                raise ValueError("参数必须为对象")
            result = await self.application.dispatch(data["action"], args)
            if self.ws_connection:
                await self.write_message({"type": "response", "id": request_id, "ok": True, "data": result})
        except Exception as exc:
            if not isinstance(exc, (ValueError, RuntimeError)):
                logging.exception("Request failed")
            if self.ws_connection:
                await self.write_message({"type": "response", "id": request_id, "ok": False, "error": str(exc) or "操作失败", 'task_id':getattr(exc,'task_id',None)})

    def on_close(self):
        self.application.clients.discard(self)


class StaticHandler(web.StaticFileHandler):
    def set_extra_headers(self, path):
        self.set_header("Cache-Control", "no-cache")


class PluginPreviewHandler(LocalHandler):
    async def post(self):
        try:
            files = self.request.files.get("file", [])
            if len(files) != 1:
                raise ValueError("请选择一个 ZIP 脚本包")
            result = await asyncio.to_thread(self.application.plugins.prepare, files[0]["body"])
            self.write({"ok": True, "data": result})
        except Exception as exc:
            self.set_status(400)
            self.write({"ok": False, "error": str(exc)})


class PluginExportHandler(LocalHandler):
    async def get(self):
        self.set_header("Content-Type", "application/zip")
        self.set_header("Content-Disposition", 'attachment; filename="photoshop-menu-actions.zip"')
        self.write(await asyncio.to_thread(self.application.plugins.export))


class UxpPreviewHandler(LocalHandler):
    async def post(self):
        try:
            files=self.request.files.get('file',[])
            if len(files)!=1:raise ValueError('请选择一个 UXP ZIP 更新包')
            result=await asyncio.to_thread(self.application.uxp.prepare,files[0]['body'])
            self.write({'ok':True,'data':result})
        except Exception as exc:
            self.set_status(400);self.write({'ok':False,'error':str(exc)})


class UxpExportHandler(LocalHandler):
    async def get(self):
        self.set_header('Content-Type','application/zip')
        self.set_header('Content-Disposition','attachment; filename="photoshop-menu-uxp.zip"')
        self.write(await asyncio.to_thread(self.application.uxp.export))


class Application(web.Application):
    def __init__(self, port, bridge=None, runtime=None):
        self.port = port
        self.runtime = Path(runtime) if runtime else runtime_dir()
        self.bridge = bridge or UxpBridge(task_history=self.runtime / 'task-history.json')
        self.tasks = getattr(self.bridge, 'tasks', None) or TaskStore()
        self.tasks.on_change = self.task_changed
        self.preferences = Settings(self.runtime / "settings.json")
        self.plugins = Plugins(self.runtime / "plugins", ROOT / "jsx")
        self.uxp=UxpManager(self.runtime,ROOT/'uxp/offline-probe')
        self.photoshop_launcher=PhotoshopLauncher(self.runtime,self.photoshop_start_ready)
        if isinstance(self.bridge,UxpBridge):self.bridge.execution_guard=self.require_uxp_enabled
        if bridge is None:
            self.bridge.replace_scripts(load_scripts(self.plugins.folder()))
        self.clients = set()
        self.stop_event = asyncio.Event()
        self.desktop = self.tray = None
        self.control = ControlWindow(f"http://127.0.0.1:{port}", self.runtime)
        self.panel_lock = asyncio.Lock()
        self.operation_lock = asyncio.Lock()
        self.recent_documents = RecentDocuments()
        super().__init__([
            (r"/websocket", WSHandler), (r"/api/health", HealthHandler),
            (r"/api/status", StatusHandler), (r"/api/service", ServiceHandler),
            (r"/api/tasks", TasksHandler),
            (r"/api/plugins/preview", PluginPreviewHandler), (r"/api/plugins/export", PluginExportHandler),
            (r"/api/uxp/preview", UxpPreviewHandler), (r"/api/uxp/export", UxpExportHandler),
            (r"/(.*)", StaticHandler, {"path": str(ROOT / "frontend/dist"), "default_filename": "index.html"}),
        ], websocket_max_message_size=65536, websocket_ping_interval=20, websocket_ping_timeout=20)

    async def broadcast(self, event):
        if self.desktop:
            self.desktop.event(event)
        for client in tuple(self.clients):
            try:
                await client.write_message(event)
            except websocket.WebSocketClosedError:
                self.clients.discard(client)

    def task_changed(self, task):
        # COM completion callbacks run on the asyncio thread. The read-only
        # task feed does not query Photoshop or wait on menu/window locks.
        try:loop=asyncio.get_running_loop()
        except RuntimeError:return
        async def publish():
            await self.broadcast({'type':'tasks', 'data':self.tasks.snapshot()})
            event = {'type':'operation', 'busy':self.bridge.busy,
                                  'task_id':task['id'], 'state':task['state'],
                                  'queue_ready':False,
                                  'queue_count':len(getattr(self.bridge,'_queue',[]))}
            if isinstance(self.bridge,PhotoshopBridge) and task['id']==self.bridge._active_task_id and task['state'] in ('capturing','running'):
                event['action']=task['action']
            await self.broadcast(event)
        loop.create_task(publish())

    def execution_contracts(self):
        contracts = command_contracts()
        if isinstance(self.bridge, UxpBridge):
            for item in contracts:
                if item['id']=='document.recent':
                    item['version']=3
                    continue
                item.update(channel='uxp-local-files', version=3,
                            target_document='captured-id; same-UXP-session; recheck-inside-modal',
                            cancellation='before-dispatch-only; submitted operation awaits UXP result')
        return contracts

    def require_uxp_enabled(self):
        if not self.uxp.enabled:raise RuntimeError('UXP 执行已禁用，请在后台插件管理中启用')

    async def photoshop_start_ready(self, started_at_ms):
        if not isinstance(self.bridge,UxpBridge):return True
        try:
            folder=await asyncio.to_thread(lambda:self.bridge.transport.folder)
            heartbeat=json.loads((folder/'probe-last.json').read_text('utf-8-sig'))
            return heartbeat.get('phase')=='ready' and int(heartbeat['session'].split('-')[0])>=started_at_ms
        except (OSError,ValueError,RuntimeError,KeyError):return False

    async def auto_start_photoshop(self):
        uxp=await asyncio.to_thread(self.uxp.status)
        if self.photoshop_launcher.auto_start and uxp['installed'] and uxp['enabled'] and not uxp['error']:
            try:return await self.dispatch('photoshop.start',{})
            except Exception as error:
                logging.warning('Automatic Photoshop start skipped: %s',error)
                return {'message':'插件已安装；自动启动未接受：'+str(error)}

    async def dispatch(self, action, args):
        if action=='language.set':
            save_language(self.runtime,args.get('language'))
            await self.broadcast({'type':'status','data':await self.dispatch('status',{})})
            return {'message':'界面语言已保存；PS 插件名称需关闭 PS 后应用','language':read_language(self.runtime)}
        if isinstance(self.bridge,UxpBridge) and action in ('plugin.install','plugin.rollback','plugin.uninstall'):
            raise ValueError('当前使用 UXP 执行端，旧 JSX 脚本包不能替换菜单操作')
        if action == "commands.list":
            return {"commands": Application.execution_contracts(self)}
        if action == 'tasks.list':
            return self.tasks.snapshot()
        if action == 'tasks.get':
            return self.tasks.get(args.get('id'))
        if action == 'tasks.cancel':
            return self.bridge.request_cancel(args.get('id'))
        if action == 'tasks.reconcile':
            if not isinstance(self.bridge,UxpBridge):raise ValueError('结果核对仅适用于 UXP 任务')
            result=await self.bridge.reconcile_result()
            await self.broadcast({'type':'status','data':await self.dispatch('status',{})})
            return {**result,'message':result.get('message','没有待核对的 UXP 任务')}
        if action=='photoshop.start':
            if self.operation_lock.locked() or self.bridge.busy or getattr(self.bridge,'_queue',[]):
                raise RuntimeError('请等待当前操作结束；启动请求未排队')
            async with self.operation_lock:
                uxp=await asyncio.to_thread(self.uxp.status)
                return await self.photoshop_launcher.start(uxp['installed'] and uxp['enabled'] and not uxp['error'])
        if action=='photoshop.autostart':
            result=self.photoshop_launcher.set_auto_start(args.get('enabled'))
            await self.broadcast({'type':'status','data':await self.dispatch('status',{})})
            return result
        if action=='uxp.status':return await asyncio.to_thread(self.uxp.status)
        if action in ('uxp.install','uxp.enable','uxp.disable','uxp.uninstall','uxp.rollback','uxp.apply-language'):
            if self.photoshop_launcher.active or self.operation_lock.locked() or self.bridge.busy or getattr(self.bridge,'_queue',[]):
                raise RuntimeError('请等待图层操作结束后再管理 UXP 插件；本次请求未排队')
            async with self.operation_lock:
                if action=='uxp.install':result=await asyncio.to_thread(self.uxp.install,args.get('token'),args.get('photoshop_exe') or None)
                elif action in ('uxp.enable','uxp.disable'):result=await asyncio.to_thread(self.uxp.set_enabled,action=='uxp.enable')
                elif action=='uxp.apply-language':result=await asyncio.to_thread(self.uxp.apply_language)
                else:result=await asyncio.to_thread(getattr(self.uxp,action.split('.')[1]))
            if action=='uxp.install':
                startup=await self.auto_start_photoshop()
                if startup:result['message']+='；'+startup['message']
            await self.broadcast({'type':'status','data':await self.dispatch('status',{})})
            return result
        if action == "status":
            status = await self.bridge.status(force=True) if args.get('refresh') and isinstance(self.bridge,PhotoshopBridge) else await self.bridge.status()
            uxp=await asyncio.to_thread(self.uxp.status)
            recent=await asyncio.to_thread(self.recent_documents.refresh,status.get('photoshop_version'))
            if isinstance(self.bridge,UxpBridge) and not uxp['enabled']:
                status={**status,'uxp_ready':False,'message':'UXP 执行已禁用'}
            return {"photoshop": status, "actions": ACTIONS, 'recent_documents':recent,
                    "commands": Application.execution_contracts(self),
                    'tasks':self.tasks.snapshot(), 'photoshop_start':self.photoshop_launcher.snapshot(),
                    'language':read_language(self.runtime),
                    "label_colors": LABEL_COLORS,
                    "version": APP_VERSION, "settings": self.preferences.get(), "plugin": self.plugins.status(), 'uxp':uxp,
                    "data_dir": str(self.runtime),
                    "service": service_identity(),
                    "menu": {"ready": bool(self.desktop and self.desktop.hwnd),
                             "hwnd": self.desktop.hwnd if self.desktop else None,
                             "pid": self.desktop.process.pid if self.desktop and self.desktop.process else None,
                             "renderer": "Dear ImGui / C++ / DirectX 11",
                             "visible": bool(self.desktop and self.desktop.visible),
                             "panel_context": self.desktop.panel_context.current if self.desktop and self.desktop.panel_context else {'kind': 'generic', 'label': '通用操作', 'source': 'fallback'},
                             "native_hotkeys": bool(self.desktop and self.desktop.native and self.desktop.native.poll() is None and self.desktop.ready.is_set()),
                             "hotkey_pid": self.desktop.native.pid if self.desktop and self.desktop.native else None},
                    "desktop": self.desktop.message if self.desktop else "无桌面模式",
                    "tray_error": self.tray.error if self.tray else ""}
        if action == 'document.new':
            if args.get('params') not in (None, {}):raise ValueError('新建窗口入口不接受文档参数')
            if not self.desktop:raise RuntimeError('无桌面模式不提供新建窗口')
            if self.photoshop_launcher.active or self.operation_lock.locked() or self.bridge.busy:
                raise RuntimeError('操作进行中，请等待完成后重新选择；本次操作未接受')
            async with self.operation_lock:
                async with self.panel_lock:
                    if 'menu_epoch' in args and args['menu_epoch'] != self.desktop.menu_epoch:
                        return {'message':'已忽略旧菜单操作'}
                    result = await asyncio.to_thread(self.desktop.new_document)
            logging.info('Homepage New dialog request: %s', result)
            return result
        if action == 'document.recent':
            if not self.desktop or not isinstance(self.bridge,UxpBridge):raise RuntimeError('最近预设新建需要 UXP 执行端')
            params=args.get('params',{})
            if not isinstance(params,dict) or set(params)!={'preset_id'}:raise ValueError('请选择一个最近预设')
            if self.photoshop_launcher.active or self.operation_lock.locked() or self.bridge.busy:
                raise RuntimeError('操作进行中，请等待完成后重新选择；本次操作未接受')
            async with self.operation_lock:
                async with self.panel_lock:
                    if 'menu_epoch' in args and args['menu_epoch']!=self.desktop.menu_epoch:return {'message':'已忽略旧菜单操作'}
                    await asyncio.to_thread(self.desktop.require_home)
                    preset=self.recent_documents.resolve(params['preset_id'])
                try:
                    await self.broadcast({'type':'operation','busy':True,'action':'document.recent'})
                    async def before_new(target):
                        async with self.panel_lock:
                            if 'menu_epoch' in args and args['menu_epoch']!=self.desktop.menu_epoch:raise TaskCancelled('菜单已重新打开，未创建文档')
                            await asyncio.to_thread(self.desktop.require_home)
                            if params['preset_id'].startswith('clipboard_'):
                                await asyncio.to_thread(self.recent_documents.resolve,params['preset_id'])
                            await asyncio.to_thread(self.desktop.hide)
                    result=await self.bridge.execute_recent(preset,before_new)
                    await self.broadcast({'type':'notice','scope':'operation','ok':True,'message':result['message']})
                    return result
                except Exception as error:
                    await self.broadcast({'type':'notice','scope':'operation','ok':False,'message':str(error)})
                    raise
                finally:
                    await self.broadcast({'type':'operation','busy':self.bridge.busy})
        if action == "action.execute":
            name = args.get("name")
            if name=='document.recent':raise ValueError('请从首页最近预设列表选择尺寸')
            validate_command(name, args.get("params"))
            if self.photoshop_launcher.active:raise RuntimeError('Photoshop 正在启动或结果待确认，请等待就绪后重新选择')
            if isinstance(self.bridge,UxpBridge):self.require_uxp_enabled()
            logging.info("Script action requested: %s", name)
            if not self.desktop:
                raise RuntimeError("无桌面模式不提供图层操作")
            await asyncio.to_thread(self.desktop.require_action_focus)
            if self.operation_lock.locked() or self.bridge.busy:
                raise RuntimeError("操作进行中，请等待完成后重新选择；本次操作未接受")
            try:
                async with self.operation_lock:
                    async with self.panel_lock:
                        if 'menu_epoch' in args and args['menu_epoch'] != self.desktop.menu_epoch:
                            return {"message":"已忽略旧菜单操作"}
                        frozen_target=None
                        snapshot=getattr(self.desktop,'menu_layer_context',None)
                        if isinstance(self.bridge,UxpBridge) and 'menu_epoch' in args and snapshot and len(snapshot.get('layer_ids',[]))==1:
                            frozen_target={key:snapshot.get(key) for key in ('session','document_id','layer_ids')}
                            frozen_target['active_layer_id']=snapshot['layer_ids'][0]
                    # Target reads can also wait for Photoshop; show busy
                    # feedback before entering COM, not just before writing.
                    if not self.bridge.busy:
                        await self.broadcast({"type": "operation", "busy": True, "action": name})
                    async def before_dispatch(target):
                        async with self.panel_lock:
                            if 'menu_epoch' in args and args['menu_epoch'] != self.desktop.menu_epoch:
                                raise TaskCancelled('菜单已重新打开，已取消旧操作')
                            if 'menu_epoch' in args and hasattr(self.desktop,'require_menu_layer_target'):
                                await asyncio.to_thread(self.desktop.require_menu_layer_target,name,target)
                            await asyncio.to_thread(self.desktop.hide)
                    # Capture before hiding; the PS-side check and write
                    # share one JSX call on the original COM connection.
                    if frozen_target is not None:
                        result=await self.bridge.execute(name,before_dispatch=before_dispatch,frozen_target=frozen_target)
                    else:result = await self.bridge.execute(name, before_dispatch=before_dispatch)
                    if isinstance(self.bridge,UxpBridge):
                        self.desktop.layer_context=dict(self.bridge.layer_context)
                logging.info("Script action completed: %s", name)
                await self.broadcast({"type": "notice", "scope": "operation", "action": name, "ok": True, "message": result["message"]})
                return result
            except TaskCancelled as exc:
                await self.broadcast({"type":"notice", "scope":"operation", "action":name,
                                      "ok":True, "message":str(exc)})
                return {'message':str(exc), 'task_id':getattr(exc,'task_id',None),'cancelled':True}
            except Exception as exc:
                await self.broadcast({"type": "notice", "scope": "operation", "action": name, "ok": False, "message": str(exc)})
                raise
            finally:
                if isinstance(self.bridge,PhotoshopBridge):
                    await self.broadcast({'type':'operation','busy':self.bridge.busy,'queue_ready':False,'queue_count':len(self.bridge._queue)})
                else:await self.broadcast({"type": "operation", "busy": self.bridge.busy})
        if action in ("panel.open", "panel.context", "panel.hide", "panel.toggle", "panel.dismiss", "panel.hold_begin", "panel.hold_release", "panel.hold_cancel", "panel.hold_pin"):
            if not self.desktop:
                return {"message": "当前运行在无桌面模式"}
            async with self.panel_lock:
                if 'menu_epoch' in args and args['menu_epoch'] != self.desktop.menu_epoch:
                    return {"message":"已忽略旧菜单事件"}
                if action in ("panel.open","panel.context") or action=="panel.toggle" and not self.desktop.visible:
                    await self.broadcast({"type":"popup.prepare","mode":"context" if action=="panel.context" else "quick"})
                if action=="panel.hold_release" and 'cursor' in args:
                    cursor=args['cursor']
                    if not isinstance(cursor,list) or len(cursor)!=2 or any(type(v) is not int or not -2147483648<=v<=2147483647 for v in cursor):
                        raise ValueError('无效的松键鼠标坐标')
                    return await asyncio.to_thread(self.desktop.hold_release,cursor=cursor)
                return await asyncio.to_thread(getattr(self.desktop, action.split(".")[1]))
        if action == "overlay.ready":
            if not self.desktop:
                raise RuntimeError("原生菜单未启动")
            self.desktop.attach(args.get("hwnd"), args.get("pid"), args.get("token"))
            return await self.dispatch("status", {})
        if action == "control.open":
            async with self.panel_lock:
                return await asyncio.to_thread(self.control.open)
        if action == "settings.save":
            previous_url = self.preferences.data["update_url"]
            data = self.preferences.save(args.get("settings"))
            if data["update_url"] != previous_url:
                self.plugins.update = None
            if self.desktop:
                self.desktop.apply_settings(data)
            await self.broadcast({"type": "status", "data": await self.dispatch("status", {})})
            return {"message": "设置已保存并生效", "settings": data}
        if action == "logs.read":
            path = self.runtime / "service.log"
            if not path.exists():
                return {"text": "暂无日志"}
            with path.open("rb") as log:
                log.seek(0, 2)
                log.seek(max(0, log.tell()-65536))
                return {"text": "\n".join(log.read().decode("utf-8", errors="replace").splitlines()[-200:])}
        if action == "plugin.check":
            return await self.plugins.check(self.preferences.data["update_url"])
        if action == "plugin.download":
            return await self.plugins.download()
        if action in ("plugin.install", "plugin.rollback", "plugin.uninstall"):
            if self.operation_lock.locked() or self.bridge.busy or getattr(self.bridge,"_queue",[]):
                raise RuntimeError("请等待图层操作完成后再更换脚本包")
            async with self.operation_lock:
                if action == "plugin.install":
                    scripts = load_scripts(self.plugins.prepared_folder(args.get("token")))
                    result = await asyncio.to_thread(self.plugins.install, args.get("token"))
                else:
                    result = await asyncio.to_thread(self.plugins.restore, action == "plugin.uninstall")
                    scripts = load_scripts(self.plugins.folder())
                self.bridge.replace_scripts(scripts)
            await self.broadcast({"type": "status", "data": await self.dispatch("status", {})})
            return {"message": "脚本包已切换并生效", "plugin": result}
        if action == "service.quit":
            # Let the response reach the browser before closing sockets.
            asyncio.get_running_loop().call_later(.2, self.stop_event.set)
            return {"message": "服务正在退出"}
        raise ValueError("未知动作")


async def reuse(port, headless):
    client = AsyncHTTPClient()
    response = await client.fetch(f"http://127.0.0.1:{port}/api/health", request_timeout=2)
    health = json.loads(response.body)
    if health.get("app") != APP_ID:
        raise RuntimeError(f"端口 {port} 已被其他服务占用")
    running_version = health.get("version")
    if not running_version:
        # Older releases did not include a version in the health response.
        response = await client.fetch(f"http://127.0.0.1:{port}/api/status", request_timeout=3)
        running_version = json.loads(response.body).get("version")
    if running_version != APP_VERSION:
        raise RuntimeError(f"启动的是 v{APP_VERSION}，端口 {port} 正在运行 v{running_version or '未知'}。"
                           "请先通过托盘或后台管理退出旧服务，等待退出完成后再打开此版本；本次未切换版本。")
    if not headless:
        await client.fetch(HTTPRequest(f"http://127.0.0.1:{port}/api/service", method="POST",
                          headers={"Content-Type": "application/json"}, body=json.dumps({"action": "open"}), request_timeout=12))
    print(f"已复用运行中的 Photoshop Menu v{running_version}：http://127.0.0.1:{port}")


async def run(port=15151, headless=False, no_desktop=False, runtime=None):
    if not (ROOT / "frontend/dist/index.html").is_file():
        raise RuntimeError("缺少前端构建，请在 frontend 中运行 npm install 和 npm run build")
    app = Application(port, runtime=runtime)
    try:
        server = app.listen(port, address="127.0.0.1", max_buffer_size=MAX_PACKAGE + 65536)
    except OSError:
        await app.bridge.close()
        await reuse(port, headless)
        return
    loop = asyncio.get_running_loop()
    async def notification(action):
        try:
            event_args = {}
            if isinstance(action, dict):
                event_args = {key:action[key] for key in ('menu_epoch','cursor') if key in action}
                action = action['action']
                if 'menu_epoch' in event_args and (not app.desktop or event_args['menu_epoch'] != app.desktop.menu_epoch):
                    return
            mapping = {"toggle": "panel.toggle", "context": "panel.context", "open": "panel.open", "hide": "panel.hide", "dismiss": "panel.dismiss", "hold_begin": "panel.hold_begin", "hold_release": "panel.hold_release", "hold_cancel": "panel.hold_cancel", "control": "control.open", "quit": "service.quit"}
            mapping['hold_pin'] = 'panel.hold_pin'
            mapping['document.new'] = 'document.new'
            if action.startswith('document.recent.'):
                event_args['params']={'preset_id':action.removeprefix('document.recent.')}
                action='document.recent'
                mapping[action]=action
            await app.dispatch(mapping.get(action, "action.execute"), event_args if action in mapping else {**event_args,"name": action})
        except Exception as exc:
            logging.exception("Desktop action failed")
            await app.broadcast({"type": "notice", "scope": "interaction", "ok": False, "message": str(exc)})
    def notify(action):
        loop.call_soon_threadsafe(lambda: asyncio.create_task(notification(action)))
    async def poll_status():
        while not app.stop_event.is_set():
            await app.broadcast({"type": "status", "data": await app.dispatch("status", {})})
            await asyncio.to_thread(app.control.refresh_icon)
            try:
                await asyncio.wait_for(app.stop_event.wait(), 3)
            except asyncio.TimeoutError:
                pass
    status_task = None
    try:
        if os.name == "nt" and not no_desktop:
            app.desktop, app.tray = Desktop(f"http://127.0.0.1:{port}", notify, app.preferences.get(), app.runtime), Tray(notify)
            app.bridge.focus_guard = app.desktop.require_action_focus
            if isinstance(app.bridge,UxpBridge):app.bridge.document_guard=app.desktop.require_home
            if isinstance(app.bridge,UxpBridge):app.desktop.layer_context_provider=app.bridge.read_layer_context
            await asyncio.to_thread(app.desktop.start)
            await asyncio.to_thread(app.tray.start)
            if app.tray.error:
                logging.error("Tray: %s", app.tray.error)
            uxp_install=await asyncio.to_thread(app.uxp.status)
            if not headless and (app.preferences.data["open_control_on_start"] or
                                 isinstance(app.bridge,UxpBridge) and (not uxp_install['installed'] or uxp_install['error'])):
                await app.dispatch("control.open", {})
        status_task = asyncio.create_task(poll_status())
        await app.photoshop_launcher.resume()
        if not headless and not no_desktop and not app.photoshop_launcher.active:
            await app.auto_start_photoshop()
        print(f"Photoshop Menu：http://127.0.0.1:{port}", flush=True)
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: loop.call_soon_threadsafe(app.stop_event.set))
        await app.stop_event.wait()
    finally:
        if status_task:
            status_task.cancel()
            await asyncio.gather(status_task, return_exceptions=True)
        server.stop()
        for client in tuple(app.clients):
            client.close()
        if app.desktop:
            await asyncio.to_thread(app.desktop.close)
        if app.tray:
            await asyncio.to_thread(app.tray.close)
        await asyncio.to_thread(app.control.close)
        await app.photoshop_launcher.close()
        await app.bridge.close()


def cli():
    parser = argparse.ArgumentParser(description="Photoshop Menu 本地应用")
    parser.add_argument("--port", type=int, default=15151)
    parser.add_argument("--headless", action="store_true", help="启动后台且不自动打开管理窗口")
    parser.add_argument("--no-desktop", action="store_true", help="禁用窗口、快捷键和托盘")
    parser.add_argument("--data-dir", type=Path, help="自定义设置、插件和日志存储目录")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("端口必须为 1–65535")
    runtime = args.data_dir.resolve() if args.data_dir else runtime_dir()
    runtime.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(runtime / "service.log", maxBytes=1024*1024, backupCount=3, encoding="utf-8")
    logging.basicConfig(handlers=[handler], level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        asyncio.run(run(args.port, args.headless, args.no_desktop, runtime))
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        logging.exception("Startup failed")
        if os.name == "nt" and getattr(sys, "frozen", False) and not args.headless:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, str(exc), "Photoshop Menu — 启动失败", 0x10)
        raise SystemExit(str(exc)) from exc
