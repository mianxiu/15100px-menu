"""Native PDF generation under the durable UXP reservation, never a retry path."""
import json
from . import text_object
from .paths import ROOT


def invoke(application,folder,request,prepared,model,xmp):
    if (request.get('command')!='text.object' or prepared.get('phase')!='prepared' or
            any(prepared.get(k)!=request.get(k) for k in ('id','session','operation','token'))):
        raise ValueError('文字对象执行身份不一致')
    text_object.source(model)
    if text_object.read(xmp)!=model:raise ValueError('文字对象源与显示草稿不一致')
    value={**request,'folder':str(folder),'prepared':prepared['prepared'],'source':model,'xmp':xmp}
    source=(ROOT/'jsx/text_object.jsx').read_text('utf-8').replace('__PS_MENU_TEXT_HASH_HELPER__',(ROOT/'jsx/text_object_sha256.jsx').read_text('utf-8'))
    return application.DoJavaScript(source.replace('__PS_MENU_TEXT_OBJECT_REQUEST__',json.dumps(value,ensure_ascii=True,allow_nan=False)))
