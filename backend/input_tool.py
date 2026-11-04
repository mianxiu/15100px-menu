"""One authenticated, read-only tool observation; unknown requests are not republished."""
import json
import math
import secrets
import time
import threading
from datetime import datetime
from .settings import atomic_json
from .uxp_bridge import publish_request

class ToolReadError(RuntimeError):
    def __init__(self,reason,message,details=None):
        super().__init__(message)
        self.reason=reason;self.details=details or {}

def host_failure(value):
    """Only known tool fields may leave the private mailbox, never raw errors."""
    error=value.get('error')
    if not isinstance(error,str):return {'reason':'host-tool-failed'}
    if 'expired-before-read' in error:return {'reason':'expired-before-read'}
    if 'Unsupported tool state: ' in error:
        details={'reason':'unsupported-tool-state'}
        try:
            row=json.loads(error.split('Unsupported tool state: ',1)[1])
            tool=row.get('classID')
            if isinstance(tool,str) and tool.isascii() and tool.isidentifier() and tool.endswith('Tool') and len(tool)<=80:details['classID']=tool
            if row.get('isModal') in ('true','false','undefined','null'):details['isModal']=row['isModal']
        except (ValueError,TypeError,AttributeError):pass
        return details
    return {'reason':'host-tool-failed'}


class ToolObservation:
    def __init__(self,transport):
        self.lock=threading.RLock()
        self.transport=transport
        self.path=transport.config.parent/'input-tool-pending.json'
        self.retry_after=None
        self.report={'state':'idle'}
        self.last_failure=None

    def snapshot(self):
        return {**self.report,'last_failure':dict(self.last_failure) if self.last_failure else None}

    def event(self):
        try:
            folder,heartbeat=self.transport.observe()
            path=folder/'input-tool-event.json'
            if path.stat().st_size>2048:return
            value=json.loads(path.read_text('utf-8'))
            token=json.loads(self.transport.config.read_text('utf-8-sig'))['token']
            stamp=value.get('created_at_ms')
            if (type(value.get('schema')) is int and value['schema']==1 and value.get('session')==heartbeat['session'] and value.get('token')==token and
                type(value.get('sequence')) is int and value['sequence']>0 and value.get('state') in ('enter','exit') and
                type(stamp) in (int,float) and math.isfinite(stamp) and 0<=time.time()*1000-stamp<=2000):
                return value['session'],value['sequence'],value['state']
        except (RuntimeError,OSError,ValueError,TypeError,AttributeError):pass

    def reconcile(self):
        if self.path.exists():
            try:self.read(publish=False,wait=False)
            except RuntimeError:pass
            return not self.path.exists()
        if self.retry_after is not None and time.monotonic()>=self.retry_after:
            self.retry_after=None;return True
        return False

    def read(self,publish=True,wait=True,identity=None):
        with self.lock:
            try:
                value=self._read(publish,wait,identity)
                self.report={'state':'ready' if value else 'idle','observed_at_ms':round(time.time()*1000)}
                return value
            except (RuntimeError,OSError,ValueError,TypeError) as error:
                self.report={'state':'failed','reason':getattr(error,'reason','transport-unavailable'),
                             'error_type':type(error).__name__,'observed_at_ms':round(time.time()*1000)}
                if isinstance(error,ToolReadError) and error.details:self.last_failure={**error.details,'observed_at_ms':self.report['observed_at_ms']}
                raise

    def _read(self,publish=True,wait=True,identity=None):
        try:
            folder,heartbeat=self.transport.observe()
            if identity is not None:
                # A previous PS process can leave a fresh-looking heartbeat on disk.
                if not isinstance(identity,(list,tuple)) or len(identity)!=4:raise ToolReadError('invalid-host-identity','ENG宿主身份无效；未发布读取')
                created=datetime.fromisoformat(identity[2])
                if created.tzinfo is None:raise ToolReadError('invalid-host-identity','ENG宿主时间身份无效；未发布读取')
                if int(heartbeat['session'].split('-')[0])<created.timestamp()*1000:
                    raise ToolReadError('previous-host-heartbeat','ENG执行插件尚未属于当前PS进程；等待就绪，未发布读取')
        except (RuntimeError,OSError,ValueError):
            # No request exists yet: cold-start readiness must not wait for a key.
            if publish and not self.path.exists():self.retry_after=time.monotonic()+1
            raise
        if tuple(int(v) for v in heartbeat['probe_version'].split('.'))<(0,3,66):
            raise ToolReadError('executor-too-old','ENG工具编辑状态需要UXP0.3.66；未尝试切换')
        token=json.loads(self.transport.config.read_text('utf-8-sig'))['token']
        if self.path.exists():
            if self.path.stat().st_size>2048:raise ToolReadError('pending-invalid','ENG原观察身份损坏，未重发')
            request=json.loads(self.path.read_text('utf-8'))
            if (not isinstance(request,dict) or type(request.get('schema')) is not int or request['schema'] not in (1,2) or
                set(request)!=({'schema','id','session','expires_at_ms','publication'} if request['schema']==2 else {'schema','id','session','expires_at_ms'}) or
                request['schema']==2 and request['publication'] not in ('prepared','published') or
                not isinstance(request['id'],str) or len(request['id'])!=32 or
                any(c not in '0123456789abcdef' for c in request['id']) or
                not isinstance(request['session'],str) or not request['session'] or
                type(request['expires_at_ms']) not in (int,float) or not math.isfinite(request['expires_at_ms'])):
                raise ToolReadError('pending-invalid','ENG原观察身份损坏，未重发')
        else:
            if not publish:return None
            request={'schema':2,'id':secrets.token_hex(16),'session':heartbeat['session'],
                     'expires_at_ms':time.time()*1000+1000,'publication':'prepared'}
            atomic_json(self.path,request)
            wire={key:value for key,value in request.items() if key!='publication'};wire.update(schema=1,token=token)
            temporary=folder/('input-tool-request-'+request['id']+'.tmp')
            try:
                temporary.write_text(json.dumps(wire,ensure_ascii=False),'utf-8')
                publish_request(temporary,folder/'input-tool-request.json')
            except OSError as error:
                # This publisher cannot raise after an accepted atomic rename.
                atomic_json(self.path.with_name('input-tool-unpublished-'+request['id']+'.json'),
                    {'request':request,'publication_failed':True,'host_request_published':False,'error_type':type(error).__name__,'winerror':getattr(error,'winerror',None)})
                if json.loads(self.path.read_text('utf-8'))!=request:raise ToolReadError('pending-changed','ENG观察身份已变化，保留原记录') from error
                self.path.unlink();self.retry_after=time.monotonic()+1
                raise ToolReadError('publication-failed','ENG读取未发布；文件暂被占用，稍后重新观察当前状态') from error
            request={**request,'publication':'published'}
            atomic_json(self.path,request)
        if request['session']!=heartbeat['session']:raise ToolReadError('pending-session-changed','ENG观察会话变化；保留原身份，不重发')
        deadline=time.monotonic()+.5
        first=True
        while first or wait and time.monotonic()<deadline:
            first=False
            try:
                path=folder/'input-tool-response.json'
                if path.stat().st_size>4096:raise ToolReadError('response-too-large','ENG工具观察记录超限，未切换')
                value=json.loads(path.read_text('utf-8'))
                if isinstance(value,dict) and all(value.get(k)==v for k,v in {'schema':1,'id':request['id'],'session':request['session'],'token':token}.items()):
                    if value.get('phase') not in ('completed','failed'):raise ToolReadError('response-invalid','ENG观察终态无效')
                    stamp=value.get('completed_at_ms')
                    if type(stamp) not in (int,float) or not math.isfinite(stamp) or stamp>time.time()*1000:
                        raise ToolReadError('response-time-invalid','ENG观察终态时间无效，保留原身份')
                    if self.transport.observe()[1]['session']!=request['session']:raise ToolReadError('pending-session-changed','ENG观察会话变化')
                    if value['phase']=='completed' and (not isinstance(value.get('classID'),str) or
                        not value['classID'].isascii() or not value['classID'].isidentifier() or
                        not 1<=len(value['classID'])<=80 or type(value.get('isModal')) is not bool):
                        raise ToolReadError('response-fields-invalid','ENG观察终态字段无效，保留原身份')
                    failure=host_failure(value) if value['phase']=='failed' else {'reason':'tool-state-stale'} if time.time()*1000-stamp>500 else None
                    if failure:
                        atomic_json(self.path.with_name('input-tool-last-failure.json'),{'request':request,'failure':failure,'completed_at_ms':stamp})
                    self.path.unlink()
                    if failure:
                        self.retry_after=time.monotonic()+.2
                        raise ToolReadError(failure['reason'],'ENG工具状态失败／失鲜，未切换',failure)
                    self.retry_after=None
                    return {'classID':value['classID'],'isModal':value['isModal']}
            except (FileNotFoundError,PermissionError,json.JSONDecodeError):pass
            if wait:time.sleep(.01)
        raise ToolReadError('request-unconfirmed','ENG原工具观察尚未确认，保留身份；不重发或COM回退')
