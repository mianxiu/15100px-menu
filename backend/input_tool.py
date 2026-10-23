"""One authenticated, read-only tool observation; unknown requests are not republished."""
import json
import math
import secrets
import time
from .settings import atomic_json


class ToolObservation:
    def __init__(self,transport):
        self.transport=transport
        self.path=transport.config.parent/'input-tool-pending.json'

    def read(self):
        folder,heartbeat=self.transport.observe()
        if tuple(int(v) for v in heartbeat['probe_version'].split('.'))<(0,3,66):
            raise RuntimeError('ENG工具编辑状态需要UXP0.3.66；未尝试切换')
        token=json.loads(self.transport.config.read_text('utf-8-sig'))['token']
        if self.path.exists():
            if self.path.stat().st_size>2048:raise RuntimeError('ENG原观察身份损坏，未重发')
            request=json.loads(self.path.read_text('utf-8'))
            if (not isinstance(request,dict) or set(request)!={'schema','id','session','expires_at_ms'} or type(request['schema']) is not int or request['schema']!=1 or
                not isinstance(request['id'],str) or len(request['id'])!=32 or
                any(c not in '0123456789abcdef' for c in request['id']) or
                not isinstance(request['session'],str) or not request['session'] or
                type(request['expires_at_ms']) not in (int,float) or not math.isfinite(request['expires_at_ms'])):
                raise RuntimeError('ENG原观察身份损坏，未重发')
        else:
            request={'schema':1,'id':secrets.token_hex(16),'session':heartbeat['session'],
                     'expires_at_ms':time.time()*1000+1000}
            atomic_json(self.path,request)
            atomic_json(folder/'input-tool-request.json',{**request,'token':token})
        if request['session']!=heartbeat['session']:raise RuntimeError('ENG观察会话变化；保留原身份，不重发')
        deadline=time.monotonic()+.5
        while time.monotonic()<deadline:
            try:
                path=folder/'input-tool-response.json'
                if path.stat().st_size>4096:raise RuntimeError('ENG工具观察记录超限，未切换')
                value=json.loads(path.read_text('utf-8'))
                if isinstance(value,dict) and all(value.get(k)==v for k,v in {**request,'token':token}.items() if k!='expires_at_ms'):
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
                        raise RuntimeError('ENG工具状态失败／失鲜，未切换')
                    return {'classID':value['classID'],'isModal':value['isModal']}
            except (FileNotFoundError,PermissionError,json.JSONDecodeError):pass
            time.sleep(.01)
        raise RuntimeError('ENG原工具观察尚未确认，保留身份；不重发或COM回退')
