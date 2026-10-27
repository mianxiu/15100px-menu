"""One selected text layer, read-only preview and explicit single-history commit."""
import asyncio
import secrets
from .layer_search import require_available
from .operation_target import validate_target
from .text_plan import evaluate,parameters,units


def mapped_parameters(value,split=False):
    keys={'revision','value','origins','count'}|({'breaks','layout'} if split else set())
    if (not isinstance(value,dict) or set(value)!=keys or not isinstance(value['revision'],str) or not 1<=len(value['revision'])<=128 or
            not isinstance(value['value'],str) or not 1<=units(value['value'])<=20000 or '\0' in value['value'] or '\n' in value['value'] or
            type(value['count']) is not int or not 0<=value['count']<=40001 or not isinstance(value['origins'],list) or
            len(value['origins'])!=units(value['value'])+1 or any(type(origin) is not int or not 0<=origin<=20000 or index and origin<value['origins'][index-1] for index,origin in enumerate(value['origins']))):
        raise ValueError('无效的文字预览计划')
    if split:
        split_parameters({'revision':value['revision'],'breaks':value['breaks']})
        if value['breaks'][-1]!=units(value['value']) or value['layout'] not in ('original','lines'):raise ValueError('无效的文字拆分布局')
    return {**value,'origins':list(value['origins']),**({'breaks':list(value['breaks'])} if split else {})}


def replace_parameters(value):
    if isinstance(value,dict) and 'value' in value:return mapped_parameters(value)
    if (not isinstance(value,dict) or set(value)!={'revision','find','replacement'} or
            not isinstance(value['revision'],str) or not 1<=len(value['revision'])<=128 or
            not isinstance(value['find'],str) or not 1<=len(value['find'])<=200 or
            not isinstance(value['replacement'],str) or len(value['replacement'])>500):
        raise ValueError('无效的文本替换参数')
    return dict(value)


def split_parameters(value):
    if isinstance(value,dict) and 'value' in value:return mapped_parameters(value,split=True)
    if (not isinstance(value,dict) or set(value)!={'revision','breaks'} or
            not isinstance(value['revision'],str) or not 1<=len(value['revision'])<=128 or
            not isinstance(value['breaks'],list) or not 2<=len(value['breaks'])<=64 or
            any(type(end) is not int or not 1<=end<=20000 or index and end<=value['breaks'][index-1] for index,end in enumerate(value['breaks']))):
        raise ValueError('无效的文字分组参数')
    return {'revision':value['revision'],'breaks':list(value['breaks'])}


class TextTools:
    def __init__(self,app):
        self.app=app
        self.snapshot=None
        self.reading=False
        self.plan=None

    def available(self):
        require_available(self.app)

    async def read(self,args):
        self.available()
        if self.reading:raise RuntimeError('文字读取进行中，请等待结果')
        self.reading=True;self.snapshot=None;self.plan=None
        try:
            result=await asyncio.to_thread(self.app.bridge.transport.call,'inspect',text_inspect=True)
            snapshot=result.get('text')
            if (not isinstance(snapshot,dict) or not isinstance(snapshot.get('text'),str) or len(snapshot['text'])>20000 or
                    not isinstance(snapshot.get('revision'),str) or not 1<=len(snapshot['revision'])<=128 or
                    not isinstance(snapshot.get('name'),str) or len(snapshot['name'])>2000):
                raise RuntimeError('文字读取结果不完整')
            target=validate_target(snapshot.get('target'))
            if len(target['layer_ids'])!=1 or snapshot['target'].get('session')!=result.get('session'):
                raise RuntimeError('文字读取会话不一致')
            self.snapshot=snapshot
            return {**snapshot,'message':'文字已读取；预览不会修改PS'}
        finally:self.reading=False

    async def replace(self,args):
        return await self._apply(replace_parameters(args),'text.replace')

    async def split(self,args,menu_guard=None):
        return await self._apply(split_parameters(args),'text.split',menu_guard)

    async def preview(self,args):
        self.available();params=parameters(args);saved=self.snapshot;self.plan=None
        if not saved or params['revision']!=saved['revision']:raise ValueError('文字读取已过期，请重新读取')
        result=await asyncio.to_thread(evaluate,saved['text'],params)
        if self.snapshot is not saved:raise ValueError('文字读取已改变，请重新预览')
        split=result['kind']=='split'
        payload={key:result[key] for key in ({'value','origins','count','breaks','layout'} if split else {'value','origins','count'})}
        payload['revision']=saved['revision'];payload=mapped_parameters(payload,split)
        identity=secrets.token_hex(16);self.plan=(identity,payload,'text.split' if split else 'text.replace')
        return {key:result[key] for key in ('preview','value','count','changed','kind','characters','matches')}|{'plan_id':identity}

    async def apply(self,args,menu_guard=None):
        if not isinstance(args,dict) or set(args)!={'revision','plan_id'} or not self.plan or (args['plan_id'],args['revision'])!=(self.plan[0],self.plan[1]['revision']):
            raise ValueError('预览已改变，请重新计算后确认')
        _,params,command=self.plan;self.plan=None
        return await self._apply(params,command,menu_guard)

    async def _apply(self,params,command,menu_guard=None):
        self.available()
        snapshot=self.snapshot
        if not snapshot or params['revision']!=snapshot['revision']:raise ValueError('文本预览已过期，请重新读取')
        app=self.app
        async with app.operation_lock:
            await app.broadcast({'type':'operation','busy':True,'action':command})
            try:
                if menu_guard:
                    await menu_guard()
                    await asyncio.to_thread(app.desktop.focus_search_result,keep_menu=True)
                else:await asyncio.to_thread(app.desktop.focus_search_result)
                result=await app.bridge.execute_text(snapshot['target'],params,command,**({'before_dispatch':menu_guard} if menu_guard else {}))
                self.snapshot=None;self.plan=None
                app.desktop.layer_context=dict(app.bridge.layer_context)
                return result
            finally:await app.broadcast({'type':'operation','busy':app.bridge.busy})
