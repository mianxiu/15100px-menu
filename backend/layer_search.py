"""Bounded read-only search; explicit result selection uses the durable UXP worker."""
import asyncio
import json
import secrets
import time
from .plugins import version
from .uxp_bridge import UxpBridge, read_heartbeat, publish_request

TYPES=('all','pixel','text','group','shape','smart-object','adjustment','fill','other')


def require_available(app):
    if not app.desktop:raise RuntimeError('此工具需要桌面服务')
    if not isinstance(app.bridge,UxpBridge):raise RuntimeError('此工具需要UXP执行插件')
    app.require_uxp_enabled()
    if app.operation_lock.locked() or app.bridge.busy or app.photoshop_launcher.active or app.stability.active:
        raise RuntimeError('操作进行中，本次请求未接受')


def query_parameters(args):
    value={key:args.get(key,default) for key,default in (('name',''),('document',''),('type','all'))}
    if any(not isinstance(value[key],str) or len(value[key])>200 for key in ('name','document')) or value['type'] not in TYPES:
        raise ValueError('无效的搜索条件')
    return value


class LayerSearch:
    def __init__(self, app):
        self.app=app
        self.searching=False
        self.result=None
        self.valid_until=0

    def available(self):
        require_available(self.app)

    async def search(self,args):
        query=query_parameters(args)
        self.available()
        if self.searching:raise RuntimeError('搜索进行中，请等待结果')
        self.searching=True
        self.result=None
        try:
            result=await asyncio.to_thread(self._read,query)
            self.result=result
            self.valid_until=time.monotonic()+60
            return result
        finally:self.searching=False

    def _read(self,query,preview=None):
        transport=self.app.bridge.transport
        folder,heartbeat=transport._discover()
        if version(heartbeat.get('probe_version'))<(0,3,57):raise RuntimeError('请更新并正常重启PS加载UXP0.3.57')
        if preview is not None and version(heartbeat.get('probe_version'))<(0,3,70):raise RuntimeError('请更新执行插件以读取图层预览')
        token=json.loads(transport.config.read_text('utf-8-sig'))['token']
        identity=secrets.token_hex(16)
        lifetime=3000 if preview is not None else 30000
        request={'token':token,'id':identity,'session':heartbeat['session'],'query':query,'expires_at_ms':int(time.time()*1000)+lifetime}
        if preview is not None:request['preview']=preview
        temporary=folder/(identity+'.search.tmp')
        temporary.write_text(json.dumps(request),'utf-8')
        publish_request(temporary,folder/'layer-search-request.json')
        deadline=time.monotonic()+lifetime/1000+1
        while time.monotonic()<deadline:
            if self.app.bridge.busy or self.app.operation_lock.locked():raise RuntimeError('菜单或操作已优先执行，请重新搜索')
            try:
                current=json.loads((folder/'layer-search-request.json').read_text('utf-8'))
                if current.get('id')!=identity:raise RuntimeError('新查找已取代本次读取')
                path=folder/'layer-search-result.json'
                if path.stat().st_size>4*1024*1024:raise ValueError('搜索结果超出限制')
                result=json.loads(path.read_text('utf-8-sig'))
                if result.get('schema')==1 and result.get('id')==identity and result.get('session')==heartbeat['session']:
                    if result.get('error'):raise RuntimeError(result['error'])
                    data=result.get('result')
                    if preview is not None:
                        if not isinstance(data,dict) or type(data.get('available')) is not bool:raise ValueError('图层预览结果不完整')
                        if not data['available'] and (not isinstance(data.get('reason'),str) or len(data['reason'])>300):raise ValueError('图层预览状态无效')
                        if data['available']:
                            width,height,pixels=data.get('width'),data.get('height'),data.get('pixels')
                            if (type(width) is not int or type(height) is not int or not 1<=width<=128 or not 1<=height<=128 or
                                    not isinstance(pixels,list) or len(pixels)!=width*height*4 or any(type(p) is not int or not 0<=p<=255 for p in pixels)):
                                raise ValueError('图层预览像素无效')
                        return data
                    if not isinstance(data,dict) or data.get('session')!=heartbeat['session'] or not isinstance(data.get('items'),list) or len(data['items'])>500:raise ValueError('搜索结果不完整')
                    return {**data,'search_id':identity,'message':'搜索完成'}
            except (OSError,json.JSONDecodeError):pass
            time.sleep(.025)
        raise RuntimeError('搜索超时，未修改文档；请重新搜索')

    def destination(self,args):
        result=self.result
        index=args.get('index')
        if not result or args.get('search_id')!=result['search_id'] or type(index) is not int or not 0<=index<len(result['items']) or time.monotonic()>self.valid_until:
            raise ValueError('搜索结果已过期，请重新搜索')
        return result,result['items'][index]

    async def preview(self,args):
        result,row=self.destination(args)
        self.available()
        return await asyncio.to_thread(self._read,{},row)

    async def focus(self,args,menu_guard=None):
        result,row=self.destination(args)
        self.available()
        app=self.app
        async with app.operation_lock:
            await app.broadcast({'type':'operation','busy':True,'action':'layer.focus'})
            try:
                if menu_guard:
                    await menu_guard()
                    await asyncio.to_thread(app.desktop.focus_search_result,keep_menu=True)
                else:await asyncio.to_thread(app.desktop.focus_search_result)
                value=await app.bridge.execute_focus(result['session'],row,**({'before_dispatch':menu_guard} if menu_guard else {}))
                app.desktop.layer_context=dict(app.bridge.layer_context)
                return value
            finally:await app.broadcast({'type':'operation','busy':app.bridge.busy})
