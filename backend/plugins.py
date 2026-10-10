"""Versioned JSX packages: preview, atomic activation, rollback, update feed."""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import uuid
import zipfile
from urllib.parse import urlparse
from tornado.httpclient import AsyncHTTPClient, HTTPRequest
from .settings import atomic_json

PLUGIN_ID = "photoshop-menu-actions"
FILES = ("select_all_layer_in_group.jsx", "color_orange.jsx", "move_to_top_or_bottom.jsx")
MAX_PACKAGE = 5 * 1024 * 1024


def version(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d+\.\d+\.\d+", value):
        raise ValueError("版本必须为 major.minor.patch")
    return tuple(map(int, value.split(".")))


def manifest(folder):
    data = json.loads((Path(folder) / "manifest.json").read_text(encoding="utf-8"))
    if data.get("id") != PLUGIN_ID or data.get("api_version") != 1:
        raise ValueError("不是兼容的 Photoshop Menu 脚本包")
    version(data.get("version"))
    if not isinstance(data.get("sha256"), dict) or set(data["sha256"]) != set(FILES):
        raise ValueError("脚本包文件清单不完整")
    for name in FILES:
        content = (Path(folder) / name).read_bytes()
        if not content or hashlib.sha256(content).hexdigest() != data["sha256"][name]:
            raise ValueError("脚本校验失败：" + name)
        content.decode("utf-8")
    if (Path(folder) / FILES[2]).read_text(encoding="utf-8").count("/*%Bool%*/") != 1:
        raise ValueError("移动脚本缺少唯一的方向参数标记")
    return data


class Plugins:
    def __init__(self, root, builtin):
        self.root, self.builtin = Path(root), Path(builtin)
        self.root.mkdir(parents=True, exist_ok=True)
        self.state_path = self.root / "state.json"
        self.state = json.loads(self.state_path.read_text(encoding="utf-8")) if self.state_path.exists() else {"active": "builtin", "history": []}
        self.update = None
        manifest(self.folder())

    def folder(self, token=None):
        token = token or self.state["active"]
        if token == "builtin":
            return self.builtin
        if not re.fullmatch(r"[a-f0-9]{32}", token):
            raise ValueError("无效的脚本包标识")
        return self.root / "versions" / token

    def status(self):
        return {"active": manifest(self.folder()), "builtin": manifest(self.builtin)["version"],
                "installed": self.state["active"] != "builtin", "can_rollback": bool(self.state["history"]),
                "update": self.update}

    def prepare(self, payload):
        if not payload or len(payload) > MAX_PACKAGE:
            raise ValueError("脚本包必须小于 5 MiB")
        token = uuid.uuid4().hex
        folder = self.root / "staging" / token
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                names = archive.namelist()
                if len(names) != 4 or set(names) != {"manifest.json", *FILES}:
                    raise ValueError("ZIP 必须只包含 manifest.json 和三个指定的 JSX 文件")
                if sum(info.file_size for info in archive.infolist()) > MAX_PACKAGE:
                    raise ValueError("解压后的脚本包过大")
                folder.mkdir(parents=True)
                for info in archive.infolist():
                    if (info.external_attr >> 16) & 0o170000 == 0o120000:
                        raise ValueError("脚本包不能包含符号链接")
                    (folder / info.filename).write_bytes(archive.read(info))
            data = manifest(folder)
            if version(data["version"]) <= version(manifest(self.folder())["version"]):
                raise ValueError("升级包版本必须高于当前版本；恢复旧版请使用回滚")
            return {"token": token, "manifest": data, "message": "脚本包校验通过，等待安装"}
        except Exception:
            if folder.exists():
                shutil.rmtree(folder)
            raise

    def prepared_folder(self, token):
        if not isinstance(token, str) or not re.fullmatch(r"[a-f0-9]{32}", token):
            raise ValueError("无效的安装预览")
        return self.root / "staging" / token

    def install(self, token):
        folder = self.prepared_folder(token)
        data = manifest(folder)
        if version(data["version"]) <= version(manifest(self.folder())["version"]):
            raise ValueError("升级包版本已过期，请重新预览")
        destination = self.folder(token)
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(folder, destination)
        new = {"active": token, "history": self.state["history"] + [self.state["active"]]}
        atomic_json(self.state_path, new)
        self.state = new
        self.update = None
        return self.status()

    def restore(self, builtin=False):
        if builtin:
            target = "builtin"
            history = self.state["history"] + [self.state["active"]] if self.state["active"] != target else self.state["history"]
        else:
            if not self.state["history"]:
                raise ValueError("没有可回滚版本")
            target, history = self.state["history"][-1], self.state["history"][:-1]
        manifest(self.folder(target))
        new = {"active": target, "history": history}
        atomic_json(self.state_path, new)
        self.state = new
        self.update = None
        return self.status()

    def export(self):
        folder = self.folder()
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
            for name in ("manifest.json", *FILES):
                archive.write(folder / name, name)
        return stream.getvalue()

    async def check(self, url):
        if not url:
            raise ValueError("请先在设置中填写更新清单 HTTPS 地址")
        client = AsyncHTTPClient(force_instance=True, max_body_size=MAX_PACKAGE)
        try:
            response = await client.fetch(HTTPRequest(url, request_timeout=15, follow_redirects=False))
            data = json.loads(response.body)
            if data.get("id") != PLUGIN_ID:
                raise ValueError("更新清单的插件 ID 不匹配")
            version(data.get("version"))
            parsed = urlparse(data.get("url", ""))
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("更新包必须使用 HTTPS 地址")
            if not isinstance(data.get("sha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", data["sha256"]):
                raise ValueError("更新清单缺少 SHA256")
            self.update = {**data, "available": version(data["version"]) > version(manifest(self.folder())["version"])}
            return self.update
        finally:
            client.close()

    async def download(self):
        if not self.update or not self.update["available"]:
            raise ValueError("请先检查可用更新")
        update = dict(self.update)
        client = AsyncHTTPClient(force_instance=True, max_body_size=MAX_PACKAGE)
        try:
            response = await client.fetch(HTTPRequest(update["url"], request_timeout=30, follow_redirects=False))
            if hashlib.sha256(response.body).hexdigest() != update["sha256"]:
                raise ValueError("更新包 SHA256 不匹配")
            preview = self.prepare(response.body)
            if preview["manifest"]["version"] != update["version"]:
                raise ValueError("更新包版本与清单不匹配")
            return preview
        finally:
            client.close()
