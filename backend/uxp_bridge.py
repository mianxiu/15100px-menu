"""Production UXP execution using private local files; no COM write fallback."""
import asyncio
import json
import os
from pathlib import Path
import secrets
import time
from .photoshop_bridge import PhotoshopBridge
from .photoshop_version import require_version
from .plugins import version
from .layer_context import unavailable,validate,fresh
from .uxp_recovery import PendingUxp

def compatible(value):
    try:return version(value)[:2]==(0,3)
    except ValueError:return False

def read_heartbeat(folder):
    """Read current metadata through UXP's brief in-place overwrite window.

    No cached heartbeat, request publication or mutation retry. Callers still
    validate the returned session/version/lease. Never wait on missing files
    or ordinary permission failures; seven 4ms gaps bound transient retries.
    """
    for attempt in range(8):
        try:return json.loads((folder/'probe-last.json').read_text('utf-8-sig'))
        except json.JSONDecodeError:
            if attempt==7:raise
        except PermissionError as error:
            if getattr(error,'winerror',None) not in (5,32) or attempt==7:raise
        time.sleep(.004)

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
        self.pending=PendingUxp(self.config.parent/'uxp-pending.json',self.storage)
        self.task_id=None
        self.response_timeout=120

    @property
    def folder(self):
        candidates=[]
        for folder in self.storage.glob('*/External/com.15100px.menu.offline-probe/PluginData'):
            try:
                heartbeat=read_heartbeat(folder)
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

    def call(self, operation, preview=None, **payload):
        import msvcrt
        if self.pending.value or self.pending.error:raise RuntimeError('上一项 UXP 结果待核对，未提交新请求')
        token=json.loads(self.config.read_text('utf-8-sig'))['token']
        folder=self.folder # Pin this host for the entire request, including its response.
        with (folder/'transport.lock').open('a+b') as lease:
            lease.seek(0);lease.write(b'0');lease.flush();lease.seek(0)
            try:msvcrt.locking(lease.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:raise RuntimeError('UXP 正在执行其他请求，未排队') from None
            try:
                heartbeat=read_heartbeat(folder)
                if not compatible(heartbeat.get('probe_version')) or time.time()*1000-heartbeat.get('plugin_time_ms',0)>15000:
                    raise RuntimeError('UXP 未就绪，请正常启动 Photoshop 并加载 0.3.x 插件')
                identity=secrets.token_hex(16)
                modifying=operation in ('set_label','new_document')
                if modifying and version(heartbeat.get('probe_version'))<(0,3,8):
                    raise RuntimeError('请更新并重新加载 UXP 0.3.8，以支持结果核对；未提交修改')
                if payload.get('command') in ('selectAbove','selectBelow','extendAbove','extendBelow') and version(heartbeat.get('probe_version'))<(0,3,16):
                    raise RuntimeError('请更新并重新加载 UXP 0.3.16，以支持单选与Shift多选；未提交操作')
                if payload.get('command')=='convertSmartObject' and version(heartbeat.get('probe_version'))<(0,3,18):
                    raise RuntimeError('请更新并重新加载 UXP 0.3.18，以支持转换智能对象；未提交操作')
                if payload.get('command')=='shape.paint' and 'mask' in payload.get('paint',{}) and version(heartbeat.get('probe_version'))<(0,3,20):
                    raise RuntimeError('请更新并重新加载 UXP 0.3.20，以支持形状羽化／密度；未提交操作')
                if payload.get('command')=='shape.preview' and (preview is None or version(heartbeat.get('probe_version'))<(0,3,24)):
                    raise RuntimeError('请更新并重新加载 UXP 0.3.24，以支持蒙版实时预览；未提交操作')
                request={**payload,'id':identity,'token':token,'session':heartbeat.get('session'),'operation':operation,'expires_at_ms':int(time.time()*1000)+5000}
                encoded=json.dumps(request)
                if len(encoded.encode('utf-8'))>4096:raise ValueError('UXP 请求超出本地协议长度，未提交操作')
                temporary=folder/(identity+'.tmp')
                if modifying:self.pending.begin(request,folder,self.task_id)
                try:
                    if preview is not None:preview.bind(folder,request)
                    temporary.write_text(encoded,'utf-8');publish_request(temporary,folder/'probe-request.json')
                except Exception:
                    if modifying:self.pending.clear()
                    raise
                interactive=operation=='set_label' and payload.get('command') in ('editStyle','shape.preview')
                deadline=None if interactive else time.monotonic()+self.response_timeout
                checked=0
                while deadline is None or time.monotonic()<deadline:
                    if interactive and time.monotonic()-checked>=1:
                        checked=time.monotonic()
                        from .uxp_management import photoshop_running
                        operation_name='预览' if payload.get('command')=='shape.preview' else '样式'
                        if not photoshop_running():raise UxpResultUnknown('Photoshop已退出，'+operation_name+'结果待核对；不重发')
                        try:
                            current=json.loads((folder/'probe-last.json').read_text('utf-8-sig'))
                            if current.get('session')!=request['session']:raise UxpResultUnknown('PS会话已改变，'+operation_name+'结果待核对；不重发')
                        except (OSError,ValueError):pass
                    try:
                        response=self.pending.read_result(allow_unknown=True) if modifying else json.loads((folder/'probe-response.json').read_text('utf-8-sig'))
                        if response is None:
                            time.sleep(.008);continue
                        if response.get('id')==identity:
                            if response.get('phase')!='completed':
                                if response.get('result_unknown'):raise UxpResultUnknown(response.get('error','新建结果未知，请检查 Photoshop'))
                                raise RuntimeError(response.get('error','UXP failed'))
                            return response
                    except (FileNotFoundError,PermissionError,json.JSONDecodeError):pass
                    time.sleep(.008)
                raise UxpResultUnknown('UXP 回应超时，结果待核对；已阻止新操作，不自动重发')
            finally:
                lease.seek(0);msvcrt.locking(lease.fileno(),msvcrt.LK_UNLCK,1)

class UxpBridge(PhotoshopBridge):
    def _status(self):
        # Avoid status DoJavaScript calls that may reset Photoshop's tool cursor
        # even for a read-only script. Observe the UXP heartbeat instead.
        # An older/missing plugin may use native COM properties as a fallback,
        # but never execute a script from the status path.
        try:
            heartbeat=json.loads((self.transport.folder/'probe-last.json').read_text('utf-8-sig'))
            theme=heartbeat.get('ui_theme');font=heartbeat.get('ui_font_size')
            if theme in ('light','light-gray','dark-gray','dark'):self.ui_theme=theme
            if font in ('small','medium','large'):self.ui_font_size=font
            name=heartbeat.get('document_name')
            return {'connected':True,'ui_theme':self.ui_theme,'ui_font_size':self.ui_font_size,
                'document':name if isinstance(name,str) else None,'message':'已连接 Photoshop'}
        except (OSError,ValueError,RuntimeError):
            try:
                app=self._application();count=int(app.Documents.Count)
                return {'connected':True,'ui_theme':self.ui_theme,'ui_font_size':self.ui_font_size,
                    'document':str(app.ActiveDocument.Name) if count else None,
                    'message':'Photoshop 已连接，等待 UXP 加载'}
            except Exception:
                return {'connected':False,'ui_theme':self.ui_theme,'ui_font_size':self.ui_font_size,
                    'document':None,'message':'请先启动 Photoshop'}

    def __init__(self, task_history=None, config=None):
        super().__init__(task_history)
        self.tasks.channel='uxp-local-files'
        self.execution_guard=None
        self.document_guard=None
        self.transport=UxpTransport(config or Path(task_history).parent/'uxp-config.json')
        self.layer_context=unavailable()
        self._reconcile_lock=asyncio.Lock()
        self._recovery_feedback=''
        if self.transport.pending.value or self.transport.pending.error:
            self.busy=True
            if self.transport.pending.value:self._active_task_id=self.transport.pending.value['task_id']

    async def reconcile_result(self):
        """Read original receipt only; never publish a request or query PS state."""
        async with self._reconcile_lock:
            pending=self.transport.pending
            if not isinstance(pending,PendingUxp):return {'active':False}
            if not pending.value:return pending.snapshot()
            task_id=pending.value['task_id']
            try:task=self.tasks.get(task_id)
            except ValueError:return {**pending.snapshot(),'message':'原任务历史记录缺失，保留待核对记录并阻止修改'}
            if task['state'] in ('succeeded','failed'):
                await self.tasks.flush()
                await asyncio.to_thread(pending.clear)
                self.busy=False
                if task.get('reconciled'):
                    self.last_error=task.get('error','')
                    self._recovery_feedback='UXP 最终结果已核对：'+task.get('message','')+'；未重复执行'
                return {'active':False}
            # A live worker still owns the result callback; do not release busy
            # or overwrite its outcome while it waits for the same receipt.
            if task['state']!='result-unknown' or (not task.get('restored') and getattr(self,'_operation_future',None) is not None and not self._operation_future.done()):
                return pending.snapshot()
            response=await asyncio.to_thread(pending.read_result)
            if response is None:return pending.snapshot()
            success=response['phase']=='completed'
            try:message=self._result_message(task['action'],json.dumps(response['result'])) if success else '原 UXP 任务已确认失败，未重复执行'
            except (ValueError,KeyError,TypeError):return pending.snapshot()
            self.tasks.confirm_uxp_result(task_id,'succeeded' if success else 'failed',message=message,
                error='' if success else response['error'],reconciled=True,
                uxp_request_id=response['id'],uxp_session=response['session'])
            await self.tasks.flush()
            await asyncio.to_thread(pending.clear)
            self.busy=False
            self.last_error='' if success else response['error']
            self._recovery_feedback='UXP 最终结果已核对：'+message+'；未重复执行'
            self._queue_changed.set()
            return {'active':False,'message':self._recovery_feedback,'task_id':task_id}

    async def status(self,force=False):
        await self.reconcile_result()
        return await super().status(force)

    async def _execute_task(self,*args,**kwargs):
        await self.reconcile_result()
        if not self.busy:self._recovery_feedback=''
        try:return await super()._execute_task(*args,**kwargs)
        finally:await self.reconcile_result()

    def request_menu_context(self, epoch):
        folder=self.transport.folder
        heartbeat=read_heartbeat(folder)
        if version(heartbeat.get('probe_version'))<(0,3,14):return None
        token=json.loads(self.transport.config.read_text('utf-8-sig'))['token']
        # New plugins publish basic eligibility before optional paint metadata.
        # Allow a slow host to finish this read-only request without relaxing
        # snapshot freshness, request identity, or any mutation target checks.
        lifetime=10 if version(heartbeat.get('probe_version'))>=(0,3,17) else 3
        deadline=time.monotonic()+lifetime
        request={'id':secrets.token_hex(16),'session':heartbeat['session'],'token':token,'expires_at_ms':int(time.time()*1000)+lifetime*1000}
        temporary=folder/(request['id']+'.menu.tmp')
        try:
            temporary.write_text(json.dumps(request),'utf-8')
            # UXP briefly holds its read handle without delete sharing. Retry
            # only publication of this same, not-yet-accepted request; no new
            # ID, request replay, longer expiry or keyboard-hook wait.
            publish_request(temporary,folder/'menu-context-request.json')
        finally:
            if temporary.exists():temporary.unlink()
        return {'id':request['id'],'session':request['session'],'folder':folder,'epoch':epoch,'deadline':deadline}

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
        recovery=self.transport.pending.snapshot() if isinstance(self.transport.pending,PendingUxp) else {'active':False}
        if recovery['active']:
            value.update(message=recovery['message'],status_wait_reason='uxp-result-pending',status_fresh=False,busy=True)
        elif self._recovery_feedback:recovery['message']=self._recovery_feedback
        value['uxp_recovery']=recovery
        try:
            heartbeat=json.loads((self.transport.folder/'probe-last.json').read_text('utf-8-sig'))
            value['uxp_ready']=compatible(heartbeat.get('probe_version')) and time.time()*1000-heartbeat.get('plugin_time_ms',0)<15000
            value['uxp_version']=heartbeat.get('probe_version')
            value['photoshop_version']=heartbeat.get('photoshop_version')
            value['layer_observation']=heartbeat.get('layer_observation',{})
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
        self.transport.task_id=self._active_task_id
        self._uxp_worker_active=True
        try:
            response=self.transport.call('set_label',**payload)
            # The plugin captured this selection after the mutation, before its
            # final receipt. Hand it to the desktop before completion feedback;
            # do not reuse the pre-creation cache in a freshly opened menu.
            context=validate(response.get('layer_context'),self._captured_app)
            self.layer_context=context if fresh(context) else unavailable()
            return json.dumps(response['result'])
        finally:self._uxp_worker_active=False

    def _bind_menu_target(self,target):
        if self.focus_guard:self.focus_guard()
        if (not isinstance(target,dict) or not isinstance(target.get('session'),str) or not target['session'] or
            type(target.get('document_id')) is not int or target['document_id']<=0 or
            not isinstance(target.get('layer_ids'),list) or len(target['layer_ids'])!=1 or
            type(target['layer_ids'][0]) is not int or target['layer_ids'][0]<=0 or
            target.get('active_layer_id')!=target['layer_ids'][0]):
            raise ValueError('Invalid frozen single-layer menu target')
        self._captured_target={key:target[key] for key in ('session','document_id','active_layer_id','layer_ids')}
        self._captured_target['layer_ids']=list(target['layer_ids'])
        self._captured_app=target['session']
        return {**self._captured_target,'instance_binding':target['session']}

    async def execute(self, action, before_dispatch=None, enqueue=False, frozen_target=None):
        if action=='document.recent':raise ValueError('请从首页最近预设列表选择尺寸')
        if self.execution_guard:self.execution_guard()
        if frozen_target is not None:
            # The menu already froze one selected layer. The plugin rechecks
            # session/document/active selection inside its modal before writes;
            # another capture IPC would only rediscover the same identity.
            frozen={**frozen_target,'layer_ids':list(frozen_target.get('layer_ids',[]))}
            return await self._execute_task(action,before_dispatch,capture=lambda:self._bind_menu_target(frozen))
        return await super().execute(action,before_dispatch,enqueue=False)

    async def execute_shape(self, params, before_dispatch=None, frozen_target=None, preview=None):
        from .shape_paint import parameters
        params=parameters(params)
        if self.execution_guard:self.execution_guard()
        def write(action):
            self.transport.task_id=self._active_task_id;self._uxp_worker_active=True
            try:
                response=self.transport.call('set_label',preview=preview,command='shape.preview' if preview else 'shape.paint',target=self._captured_target,paint=params)
                value=validate(response.get('layer_context'),self._captured_app)
                self.layer_context=value if fresh(value) else unavailable()
                return json.dumps(response['result'])
            finally:self._uxp_worker_active=False
        capture=(lambda:self._bind_menu_target(frozen_target)) if frozen_target is not None else self._capture_target
        return await self._execute_task('shape.paint',before_dispatch,capture=capture,execute=write,interactive=preview is not None)

    def _capture_new_target(self):
        if self.document_guard:self.document_guard()
        target=self.transport.call('inspect').get('target')
        if not isinstance(target,dict) or 'document_ids' not in target:
            raise RuntimeError('最近预设新建需要更新并重新加载 UXP 0.3.2')
        self._captured_target=target
        return dict(target)

    def _execute_new_document(self, preset):
        if self.document_guard:self.document_guard()
        self.transport.task_id=self._active_task_id
        self._uxp_worker_active=True
        try:return json.dumps(self.transport.call('new_document',target=self._captured_target,preset=preset)['result'])
        finally:self._uxp_worker_active=False

    async def execute_recent(self, preset, before_dispatch=None):
        if self.execution_guard:self.execution_guard()
        return await self._execute_task('document.recent',before_dispatch,
            capture=self._capture_new_target,execute=lambda action:self._execute_new_document(preset))

    def replace_scripts(self,scripts):
        # Existing script-package UI stays readable; JSX never controls UXP.
        self.scripts=dict(scripts)
