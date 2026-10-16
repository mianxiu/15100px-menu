"""Public GitHub Releases updates, separate from the legacy JSX updater.

Network and ZIP work runs off the event loop. Checking never downloads or
installs. Installation is explicitly requested and uses a separate process;
Photoshop operations are neither cancelled nor replayed.
"""
import asyncio
import copy
from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import uuid
import zipfile

from .settings import atomic_json
from .version import APP_VERSION

REPO = 'mianxiu/15100px-menu'
API = 'https://api.github.com/repos/' + REPO + '/releases/latest'
RELEASES = 'https://github.com/' + REPO + '/releases'
MANIFEST = RELEASES+'/latest/download/PhotoshopMenu-update.json'
MAX_DOWNLOAD = 128 * 1024 * 1024
CHECK_INTERVAL = 24 * 60 * 60
HASH = re.compile(r'[0-9a-f]{64}')


def version(value):
    if not isinstance(value, str) or not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', value):
        raise ValueError('发行版本号无效')
    parts = tuple(map(int, value.split('.')))
    if any(part > 65535 for part in parts):raise ValueError('发行版本号无效')
    return parts


def sha256(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024), b''):result.update(chunk)
    return result.hexdigest()


def release_url(tag, name):
    return f'https://github.com/{REPO}/releases/download/{tag}/{name}'


class ReleaseRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        parsed = urlsplit(newurl)
        if (parsed.scheme != 'https' or parsed.hostname not in
            ('github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com') or
            parsed.username or parsed.password or parsed.port not in (None,443)):
            raise ValueError('更新下载重定向地址不受信任')
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def opener():
    # urllib uses the configured system/environment proxy, never a bundled proxy
    # or Git credential. All endpoints are public and no token is requested.
    return build_opener(ReleaseRedirects())


def update_error(error):
    """Actionable network messages; retain HTTPS/certificate verification."""
    reason=error.reason if isinstance(error,URLError) else error
    if isinstance(reason,ssl.SSLCertVerificationError):
        return 'GitHub HTTPS证书校验失败，请检查系统日期、Windows根证书及代理的证书配置'
    if isinstance(reason,ssl.SSLError) or 'SSL' in str(reason).upper():
        return 'GitHub HTTPS连接失败（SSL），请检查代理或网络拦截；也可从GitHub Releases手动下载'
    if isinstance(reason,(TimeoutError,socket.timeout)):
        return '连接GitHub超时，请检查网络及系统代理，稍后重试'
    if isinstance(reason,socket.gaierror):
        return '无法解析GitHub地址，请检查网络、DNS及系统代理'
    if isinstance(error,URLError) and not isinstance(error,HTTPError):
        return '无法连接GitHub，请检查网络及系统代理；也可从GitHub Releases手动下载'
    return str(error)[:600]


def select_release(data, current):
    if not isinstance(data, dict) or data.get('draft') is not False or data.get('prerelease') is not False:
        raise ValueError('只接受已发布的正式版本')
    tag = data.get('tag_name','')
    v = tag.removeprefix('v')
    version(v); version(current)
    if tag != 'v'+v or type(data.get('id')) is not int or data['id'] <= 0:
        raise ValueError('发行记录无效')
    name = 'PhotoshopMenu-Backend-'+v+'.zip'
    assets = data.get('assets')
    if not isinstance(assets,list):raise ValueError('发行附件无效')
    result = {'version':v,'tag':tag,'id':data['id'],'url':RELEASES+'/tag/'+tag,
              'available':version(v)>version(current), 'notes':str(data.get('body') or '')[:8000]}
    for key, filename, limit in (('asset',name,MAX_DOWNLOAD),('checksum',name+'.sha256',4096)):
        matches = [a for a in assets if isinstance(a,dict) and a.get('name')==filename]
        if len(matches)!=1:raise ValueError('正式版本缺少唯一的统一安装包或校验文件')
        item=matches[0]
        if (item.get('state')!='uploaded' or type(item.get('id')) is not int or item['id']<=0 or
            type(item.get('size')) is not int or not 0<item['size']<=limit or
            item.get('browser_download_url')!=release_url(tag,filename)):
            raise ValueError('发行附件身份或大小无效')
        digest=item.get('digest')
        if digest is not None and not re.fullmatch(r'sha256:[0-9a-f]{64}',digest):
            raise ValueError('发行附件摘要无效')
        result[key] = {'id':item['id'],'name':filename,'size':item['size'],
                       'url':item['browser_download_url'],'digest':digest}
    return result


def parse_checksum(body, name):
    match = re.fullmatch(rb'([0-9a-fA-F]{64}) [ *]'+re.escape(name.encode('ascii'))+rb'\r?\n?', body)
    if not match:raise ValueError('SHA256 校验文件内容无效')
    return match[1].decode('ascii').lower()


def executable_version(path):
    import win32api
    info=win32api.GetFileVersionInfo(str(path),'\\')
    result=(info['FileVersionMS']>>16,info['FileVersionMS']&65535,info['FileVersionLS']>>16)
    if info['FileVersionLS']&65535:raise ValueError('应用版本资源无效')
    for table in info.get('Translation',[]) or win32api.GetFileVersionInfo(str(path),'\\VarFileInfo\\Translation'):
        prefix=f'\\StringFileInfo\\{table[0]:04x}{table[1]:04x}\\'
        if (win32api.GetFileVersionInfo(str(path),prefix+'OriginalFilename')=='PhotoshopMenu.exe' and
            win32api.GetFileVersionInfo(str(path),prefix+'ProductName')=='Photoshop Menu'):
            return '.'.join(map(str,result))
    raise ValueError('安装包不是 Photoshop Menu 应用')


def unpack_package(package, folder, expected_version, expected_sha):
    """Validate all entries, but extract only the EXE; no ZIP-supplied installer."""
    if sha256(package)!=expected_sha:raise ValueError('统一安装包 SHA256 不匹配')
    destination=Path(folder)/'PhotoshopMenu.exe'
    with zipfile.ZipFile(package) as bundle:
        entries=bundle.infolist();names=[item.filename for item in entries]
        if len(entries)>150 or len(names)!=len({n.casefold() for n in names}) or sum(i.file_size for i in entries)>256*1024*1024:
            raise ValueError('安装包结构或解压大小无效')
        for item in entries:
            p=PurePosixPath(item.filename)
            if (not item.filename or chr(0) in item.orig_filename or chr(92) in item.orig_filename or ':' in item.filename or p.is_absolute() or
                '..' in p.parts or item.flag_bits&1 or (item.external_attr>>16)&0o170000==0o120000):
                raise ValueError('安装包包含不安全路径或文件')
        if not {'PhotoshopMenu.exe','PhotoshopMenu.exe.sha256','PhotoshopMenu-UXP-'+expected_version+'.zip'}.issubset(names):
            raise ValueError('需要统一后台安装包，不能使用独立 UXP 或源码 ZIP')
        if not 0<bundle.getinfo('PhotoshopMenu.exe').file_size<=MAX_DOWNLOAD:
            raise ValueError('应用大小无效')
        if bundle.getinfo('PhotoshopMenu.exe.sha256').file_size>4096:raise ValueError('应用摘要文件过大')
        exe_sha=parse_checksum(bundle.read('PhotoshopMenu.exe.sha256'),'PhotoshopMenu.exe')
        with bundle.open('PhotoshopMenu.exe') as source, destination.open('xb') as target:
            shutil.copyfileobj(source,target,1024*1024)
    if sha256(destination)!=exe_sha or executable_version(destination)!=expected_version:
        raise ValueError('应用文件校验或版本不匹配')
    return {'version':expected_version,'sha256':exe_sha,'folder':str(Path(folder).resolve())}


class ApplicationUpdates:
    def __init__(self, runtime, current=APP_VERSION):
        self.runtime=Path(runtime).resolve();self.root=self.runtime/'application-updates'
        self.path=self.runtime/'application-update.json';self.current=current
        self.lock=threading.RLock();self.worker=None;self.schedule=None
        try:self.data=json.loads(self.path.read_text('utf-8'))
        except (OSError,ValueError):self.data={}
        if not isinstance(self.data,dict):self.data={}
        self.data.setdefault('auto_check',True)
        if type(self.data['auto_check']) is not bool:self.data['auto_check']=True
        for field in ('last_attempt','last_checked'):
            if type(self.data.get(field,0)) not in (int,float):self.data[field]=0
        if self.data.get('phase') in ('checking','downloading'):
            self.data.update(phase='error',message='上次检查或下载已中断，可重新操作；未安装更新')
        self.data.setdefault('phase','idle')
        self.data.setdefault('message','尚未检查 GitHub 正式版本')
        self.progress=0
        self.closing=threading.Event()

    def change(self, **fields):
        with self.lock:
            self.data.update(fields);atomic_json(self.path,self.data)

    def snapshot(self):
        with self.lock:result=copy.deepcopy(self.data)
        result.update(source=RELEASES,current=self.current,progress=self.progress,
                      supported=os.name=='nt' and bool(getattr(sys,'frozen',False)))
        release=result.get('release')
        if release:
            try:result['available']=select_release(self._release_document(release),self.current)['available']
            except (ValueError,KeyError,TypeError):result['available']=False
        stage=result.get('staged')
        if stage:
            try:
                if not self.stage_folder(stage).is_dir():raise ValueError()
                if version(stage['version'])<=version(self.current):result.pop('staged',None)
            except (ValueError,KeyError,TypeError):result.pop('staged',None)
        job=result.get('job')
        if isinstance(job,str) and re.fullmatch(r'[0-9a-f]{32}',job):
            try:result['installation']=json.loads((self.root/job/'result.json').read_text('utf-8'))
            except (OSError,ValueError):pass
        if result.get('phase')=='installing' and result.get('installation',{}).get('phase') in ('completed','rolled-back','error'):
            result['phase']=result['installation']['phase'];result['message']=result['installation']['message']
        return result

    @staticmethod
    def _release_document(release):
        return {'id':release['id'],'tag_name':release['tag'],'draft':False,'prerelease':False,
                'body':release['notes'],'assets':[{'state':'uploaded','browser_download_url':a['url'],**a}
                                                  for a in (release['asset'],release['checksum'])]}

    def stage_folder(self, stage):
        folder=Path(stage['folder']).resolve()
        if folder.parent!=self.root or not re.fullmatch(r'[0-9a-f]{32}',folder.name):
            raise ValueError('更新暂存目录无效')
        if not HASH.fullmatch(stage['sha256']):raise ValueError('暂存摘要无效')
        return folder

    def start(self, operation):
        if self.worker and not self.worker.done():raise RuntimeError('正在检查或下载更新，请等待完成')
        if self.snapshot()['phase']=='installing':raise RuntimeError('应用更新正在安装')
        self.change(phase='checking' if operation=='check' else 'downloading',message='正在检查 GitHub 正式版本' if operation=='check' else '正在下载统一安装包')
        self.progress=0
        async def work():
            try:await asyncio.to_thread(self.check if operation=='check' else self.download)
            except Exception as error:
                self.change(phase='error',message='更新检查或下载失败；当前应用未更改',error=update_error(error))
        self.worker=asyncio.create_task(work())
        return {'message':self.data['message']}

    def check(self):
        headers={'User-Agent':'PhotoshopMenu/'+self.current,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}
        if self.data.get('etag') and self.data.get('release'):headers['If-None-Match']=self.data['etag']
        try:
            with opener().open(Request(API,headers=headers),timeout=20) as response:
                body=response.read(1024*1024+1)
                if len(body)>1024*1024:raise ValueError('发行记录过大')
                release=select_release(json.loads(body),self.current)
                etag=response.headers.get('ETag','')
        except HTTPError as error:
            if error.code==304 and self.data.get('release'):
                release=select_release(self._release_document(self.data['release']),self.current);etag=self.data.get('etag','')
            elif error.code in (403,429):
                # This small public Release asset does not use the REST API.
                # Validate the same repo/version/asset identities as API data.
                try:
                    with opener().open(Request(MANIFEST,headers={'User-Agent':'PhotoshopMenu/'+self.current,'Accept':'application/json'}),timeout=20) as response:
                        body=response.read(65537)
                        if len(body)>65536:raise ValueError('更新清单过大')
                        release=select_release(json.loads(body),self.current);etag=''
                except Exception as fallback:
                    detail=update_error(fallback)
                    raise RuntimeError('GitHub API请求受限，Release备用清单也未能读取：'+detail) from None
            else:raise
        self.change(release=release,etag=etag,last_checked=time.time(),phase='available' if release['available'] else 'current',
                    message='发现新版，可以下载更新' if release['available'] else '当前已是最新版本',error='')

    def fetch(self, item, destination=None):
        headers={'User-Agent':'PhotoshopMenu/'+self.current,'Accept':'application/octet-stream'}
        with opener().open(Request(item['url'],headers=headers),timeout=30) as response:
            chunks=[];total=0;digest=hashlib.sha256();started=time.monotonic()
            with (Path(destination).open('xb') if destination else nullcontext()) as file:
                while True:
                    if self.closing.is_set():raise RuntimeError('后台正在退出，下载已停止；当前应用未更改')
                    if time.monotonic()-started>600:raise TimeoutError('下载超时，可重新下载；当前应用未更改')
                    chunk=response.read(256*1024)
                    if not chunk:break
                    total+=len(chunk)
                    if total>item['size']:raise ValueError('下载内容超过发行附件大小')
                    digest.update(chunk)
                    if file:file.write(chunk);self.progress=round(100*total/item['size'])
                    else:chunks.append(chunk)
        if total!=item['size']:raise ValueError('下载不完整')
        if item.get('digest') and item['digest']!='sha256:'+digest.hexdigest():raise ValueError('发行附件 SHA256 不匹配')
        return b''.join(chunks) if not destination else digest.hexdigest()

    def download(self):
        cached=copy.deepcopy(self.data.get('release'))
        if not cached:raise ValueError('请先检查应用更新')
        release=select_release(self._release_document(cached),self.current)
        if not release['available']:raise ValueError('没有更高版本的正式更新')
        expected=parse_checksum(self.fetch(release['checksum']),release['asset']['name'])
        if release['asset'].get('digest') and release['asset']['digest']!='sha256:'+expected:
            raise ValueError('发行摘要与 SHA256 文件不一致')
        folder=self.root/uuid.uuid4().hex;folder.mkdir(parents=True)
        package=folder/'package.zip'
        try:
            if self.fetch(release['asset'],package)!=expected:raise ValueError('统一安装包 SHA256 不匹配')
            staged=unpack_package(package,folder,release['version'],expected)
            atomic_json(folder/'verified.json',staged)
            self.change(staged=staged,phase='ready',message='更新包已下载并校验，空闲时可安装并重启后台',error='')
        except Exception:
            # Only files created in this unique stage; retain other stages/backups.
            for name in ('package.zip','PhotoshopMenu.exe'):(folder/name).unlink(missing_ok=True)
            raise

    def set_auto(self, enabled):
        if type(enabled) is not bool:raise ValueError('自动检查设置必须为布尔值')
        self.change(auto_check=enabled)
        return {'message':'自动检查设置已保存'}

    async def periodic(self):
        while True:
            # No automatic retries for failed downloads or installations.
            if (self.data.get('auto_check') and time.time()-self.data.get('last_attempt',0)>=CHECK_INTERVAL and
                self.snapshot()['phase'] not in ('installing','ready') and not (self.worker and not self.worker.done())):
                self.change(last_attempt=time.time());self.start('check')
            await asyncio.sleep(60)

    async def close(self):
        self.closing.set()
        if self.schedule:self.schedule.cancel();await asyncio.gather(self.schedule,return_exceptions=True)
        if self.worker:await asyncio.gather(self.worker,return_exceptions=True)

    async def prepare_install(self, port, headless, no_desktop):
        if os.name!='nt' or not getattr(sys,'frozen',False):raise RuntimeError('应用更新安装仅支持打包后的 Windows EXE')
        if self.worker and not self.worker.done():raise RuntimeError('请等待检查或下载完成')
        staged=self.snapshot().get('staged')
        if not staged:raise ValueError('请先下载并校验更高版本更新')
        stage_folder=self.stage_folder(staged);source=stage_folder/'PhotoshopMenu.exe'
        if sha256(source)!=staged['sha256'] or executable_version(source)!=staged['version']:
            raise ValueError('暂存应用已改变，请重新下载')
        target=Path(sys.executable).resolve()
        if target.name!='PhotoshopMenu.exe' or target.is_relative_to(self.root):raise ValueError('实际运行入口不适合自动更新')
        import win32com.client
        def process_ids():
            import pythoncom
            pythoncom.CoInitialize()
            try:
                wmi=win32com.client.GetObject('winmgmts:')
                process=list(wmi.ExecQuery('SELECT ParentProcessId FROM Win32_Process WHERE ProcessId='+str(os.getpid())))[0]
                ids=[os.getpid()]
                for parent in wmi.ExecQuery('SELECT ExecutablePath FROM Win32_Process WHERE ProcessId='+str(process.ParentProcessId)):
                    if parent.ExecutablePath and Path(parent.ExecutablePath).resolve()==target:ids.append(int(process.ParentProcessId))
                return ids
            finally:pythoncom.CoUninitialize()
        ids=await asyncio.to_thread(process_ids)
        # A new job per attempt prevents a stale ready/result file from an
        # earlier cancelled helper causing shutdown without a live updater.
        folder=self.root/uuid.uuid4().hex;folder.mkdir()
        await asyncio.to_thread(shutil.copy2,source,folder/'PhotoshopMenu.exe')
        helper=folder/'update-host.exe'
        # The verified new release supplies the helper as well. Keep the
        # --apply-update schema backward-compatible in subsequent releases.
        await asyncio.to_thread(shutil.copy2,source,helper)
        job={'schema':1,'id':folder.name,'runtime':str(self.runtime),'target':str(target),
             'old_sha256':sha256(target),'old_version':self.current,'new_sha256':staged['sha256'],
             'new_version':staged['version'],'pids':ids,'port':port,'headless':headless,'no_desktop':no_desktop}
        atomic_json(folder/'job.json',job)
        process=subprocess.Popen([str(helper),'--apply-update',str(folder/'job.json')],cwd=str(folder),
                                 stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        for _ in range(600):
            if (folder/'helper-ready.json').exists():
                ready=json.loads((folder/'helper-ready.json').read_text('utf-8'))
                if ready.get('id')==folder.name and ready.get('ready') is True:
                    self.change(phase='installing',job=folder.name,message='正在正常退出后台，安装后自动重新连接',error='')
                    return {'message':'正在正常退出后台，安装后自动重新连接'}
                raise RuntimeError(ready.get('error','更新助手未就绪'))
            if process.poll() is not None:raise RuntimeError('更新助手启动失败；当前服务保持运行')
            await asyncio.sleep(.05)
        # Helper has a bounded wait and never replaces an active process.
        raise RuntimeError('更新助手启动超时；当前服务保持运行')
