"""Production UXP execution using private local files; no COM write fallback."""
import json
import os
from pathlib import Path
import secrets
import time
from .photoshop_bridge import PhotoshopBridge
from .photoshop_version import require_version
from .plugins import version
from .layer_context import unavailable,validate,fresh

def compatible(value):
    try:return version(value)[:2]==(0,3)
    except ValueError:return False

class UxpResultUnknown(RuntimeError):
    result_unknown = True

def publish_request(temporary, destination):
    """Retry only failed atomic publication, never an accepted operation."""
    deadline=time.monotonic()+.25
    try:
        while True:
            try:
                os.replace(temporary,destination)
                return
            except PermissionError as error:
                if getattr(error,'winerror',None) not in (5,32) or time.monotonic()>=deadline:raise
                # UXP may still hold a read handle without Windows delete-share.
                time.sleep(.004)
    finally:
        if temporary.exists():temporary.unlink()

class UxpTransport:
    def __init__(self, config):
        self.config=Path(config)
        self.storage=Path(os.environ.get('APPDATA',str(Path.home()/'AppData/Roaming')))/'Adobe/UXP/PluginsStorage/PHSP'

    @property
    def folder(self):
        candidates=[]
        for folder in self.storage.glob('*/External/com.15100px.menu.offline-probe/PluginData'):
            try:
                heartbeat=json.loads((folder/'probe-last.json').read_text('utf-8-sig'))
                age=time.time()*1000-heartbeat.get('plugin_time_ms',0)
                if compatible(heartbeat.get('probe_version')) and 0<=age<15000:
                    require_version(heartbeat.get('photoshop_version'))
                    candidates.append(folder)
            except (OSError,ValueError,TypeError):pass
        if len(candidates)>1:
            raise RuntimeError('检测到多个 Photoshop UXP 实例，请仅保留一个实例运行')
        if not candidates:
            raise RuntimeError('UXP 未就绪，请启动 Photoshop 24.0.1 或更新版本')
        return candidates[0]

    def call(self, operation, **payload):
        import msvcrt
        token=json.loads(self.config.read_text('utf-8-sig'))['token']
        folder=self.folder # Pin this host for the entire request, including its response.
        with (folder/'transport.lock').open('a+b') as lease:
            lease.seek(0);lease.write(b'0');lease.flush();lease.seek(0)
            try:msvcrt.locking(lease.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:raise RuntimeError('UXP 正在执行其他请求，未排队') from None
            try:
                heartbeat=json.loads((folder/'probe-last.json').read_text('utf-8-sig'))
                if not compatible(heartbeat.get('probe_version')) or time.time()*1000-heartbeat.get('plugin_time_ms',0)>15000:
                    raise RuntimeError('UXP 未就绪，请正常启动 Photoshop 并加载 0.3.x 插件')
                identity=secrets.token_hex(16)
                request={**payload,'id':identity,'token':token,'operation':operation,'expires_at_ms':int(time.time()*1000)+5000}
                encoded=json.dumps(request)
                if len(encoded.encode('utf-8'))>4096:raise ValueError('UXP 请求超出本地协议长度，未提交操作')
                temporary=folder/(identity+'.tmp')
                temporary.write_text(encoded,'utf-8');publish_request(temporary,folder/'probe-request.json')
                deadline=time.monotonic()+120
                while time.monotonic()<deadline:
                    try:
                        response=json.loads((folder/'probe-response.json').read_text('utf-8-sig'))
                        if response.get('id')==identity:
                            if response.get('phase')!='completed':
                                if response.get('result_unknown'):raise UxpResultUnknown(response.get('error','新建结果未知，请检查 Photoshop'))
                                raise RuntimeError(response.get('error','UXP failed'))
                            return response
                    except (FileNotFoundError,PermissionError,json.JSONDecodeError):pass
                    time.sleep(.008)
                raise UxpResultUnknown('UXP 回应超时，结果未知；已阻止后续操作，请检查 PS 后重启服务')
            finally:
                lease.seek(0);msvcrt.locking(lease.fileno(),msvcrt.LK_UNLCK,1)

class UxpBridge(PhotoshopBridge):
    def __init__(self, task_history=None, config=None):
        super().__init__(task_history)
        self.tasks.channel='uxp-local-files'
        self.execution_guard=None
        self.document_guard=None
        self.transport=UxpTransport(config or Path(task_history).parent/'uxp-config.json')
        self.layer_context=unavailable()

    def read_layer_context(self):
        # Called by the desktop monitor, never by the low-level hook or open().
        try:
            folder=self.transport.folder
            heartbeat=json.loads((folder/'probe-last.json').read_text('utf-8-sig'))
        except (OSError,ValueError,RuntimeError,KeyError,TypeError):
            self.layer_context=unavailable()
            return self.layer_context
        try:
            source=folder/'layer-context.json'
            if source.stat().st_size>32768:raise ValueError('Layer metadata exceeds limit')
            self.layer_context=validate(json.loads(source.read_text('utf-8-sig')),heartbeat['session'])
        except (OSError,ValueError,RuntimeError,KeyError,TypeError):
            # A reader may meet UXP's short overwrite window. Retain only a
            # recent snapshot from this exact plugin session, never an old host.
            if self.layer_context.get('session')!=heartbeat.get('session') or not fresh(self.layer_context):
                self.layer_context=unavailable()
        return self.layer_context

    def _status_snapshot(self):
        value=super()._status_snapshot()
        value['execution_backend']='uxp-local-files'
        value['layer_context']=self.layer_context
        try:
            heartbeat=json.loads((self.transport.folder/'probe-last.json').read_text('utf-8-sig'))
            value['uxp_ready']=compatible(heartbeat.get('probe_version')) and time.time()*1000-heartbeat.get('plugin_time_ms',0)<15000
            value['uxp_version']=heartbeat.get('probe_version')
            value['photoshop_version']=heartbeat.get('photoshop_version')
        except (OSError,ValueError,RuntimeError):value['uxp_ready']=False
        return value

    def _capture_target(self):
        if self.focus_guard:self.focus_guard()
        target=self.transport.call('capture')['target']
        self._captured_target=target
        self._captured_app=target['session']
        return {**target,'instance_binding':target['session']}

    def _execute(self, action):
        if self.focus_guard:self.focus_guard()
        if not self._captured_target:raise RuntimeError('未固定 UXP 目标')
        payload={'target':self._captured_target}
        if action.startswith('label.') or action=='color':
            payload.update(command='label',color=action.split('.',1)[1] if '.' in action else 'orange')
        else:payload['command']=action
        return json.dumps(self.transport.call('set_label',**payload)['result'])

    async def execute(self, action, before_dispatch=None, enqueue=False):
        if action=='document.recent':raise ValueError('请从首页最近预设列表选择尺寸')
        if self.execution_guard:self.execution_guard()
        return await super().execute(action,before_dispatch,enqueue=False)

    def _capture_new_target(self):
        if self.document_guard:self.document_guard()
        target=self.transport.call('inspect').get('target')
        if not isinstance(target,dict) or 'document_ids' not in target:
            raise RuntimeError('最近预设新建需要更新并重新加载 UXP 0.3.2')
        self._captured_target=target
        return dict(target)

    def _execute_new_document(self, preset):
        if self.document_guard:self.document_guard()
        return json.dumps(self.transport.call('new_document',target=self._captured_target,preset=preset)['result'])

    async def execute_recent(self, preset, before_dispatch=None):
        if self.execution_guard:self.execution_guard()
        return await self._execute_task('document.recent',before_dispatch,
            capture=self._capture_new_target,execute=lambda action:self._execute_new_document(preset))

    def replace_scripts(self,scripts):
        # Existing script-package UI stays readable; JSX never controls UXP.
        self.scripts=dict(scripts)
