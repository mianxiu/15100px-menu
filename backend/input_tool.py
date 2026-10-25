"""One authenticated, read-only tool observation; unknown requests are not republished."""
import json
import math
import secrets
import time
from .settings import atomic_json
from .uxp_bridge import publish_request


class ToolObservation:
    def __init__(self,transport):
        self.transport=transport
        self.path=transport.config.parent/'input-tool-pending.json'
        self.retry_after=None

    def reconcile(self):
        if self.path.exists():
            try:self.read(publish=False,wait=False)
            except RuntimeError:pass
            return not self.path.exists()
        if self.retry_after is not None and time.monotonic()>=self.retry_after:
            self.retry_after=None;return True
        return False

    def read(self,publish=True,wait=True):
        folder,heartbeat=self.transport.observe()
        if tuple(int(v) for v in heartbeat['probe_version'].split('.'))<(0,3,66):
            raise RuntimeError('ENG工具编辑状态需要UXP0.3.66；未尝试切换')
        token=json.loads(self.transport.config.read_text('utf-8-sig'))['token']
        if self.path.exists():
            if self.path.stat().st_size>2048:raise RuntimeError('ENG原观察身份损坏，未重发')
            request=json.loads(self.path.read_text('utf-8'))
            if (not isinstance(request,dict) or type(request.get('schema')) is not int or request['schema'] not in (1,2) or
                set(request)!=({'schema','id','session','expires_at_ms','publication'} if request['schema']==2 else {'schema','id','session','expires_at_ms'}) or
                request['schema']==2 and request['publication'] not in ('prepared','published') or
                not isinstance(request['id'],str) or len(request['id'])!=32 or
                any(c not in '0123456789abcdef' for c in request['id']) or
                not isinstance(request['session'],str) or not request['session'] or
                type(request['expires_at_ms']) not in (int,float) or not math.isfinite(request['expires_at_ms'])):
                raise RuntimeError('ENG原观察身份损坏，未重发')
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
                if json.loads(self.path.read_text('utf-8'))!=request:raise RuntimeError('ENG观察身份已变化，保留原记录') from error
                self.path.unlink();self.retry_after=time.monotonic()+1
                raise RuntimeError('ENG读取未发布；文件暂被占用，稍后重新观察当前状态') from error
            request={**request,'publication':'published'}
            atomic_json(self.path,request)
        if request['session']!=heartbeat['session']:raise RuntimeError('ENG观察会话变化；保留原身份，不重发')
        deadline=time.monotonic()+.5
        first=True
        while first or wait and time.monotonic()<deadline:
            first=False
            try:
                path=folder/'input-tool-response.json'
                if path.stat().st_size>4096:raise RuntimeError('ENG工具观察记录超限，未切换')
                value=json.loads(path.read_text('utf-8'))
                if isinstance(value,dict) and all(value.get(k)==v for k,v in {'schema':1,'id':request['id'],'session':request['session'],'token':token}.items()):
                    if value.get('phase') not in ('completed','failed'):raise RuntimeError('ENG观察终态无效')
                    stamp=value.get('completed_at_ms')
                    if type(stamp) not in (int,float) or not math.isfinite(stamp) or stamp>time.time()*1000:
                        raise RuntimeError('ENG观察终态时间无效，保留原身份')
                    if self.transport.observe()[1]['session']!=request['session']:raise RuntimeError('ENG观察会话变化')
                    if value['phase']=='completed' and (not isinstance(value.get('classID'),str) or
                        not value['classID'].isascii() or not value['classID'].isidentifier() or
                        not 1<=len(value['classID'])<=80 or type(value.get('isModal')) is not bool):
                        raise RuntimeError('ENG观察终态字段无效，保留原身份')
                    self.path.unlink()
                    if value['phase']!='completed' or time.time()*1000-stamp>500:
                        self.retry_after=time.monotonic()+.2
                        raise RuntimeError('ENG工具状态失败／失鲜，未切换')
                    self.retry_after=None
                    return {'classID':value['classID'],'isModal':value['isModal']}
            except (FileNotFoundError,PermissionError,json.JSONDecodeError):pass
            if wait:time.sleep(.01)
        raise RuntimeError('ENG原工具观察尚未确认，保留身份；不重发或COM回退')
