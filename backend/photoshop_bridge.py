"""Serial Photoshop COM calls on one dedicated apartment thread."""
import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from .paths import ROOT
from .layer_labels import LABEL_ACTIONS, label_script
from .photoshop_theme import read_theme, read_font_size

ACTIONS = {
    "select": {"label": "选择组内图层", "shortcut": "CapsLock+A"},
    "color": {"label": "橙色图层标签", "shortcut": "CapsLock+C"},
    "moveToTop": {"label": "移到顶部", "shortcut": "CapsLock+W"},
    "moveToBottom": {"label": "移到底部", "shortcut": "CapsLock+S"},
}
COMMANDS = {**ACTIONS, **LABEL_ACTIONS}


def load_scripts(folder=None):
    from photoshop_action.baseJsxInit import jsxFilesBooleanStr
    folder = Path(folder) if folder else ROOT / "jsx"
    move = (folder / "move_to_top_or_bottom.jsx").read_text(encoding="utf-8")
    return {"select": (folder / "select_all_layer_in_group.jsx").read_text(encoding="utf-8"),
            "color": (folder / "color_orange.jsx").read_text(encoding="utf-8"), "moveToTop": jsxFilesBooleanStr(move, True),
            "moveToBottom": jsxFilesBooleanStr(move, False)}


class PhotoshopBridge:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="photoshop-com")
        self.scripts = load_scripts()
        self.initialized = self.busy = self.closed = False
        self.last_error = ""
        self.focus_guard = None
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

    def _execute(self, action):
        if self.focus_guard:
            self.focus_guard()
        app = self._application()
        if not app.Documents.Count:
            raise ValueError("请先在 Photoshop 中打开文档")
        script = label_script(action) if action in LABEL_ACTIONS else self.scripts[action]
        return app.DoJavaScript(script)

    async def execute(self, action):
        if action not in COMMANDS:
            raise ValueError("未知的图层操作")
        if self.closed:
            raise RuntimeError("服务正在退出")
        if self.busy:
            raise RuntimeError("上一项操作尚未完成，请稍后再试")
        self.busy = True
        future = asyncio.get_running_loop().run_in_executor(self.executor, self._execute, action)
        def finished(completed):
            self.busy = False
            error = completed.exception() if not completed.cancelled() else None
            self.last_error = str(error) if error else ""
        future.add_done_callback(finished)
        try:
            result = await asyncio.wait_for(asyncio.shield(future), 45)
            message = COMMANDS[action]["label"] + "已完成"
            if action == 'label.none':
                details = json.loads(result)
                message = f"已清除 {details['count']} 个图层的标签，并核验为无颜色"
                if details.get('inherited'):
                    message += "；父组仍有颜色标签，图层面板可能继续显示父组颜色"
            return {"message": message, "result": str(result or "")}
        except asyncio.TimeoutError:
            raise RuntimeError("操作超时，结果尚未确定；请检查 Photoshop，避免重复操作") from None
        except (ValueError, RuntimeError):
            raise
        except Exception as exc:
            raise RuntimeError("Photoshop 执行失败：" + str(exc)) from exc

    def replace_scripts(self, scripts):
        if self.busy or self.closed:
            raise RuntimeError("请等待图层操作完成后再更换脚本包")
        self.scripts = dict(scripts)

    def _release(self):
        if self.initialized:
            import pythoncom
            pythoncom.CoUninitialize()
            self.initialized = False

    async def close(self):
        self.closed = True
        await asyncio.get_running_loop().run_in_executor(self.executor, self._release)
        self.executor.shutdown(wait=False)
