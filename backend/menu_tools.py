"""Caps-owned views of the existing search and single-history text tools."""
import asyncio
from .layer_search import LayerSearch, require_available
from .text_tools import TextTools


class MenuTools:
    def __init__(self, app):
        self.app=app
        self.epoch=None
        self.pending=False
        self.last_request=0
        self.preview_request=None
        self.search=LayerSearch(app)
        self.text=TextTools(app)

    async def open(self,args):
        params=args.get('params',{})
        if not isinstance(params,dict) or set(params)-{'mode'}:raise ValueError('无效的工具参数')
        epoch=args.get('menu_epoch')
        if epoch is not None and (type(epoch) is not int or epoch<=0):raise ValueError('无效的菜单会话')
        mode=params.get('mode','search')
        if mode not in ('search','split'):raise ValueError('未知的Caps工具')
        require_available(self.app)
        if self.pending or self.app.panel_lock.locked():raise RuntimeError('工具正在处理，本次未接受')
        async with self.app.panel_lock:
            epoch=await asyncio.to_thread(self.app.desktop.open_menu_tools,mode,args.get('menu_epoch'))
            require_available(self.app)
            self.epoch=epoch
            self.last_request=0
            self.search=LayerSearch(self.app);self.text=TextTools(self.app)
            self.app.desktop.event({'type':'menu.tools.opened','epoch':epoch,'mode':mode})
        return {'message':'Caps工具已打开','epoch':epoch}

    async def request(self,args):
        epoch=args.get('menu_epoch');value=args.get('params',{})
        if (type(epoch) is not int or epoch<=0 or not isinstance(value,dict) or set(value)!={'request','action','args'} or
                type(value['request']) is not int or not 1<=value['request']<=2147483647 or
                value['action'] not in ('layers.search','layers.focus','text.read','text.split','text.preview','text.apply','text.write') or not isinstance(value['args'],dict)):
            raise ValueError('无效的Caps工具请求')
        async def guard(_target=None):
            if epoch != self.epoch:raise RuntimeError('工具会话已改变，本次未执行')
            await asyncio.to_thread(self.app.desktop.require_menu_tools,epoch)
        event={'type':'menu.tools.result','epoch':epoch,'request':value['request'],'action':value['action']}
        if self.pending and epoch==self.epoch and value['request']==self.last_request:return {'message':'已忽略重复工具请求'}
        if self.pending or self.preview_request is not None:
            self.app.desktop.event({**event,'ok':False,'error':'操作进行中，本次请求未接受'})
            return {'message':'操作进行中'}
        self.pending=True
        try:
            await guard();require_available(self.app)
            if value['request']<=self.last_request:raise RuntimeError('已忽略重复工具请求')
            self.last_request=value['request']
            action,params=value['action'],value['args']
            if action=='layers.search':
                result=await self.search.search(params)
                await guard()
                await asyncio.to_thread(self.app.desktop.resize_menu_tools,epoch,len(result['items']))
            elif action=='layers.focus':result=await self.search.focus(params,menu_guard=guard)
            elif action=='text.read':
                result=await self.text.read(params)
                await guard()
                target=self.app.desktop.menu_layer_context or {}
                if any(target.get(key)!=result['target'].get(key) for key in ('session','document_id','layer_ids')):
                    self.text.snapshot=None
                    raise RuntimeError('文字目标已改变，请重新打开菜单')
            elif action=='text.preview':
                result=await self.text.preview(params)
                await guard()
            elif action=='text.apply':result=await self.text.apply(params,menu_guard=guard)
            elif action=='text.write':result=await self.text.write(params,menu_guard=guard)
            else:result=await self.text.split(params,menu_guard=guard)
            self.app.desktop.event({**event,'ok':True,'result':result})
            if action in ('text.split','text.apply','text.write','layers.focus'):
                await self.app.broadcast({'type':'notice','scope':'operation','ok':True,'message':result['message']})
            return result
        except Exception as error:
            self.app.desktop.event({**event,'ok':False,'error':str(error)})
            if value['action'] in ('text.split','text.apply','text.write','layers.focus'):
                await self.app.broadcast({'type':'notice','scope':'operation','ok':False,'message':str(error)})
            return {'message':str(error),'error':str(error)}
        finally:self.pending=False

    async def preview(self,args):
        epoch=args.get('menu_epoch');params=args.get('params',{})
        if (type(epoch) is not int or epoch<=0 or not isinstance(params,dict) or set(params)!={'request','search_id','index'} or
                type(params['request']) is not int or not 1<=params['request']<=2147483647):raise ValueError('无效的图层预览请求')
        event={'type':'menu.tools.preview.result','epoch':epoch,'request':params['request']}
        identity=(epoch,params['request'])
        if self.preview_request==identity:return {'error':'已忽略重复预览请求'}
        acquired=False
        try:
            if self.preview_request is not None or self.pending:raise RuntimeError('查找或预览读取中，本次未接受')
            if epoch!=self.epoch:raise RuntimeError('查找已关闭或重新打开')
            await asyncio.to_thread(self.app.desktop.require_menu_tools,epoch)
            require_available(self.app);self.preview_request=identity;acquired=True
            async def guard(_target=None):
                if epoch!=self.epoch:raise RuntimeError('查找已关闭或重新打开')
                await asyncio.to_thread(self.app.desktop.require_menu_tools,epoch)
            result=await self.search.preview(params,menu_guard=guard)
            if epoch!=self.epoch:return {'message':'已忽略旧预览'}
            await asyncio.to_thread(self.app.desktop.require_menu_tools,epoch)
            self.app.desktop.event({**event,'ok':True,'result':result})
            return {'message':'预览已读取'}
        except Exception as error:
            self.app.desktop.event({**event,'ok':False,'error':str(error)})
            return {'error':str(error)}
        finally:
            if acquired and self.preview_request==identity:self.preview_request=None
