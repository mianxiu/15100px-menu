"""Serial Photoshop COM calls on one dedicated apartment thread."""
import asyncio
import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from .paths import ROOT
from .layer_labels import LABEL_ACTIONS, label_script
from .photoshop_theme import read_theme, read_font_size
from .commands import ACTIONS, COMMANDS, validate_command
from .operation_target import CAPTURE_SCRIPT, validate_target, guarded_script
from .tasks import TaskStore, TaskCancelled


def load_scripts(folder=None):
    from photoshop_action.baseJsxInit import jsxFilesBooleanStr
    folder = Path(folder) if folder else ROOT / "jsx"
    move = (folder / "move_to_top_or_bottom.jsx").read_text(encoding="utf-8")
    return {"select": (folder / "select_all_layer_in_group.jsx").read_text(encoding="utf-8"),
            "color": (folder / "color_orange.jsx").read_text(encoding="utf-8"), "moveToTop": jsxFilesBooleanStr(move, True),
            "moveToBottom": jsxFilesBooleanStr(move, False)}


class PhotoshopBridge:
    def __init__(self, task_history=None):
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="photoshop-com")
        self.scripts = load_scripts()
        self.initialized = self.busy = self.closed = False
        self.last_error = ""
        self.focus_guard = None
        self.tasks = TaskStore(path=task_history)
        self.operation_timeout = 45
        self._captured_app = self._captured_target = None
        self.ui_theme = 'dark'
        self.ui_font_size = 'small'
        self.cached_status = {'connected': False, 'document': None, 'message': '检查 Photoshop 中'}

    def _application(self):
        import pythoncom
        import win32com.client
        if not self.initialized:
            pythoncom.CoInitialize()
            self.initialized = True
        # Attach only: do not launch Photoshop implicitly.
        return win32com.client.GetActiveObject("Photoshop.Application")

    def _status(self):
        try:
            app = self._application()
            count = int(app.Documents.Count)
            self.ui_theme = read_theme(app, self.ui_theme)
            self.ui_font_size = read_font_size(app, self.ui_font_size)
            return {"connected": True, "ui_theme": self.ui_theme, "ui_font_size": self.ui_font_size, "document": str(app.ActiveDocument.Name) if count else None,
                    "message": "已连接 Photoshop" if count else "Photoshop 尚未打开文档"}
        except Exception:
            return {"connected": False, "ui_theme": self.ui_theme, "ui_font_size": self.ui_font_size, "document": None, "message": "请先启动 Photoshop"}

    async def status(self):
        if self.busy:
            return {**self.cached_status, "busy": True, "message": "Photoshop 正在执行操作", "last_error": self.last_error}
        result = await asyncio.get_running_loop().run_in_executor(self.executor, self._status)
        self.cached_status = dict(result)
        return {**result, "busy": self.busy, "last_error": self.last_error}

    def _capture_target(self):
        if self.focus_guard:
            self.focus_guard()
        app = self._application()
        if not app.Documents.Count:
            raise ValueError("请先在 Photoshop 中打开文档")
        target = validate_target(json.loads(app.DoJavaScript(CAPTURE_SCRIPT)))
        # This COM reference is retained and used on the same apartment thread;
        # never reconnect to a new Photoshop instance between capture and write.
        self._captured_app, self._captured_target = app, target
        return {**target, 'instance_binding':uuid.uuid4().hex}

    def _execute(self, action):
        if self.focus_guard:
            self.focus_guard()
        app, target = self._captured_app, self._captured_target
        if app is None or target is None:
            raise RuntimeError('未固定操作目标，操作已取消')
        script = label_script(action) if action in LABEL_ACTIONS else self.scripts[action]
        return app.DoJavaScript(guarded_script(script, target))

    async def execute(self, action, before_dispatch=None):
        command = validate_command(action)
        if self.closed:
            raise RuntimeError("服务正在退出")
        if self.busy:
            raise RuntimeError("上一项操作尚未完成，请稍后再试")
        self.busy = True
        task_id = self.tasks.create(action, command.label)
        future = None
        dispatched = False
        def finished(completed):
            self.busy = False
            error = completed.exception() if not completed.cancelled() else None
            if dispatched:
                try:
                    if error:raise error
                    message = self._result_message(action, completed.result())
                    self.tasks.update(task_id, 'succeeded', message=message, error='')
                except Exception as exc:
                    error = exc
                    self.tasks.update(task_id, 'failed', error=str(exc))
            else:
                self.tasks.update(task_id, 'failed' if error else 'cancelled',
                                  message='目标读取已结束，未提交修改', error=str(error or ''))
            self.last_error = str(error) if error else ""
        try:
            await self.tasks.flush()
            future = asyncio.get_running_loop().run_in_executor(self.executor, self._capture_target)
            target = await asyncio.wait_for(asyncio.shield(future), self.operation_timeout)
            self.tasks.update(task_id, 'capturing', target=target)
            logging.info('Operation target captured: action=%s target=%s', action, target)
            self.tasks.update(task_id, 'running')
            await self.tasks.flush()
            # Recheck the menu session after the durable-write wait, so opening
            # a new menu while disk I/O completes cancels the old operation.
            if before_dispatch:
                await before_dispatch(target)
            future = asyncio.get_running_loop().run_in_executor(self.executor, self._execute, action)
            dispatched = True
            future.add_done_callback(finished)
            result = await asyncio.wait_for(asyncio.shield(future), self.operation_timeout)
            return {"message": self._result_message(action,result), "result": str(result or ""), "target":target, 'task_id':task_id}
        except asyncio.TimeoutError:
            if not dispatched:
                message='目标读取超时，未执行操作'
                self.tasks.update(task_id,'cancel-requested',error=message)
            else:
                message='操作超时，结果尚未确定；请检查 Photoshop，避免重复操作'
                if self.tasks.get(task_id)['state']=='running':
                    self.tasks.update(task_id,'result-unknown',error=message,wait_error=message)
            error=RuntimeError(message);error.task_id=task_id
            raise error from None
        except asyncio.CancelledError:
            if self.tasks.get(task_id)['state'] in ('capturing','running'):
                self.tasks.update(task_id,'result-unknown' if dispatched else 'cancel-requested',
                                  message='等待已取消；已提交的 COM 操作不能强制中断' if dispatched else '等待已取消，未提交修改')
            raise
        except (ValueError, RuntimeError) as exc:
            if not dispatched:self.tasks.update(task_id,'cancelled' if isinstance(exc,TaskCancelled) else 'failed',error=str(exc))
            exc.task_id=task_id
            raise
        except Exception as exc:
            if not dispatched:self.tasks.update(task_id,'failed',error=str(exc))
            error=RuntimeError("Photoshop 执行失败：" + str(exc));error.task_id=task_id
            raise error from exc
        finally:
            if not dispatched:
                if future is not None and not future.done():
                    future.add_done_callback(finished)
                else:
                    self.busy = False
                    if self.tasks.get(task_id)['state']=='cancel-requested':
                        self.tasks.update(task_id,'cancelled',message='目标读取已结束，未提交修改')

    def _result_message(self, action, result):
        message = validate_command(action).label + '已完成'
        if action == 'label.none':
            details = json.loads(result)
            message = f"已清除 {details['count']} 个图层的标签，并核验为无颜色"
            if details.get('inherited'):
                message += '；父组仍有颜色标签，图层面板可能继续显示父组颜色'
        return message

    def replace_scripts(self, scripts):
        if self.busy or self.closed:
            raise RuntimeError("请等待图层操作完成后再更换脚本包")
        self.scripts = dict(scripts)

    def _release(self):
        self._captured_app = self._captured_target = None
        if self.initialized:
            import pythoncom
            pythoncom.CoUninitialize()
            self.initialized = False

    async def close(self):
        self.closed = True
        await asyncio.get_running_loop().run_in_executor(self.executor, self._release)
        self.executor.shutdown(wait=False)
        await self.tasks.close()
