"""Offline UXP lifecycle owned by the main application, not a separate installer."""
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import shutil
import uuid
import zipfile
from .settings import atomic_json
from .photoshop_version import MIN_PHOTOSHOP_TEXT, check_install_hosts, installed_paths
from .plugins import version, MAX_PACKAGE
from .language import read_language, localized_manifest, plugin_name
from .uxp_registration import UxpRegistration

PLUGIN_ID = 'com.15100px.menu.offline-probe'
FILES = ('manifest.json', 'main.js', 'labels.js')
OWNED = (*FILES, 'probe-config.js')

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def validate(folder, *, allow_previous_floor=False):
    folder = Path(folder)
    data = json.loads((folder/'manifest.json').read_text('utf-8-sig'))
    if data.get('id') != PLUGIN_ID or version(data.get('version'))[:2] != (0, 3):
        raise ValueError('不是兼容的 Photoshop Menu UXP 插件（需要 0.3.x）')
    host = data.get('host', {})
    floors={MIN_PHOTOSHOP_TEXT,'24.0.1'} if allow_previous_floor else {MIN_PHOTOSHOP_TEXT}
    if host.get('app') != 'PS' or host.get('minVersion') not in floors:
        raise ValueError('UXP 插件最低 Photoshop 版本必须为 '+MIN_PHOTOSHOP_TEXT)
    if data.get('main')!='main.js' or data.get('manifestVersion')!=5 or host.get('data')!={'apiVersion':2,'loadEvent':'startup'}:
        raise ValueError('UXP 插件启动方式或 API 不兼容')
    if data.get('requiredPermissions')!={'localFileSystem':'plugin'}:
        raise ValueError('离线插件只能请求本地插件文件权限')
    for name in FILES:
        content = (folder/name).read_bytes()
        if not content: raise ValueError('插件文件为空：'+name)
        content.decode('utf-8-sig')
    return data

def photoshop_running():
    import ctypes
    from ctypes import wintypes as W
    class Entry(ctypes.Structure):
        _fields_ = [('size',W.DWORD),('usage',W.DWORD),('pid',W.DWORD),('heap',ctypes.c_size_t),
                    ('module',W.DWORD),('threads',W.DWORD),('parent',W.DWORD),('priority',W.LONG),
                    ('flags',W.DWORD),('name',W.WCHAR*260)]
    api = ctypes.WinDLL('kernel32',use_last_error=True)
    api.CreateToolhelp32Snapshot.restype=W.HANDLE
    api.Process32FirstW.argtypes=api.Process32NextW.argtypes=[W.HANDLE,ctypes.POINTER(Entry)]
    api.CloseHandle.argtypes=[W.HANDLE]
    handle=api.CreateToolhelp32Snapshot(2,0)
    if handle==ctypes.c_void_p(-1).value: raise ctypes.WinError(ctypes.get_last_error())
    try:
        entry=Entry();entry.size=ctypes.sizeof(entry)
        ok=api.Process32FirstW(handle,ctypes.byref(entry))
        while ok:
            if entry.name.lower()=='photoshop.exe':return True
            ok=api.Process32NextW(handle,ctypes.byref(entry))
        return False
    finally:api.CloseHandle(handle)

class UxpManager:
    def __init__(self, runtime, builtin, roaming=None, running=None, hosts=None):
        self.runtime=Path(runtime)
        self.root=self.runtime/'uxp-management'
        self.builtin=Path(builtin)
        self.plugin=Path(roaming or os.environ.get('APPDATA', str(Path.home()/'AppData/Roaming')))/'Adobe/UXP/Plugins/External'/ (PLUGIN_ID+'_PS')
        self.registration=UxpRegistration(self.plugin.parents[2]/'PluginsInfo/v1/PS.json',self.plugin,PLUGIN_ID)
        self.state_path=self.root/'state.json'
        self.config=self.runtime/'uxp-config.json'
        self.running=running or photoshop_running
        self.hosts=hosts or (lambda explicit:check_install_hosts(installed_paths(explicit)))

    def state(self):
        if self.state_path.exists():return json.loads(self.state_path.read_text('utf-8'))
        return {'enabled':True,'history':[],'owned':{}}

    @property
    def enabled(self):return self.state().get('enabled',False) is True

    def status(self):
        language=read_language(self.runtime)
        result={'enabled':self.enabled,'installed':False,'version':None,'bundled_version':validate(self.builtin)['version'],
                'minimum_photoshop':MIN_PHOTOSHOP_TEXT,'can_rollback':bool(self.state()['history']),
                'plugin_dir':str(self.plugin),'matches_builtin':False,'error':'',
                'minimum_declaration_pending':False,
                'installation':'missing','name':None,'desired_name':plugin_name(language,validate(self.builtin)['version']),
                'language':language,'language_pending':False}
        try:
            if self.plugin.exists():
                result['installation']='invalid'
                data=validate(self.plugin,allow_previous_floor=True)
                result['minimum_declaration_pending']=data['host']['minVersion']!=MIN_PHOTOSHOP_TEXT
                result.update(installed=True,version=data['version'],name=data.get('name'))
                result['desired_name']=plugin_name(language,data['version'])
                result['language_pending']=data!=localized_manifest(data,language)
                builtin=validate(self.builtin)
                result['matches_builtin']=(localized_manifest(data,language)==localized_manifest(builtin,language)
                                          and all(digest(self.plugin/n)==digest(self.builtin/n) for n in ('main.js','labels.js')))
                token=json.loads(self.config.read_text('utf-8-sig'))['token']
                if (self.plugin/'probe-config.js').read_text('utf-8-sig').strip() != 'module.exports = '+json.dumps(token)+';':
                    result['error']='插件凭据与当前后台不一致，请关闭 PS 后重新安装内置插件'
                else:
                    tracked=self.state().get('owned',{})
                    changed=[n for n,wanted in tracked.items() if n in OWNED and digest(self.plugin/n)!=wanted]
                    if changed:result['error']='插件文件被外部修改：'+', '.join(changed)
                    else:result['installation']='installed'
        except (OSError,ValueError,KeyError) as error:result['error']=str(error)
        result['registration']=self.registration.status(data if result['installed'] else None)
        return result

    def sync_minimum_declaration(self):
        """Update only a known owned floor; loaded JS and credentials stay intact."""
        current=self.status()
        if not current['installed'] or current['error']:raise RuntimeError('无法确认原插件所有权，未修改最低版本')
        if not current['minimum_declaration_pending']:return current
        self.assert_owned()
        data=validate(self.plugin,allow_previous_floor=True)
        wanted=validate(self.builtin)
        data['host']['minVersion']=MIN_PHOTOSHOP_TEXT
        language=read_language(self.runtime)
        if (localized_manifest(data,language)!=localized_manifest(wanted,language) or
                any(digest(self.plugin/n)!=digest(self.builtin/n) for n in ('main.js','labels.js'))):
            raise RuntimeError('运行脚本或清单有其他变化，请正常关闭PS后安装')
        backup=self.snapshot()
        try:
            atomic_json(self.plugin/'manifest.json',data)
            state=self.state();state.update(history=state['history']+[backup],owned={n:digest(self.plugin/n) for n in OWNED})
            atomic_json(self.state_path,state);self.sync_receipt()
            if (self.runtime/'offline-install.json').exists():
                receipt=json.loads((self.runtime/'offline-install.json').read_text('utf-8'))
                receipt['minimum_photoshop']=MIN_PHOTOSHOP_TEXT
                atomic_json(self.runtime/'offline-install.json',receipt)
        except Exception:
            saved=self.root/'backups'/backup
            shutil.copy2(saved/'manifest.json',self.plugin/'manifest.json')
            atomic_json(self.state_path,json.loads((saved/'snapshot.json').read_text('utf-8'))['state'])
            if (saved/'offline-install.json').exists():shutil.copy2(saved/'offline-install.json',self.runtime/'offline-install.json')
            raise
        return self.status()

    def set_enabled(self, enabled):
        if type(enabled) is not bool:raise ValueError('启用状态必须为布尔值')
        if enabled:
            status=self.status()
            if not status['installed'] or status['error']:raise RuntimeError('请先安装可用的 UXP 插件')
        state=self.state();state['enabled']=enabled;atomic_json(self.state_path,state)
        return {'message':'UXP 执行已启用' if enabled else 'UXP 执行已禁用；不再接受菜单或快捷键操作', 'uxp':self.status()}

    def prepare(self, payload):
        if not payload or len(payload)>MAX_PACKAGE:raise ValueError('更新包必须小于 5 MiB')
        token=uuid.uuid4().hex;folder=self.root/'staging'/token
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                if len(archive.infolist())!=4 or set(archive.namelist())!={*FILES,'package.json'}:
                    raise ValueError('UXP ZIP 必须只包含 manifest.json、main.js、labels.js 和 package.json')
                if sum(i.file_size for i in archive.infolist())>MAX_PACKAGE:raise ValueError('解压后的更新包过大')
                folder.mkdir(parents=True)
                for info in archive.infolist():
                    if (info.external_attr>>16)&0o170000==0o120000:raise ValueError('更新包不能含符号链接')
                    (folder/info.filename).write_bytes(archive.read(info))
            metadata=json.loads((folder/'package.json').read_text('utf-8'))
            if metadata.get('id')!=PLUGIN_ID or metadata.get('api_version')!=1 or set(metadata.get('sha256',{}))!=set(FILES):
                raise ValueError('UXP 更新包协议或文件清单不兼容')
            if any(digest(folder/n)!=metadata['sha256'][n] for n in FILES):raise ValueError('UXP 更新包 SHA256 校验失败')
            data=validate(folder)
            current=self.status()
            if current['version'] and version(data['version'])<version(current['version']):raise ValueError('不能安装更低版本，请使用回退')
            return {'token':token,'manifest':data,'message':'离线 UXP 更新包校验通过；关闭 Photoshop 后安装'}
        except Exception:
            if folder.exists():shutil.rmtree(folder)
            raise

    def source(self, token):
        if token is None:return self.builtin
        if not isinstance(token,str) or len(token)!=32 or any(c not in '0123456789abcdef' for c in token):raise ValueError('无效更新包标识')
        source=self.root/'staging'/token
        metadata=json.loads((source/'package.json').read_text('utf-8'))
        if set(metadata['sha256'])!=set(FILES) or any(digest(source/n)!=metadata['sha256'][n] for n in FILES):
            raise ValueError('预览后的更新包已改变，请重新导入')
        return source

    def assert_owned(self):
        if not self.plugin.exists():return
        extras=[p.name for p in self.plugin.iterdir() if p.name not in OWNED]
        if extras:raise RuntimeError('插件目录含非管理文件，已保留：'+', '.join(extras))
        if (self.plugin/'manifest.json').exists() and json.loads((self.plugin/'manifest.json').read_text('utf-8-sig')).get('id')!=PLUGIN_ID:
            raise RuntimeError('插件目录属于其他插件，已保留')
        tracked=self.state().get('owned',{})
        receipt=self.runtime/'offline-install.json'
        if not tracked and receipt.exists():
            owned=json.loads(receipt.read_text('utf-8'))['owned']
            tracked={n:owned[str(self.plugin/n)] for n in OWNED if str(self.plugin/n) in owned}
        if not tracked and self.plugin.exists():
            # Adopt only an identical built-in installation with our credentials.
            current=self.status()
            if not current['matches_builtin'] or current['error']:raise RuntimeError('无法确认插件文件归属，请保留并手动检查')
        if any((self.plugin/n).exists() and digest(self.plugin/n)!=wanted for n,wanted in tracked.items()):
            raise RuntimeError('插件文件被外部修改，已保留；请检查后再更新')

    def snapshot(self):
        raw,registration=self.registration.snapshot()
        token=uuid.uuid4().hex;folder=self.root/'backups'/token;folder.mkdir(parents=True)
        present=[]
        for n in OWNED:
            if (self.plugin/n).exists():shutil.copy2(self.plugin/n,folder/n);present.append(n)
        for n in ('uxp-config.json','offline-install.json'):
            if (self.runtime/n).exists():shutil.copy2(self.runtime/n,folder/n);present.append(n)
        if raw is not None:(folder/'PS-index-recovery.json').write_bytes(raw)
        atomic_json(folder/'snapshot.json',{'present':present,'state':self.state(),'registration':registration})
        return token

    def restore(self, token, *, registration=True):
        if len(token)!=32 or any(c not in '0123456789abcdef' for c in token):raise ValueError('无效回退标识')
        folder=self.root/'backups'/token;data=json.loads((folder/'snapshot.json').read_text('utf-8'))
        plan=self.registration.prepare(restore=data['registration']) if registration and 'registration' in data else None
        for name in (*OWNED,'uxp-config.json','offline-install.json'):
            target=(self.plugin if name in OWNED else self.runtime)/name
            if name in data['present']:
                target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(folder/name,target)
            elif target.exists():target.unlink()
        if self.plugin.exists() and not any(self.plugin.iterdir()):self.plugin.rmdir()
        atomic_json(self.state_path,data['state'])
        if plan is not None:self.registration.commit(plan)

    def sync_receipt(self):
        path=self.runtime/'offline-install.json'
        if not path.exists():return
        receipt=json.loads(path.read_text('utf-8'))
        for name in OWNED:
            file=self.plugin/name
            receipt['owned'].pop(str(file),None)
            if file.exists():receipt['owned'][str(file)]=digest(file)
        if self.config.exists():receipt['owned'][str(self.config)]=digest(self.config)
        receipt['plugin_version']=self.status()['version'];atomic_json(path,receipt)

    def install(self, token=None, photoshop_exe=None):
        source=self.source(token);data=validate(source);current=self.status()
        if current['version'] and version(data['version'])<version(current['version']):raise ValueError('内置插件比当前版本旧，请使用回退')
        self.hosts(photoshop_exe)
        if self.running():raise RuntimeError('请先保存并正常关闭 Photoshop，再安装或更新；后台会继续运行')
        plan=self.registration.prepare(localized_manifest(data,read_language(self.runtime)))
        self.assert_owned();backup=self.snapshot()
        try:
            credential=secrets.token_hex(32)
            if self.config.exists():
                credential=json.loads(self.config.read_text('utf-8-sig'))['token']
                if not isinstance(credential,str) or len(credential)<32:raise ValueError('原有凭据无效，已保留')
            self.plugin.mkdir(parents=True,exist_ok=True)
            # Photoshop is closed; manifest is published last.
            for name in ('main.js','labels.js'):shutil.copy2(source/name,self.plugin/name)
            (self.plugin/'probe-config.js').write_text('module.exports = '+json.dumps(credential)+';\n','utf-8')
            if not self.config.exists():atomic_json(self.config,{'token':credential,'protocol_version':1})
            localized=localized_manifest(data,read_language(self.runtime))
            if localized==data:shutil.copy2(source/'manifest.json',self.plugin/'manifest.json')
            else:atomic_json(self.plugin/'manifest.json',localized)
            state=self.state();state.update(enabled=True,history=state['history']+[backup],owned={n:digest(self.plugin/n) for n in OWNED})
            atomic_json(self.state_path,state);self.sync_receipt()
            self.registration.commit(plan)
        except Exception:self.restore(backup,registration=False);raise
        return {'message':'UXP 插件已安装并启用；正常启动 Photoshop 后自动加载','uxp':self.status()}

    def apply_language(self):
        if self.running():raise RuntimeError('请先保存并正常关闭 Photoshop，再应用插件名称语言')
        current=self.status()
        if not current['installed'] or current['error']:raise RuntimeError('请先安装可用的 UXP 插件')
        self.assert_owned();backup=self.snapshot()
        plan=self.registration.prepare(localized_manifest(validate(self.plugin),read_language(self.runtime)))
        try:
            data=validate(self.plugin)
            atomic_json(self.plugin/'manifest.json',localized_manifest(data,read_language(self.runtime)))
            state=self.state();state.update(history=state['history']+[backup],owned={n:digest(self.plugin/n) for n in OWNED})
            atomic_json(self.state_path,state);self.sync_receipt()
            self.registration.commit(plan)
        except Exception:self.restore(backup,registration=False);raise
        return {'message':'插件名称语言已应用；下次启动 Photoshop 后生效','uxp':self.status()}

    def uninstall(self):
        if self.running():raise RuntimeError('请先保存并正常关闭 Photoshop，再卸载 UXP 插件')
        plan=self.registration.prepare()
        self.assert_owned();backup=self.snapshot()
        try:
            for name in OWNED:
                file=self.plugin/name
                if file.exists():file.unlink()
            if self.plugin.exists():self.plugin.rmdir()
            state=self.state();state.update(enabled=False,owned={},history=state['history']+[backup])
            atomic_json(self.state_path,state);self.sync_receipt()
            self.registration.commit(plan)
        except Exception:self.restore(backup,registration=False);raise
        return {'message':'UXP 插件已卸载；菜单程序、设置、凭据和任务记录保留','uxp':self.status()}

    def repair_registration(self):
        if self.running():raise RuntimeError('请先保存并正常关闭 Photoshop，再修复加载登记')
        current=self.status()
        if not current['installed'] or current['error']:raise RuntimeError('请先安装可用的 UXP 插件')
        self.assert_owned()
        plan=self.registration.prepare(validate(self.plugin),enable=True)
        backup=self.snapshot()
        try:
            state=self.state();state['history'].append(backup);atomic_json(self.state_path,state)
            self.registration.commit(plan)
        except Exception:self.restore(backup,registration=False);raise
        return {'message':'UXP 加载登记已修复；下次启动 Photoshop 后核对连接','uxp':self.status()}

    def rollback(self):
        if self.running():raise RuntimeError('请先保存并正常关闭 Photoshop，再回退 UXP 插件')
        self.assert_owned();history=self.state()['history']
        if not history:raise ValueError('没有可回退的 UXP 安装')
        safety=self.snapshot()
        saved=json.loads((self.root/'backups'/history[-1]/'snapshot.json').read_text('utf-8'))
        old_folder=self.root/'backups'/history[-1]
        plan=self.registration.prepare(restore=saved['registration']) if 'registration' in saved else self.registration.prepare(validate(old_folder,allow_previous_floor=True) if 'manifest.json' in saved['present'] else None)
        receipt=self.runtime/'offline-install.json'
        current_receipt=json.loads(receipt.read_text('utf-8')) if receipt.exists() else None
        try:
            self.restore(history[-1],registration=False)
            # Plugin rollback must not rewind ownership/version of a newer app.
            if current_receipt is not None:atomic_json(receipt,current_receipt)
            elif receipt.exists():receipt.unlink()
            self.sync_receipt()
            self.registration.commit(plan)
        except Exception:self.restore(safety,registration=False);raise
        return {'message':'已恢复上次 UXP 安装状态；正常启动 Photoshop 后加载','uxp':self.status()}

    def export(self):
        source=self.plugin if self.status()['installed'] else self.builtin
        return self.export_source(source)

    def export_builtin(self):
        return self.export_source(self.builtin)

    def export_source(self, source):
        validate(source);buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
            for n in FILES:archive.write(source/n,n)
            archive.writestr('package.json',json.dumps({'id':PLUGIN_ID,'api_version':1,'sha256':{n:digest(source/n) for n in FILES}},indent=2))
        return buffer.getvalue()
