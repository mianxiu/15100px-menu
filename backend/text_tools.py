"""One selected text layer, read-only preview and explicit single-history commit."""
import asyncio
from .layer_search import require_available
from .operation_target import validate_target


def replace_parameters(value):
    if (not isinstance(value,dict) or set(value)!={'revision','find','replacement'} or
            not isinstance(value['revision'],str) or not 1<=len(value['revision'])<=128 or
            not isinstance(value['find'],str) or not 1<=len(value['find'])<=200 or
            not isinstance(value['replacement'],str) or len(value['replacement'])>500):
        raise ValueError('无效的文本替换参数')
    return dict(value)


def split_parameters(value):
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

    def available(self):
        require_available(self.app)

    async def read(self,args):
        self.available()
        if self.reading:raise RuntimeError('文字读取进行中，请等待结果')
        self.reading=True;self.snapshot=None
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

    async def split(self,args):
        return await self._apply(split_parameters(args),'text.split')

    async def _apply(self,params,command):
        self.available()
        snapshot=self.snapshot
        if not snapshot or params['revision']!=snapshot['revision']:raise ValueError('文本预览已过期，请重新读取')
        app=self.app
        async with app.operation_lock:
            await app.broadcast({'type':'operation','busy':True,'action':command})
            try:
                await asyncio.to_thread(app.desktop.focus_search_result)
                result=await app.bridge.execute_text(snapshot['target'],params,command)
                self.snapshot=None
                app.desktop.layer_context=dict(app.bridge.layer_context)
                return result
            finally:await app.broadcast({'type':'operation','busy':app.bridge.busy})
