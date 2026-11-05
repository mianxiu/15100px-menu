"""Offline vector list pages: fixed body columns, independent of PS paragraph engines."""
import asyncio
import base64
import html
import json
import math
import os
from pathlib import Path
import re
import struct
import shutil
import subprocess
import sys
import tempfile
import time
from . import text_object,text_list


def edge_path():
    for root in ('PROGRAMFILES(X86)','PROGRAMFILES'):
        path=Path(os.environ.get(root,'C:/Program Files (x86)' if root.endswith('(X86)') else 'C:/Program Files'))/'Microsoft/Edge/Application/msedge.exe'
        if path.is_file():return path
    raise ValueError('智能文字对象需要本机 Microsoft Edge 排版组件；不需要联网或登录')


def inherited(value):
    return {**(inherited(value['baseParentStyle']) if value.get('baseParentStyle') else {}),**value}


def private_font(postscript):
    # PS ships some fonts privately; they are not visible through CSS local().
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',postscript):return None
    from .photoshop_version import installed_paths
    for executable in installed_paths():
        font=Path(executable).parent/'Required/PDFL/Resource/Fonts'/(postscript+'.otf')
        if not font.is_file():continue
        if not 12<=font.stat().st_size<=16777216:raise ValueError('PS字体文件超出上限')
        value=font.read_bytes();count=struct.unpack_from('>H',value,4)[0]
        if 12+count*16>len(value):raise ValueError('PS字体目录无效')
        tables={}
        for i in range(count):
            tag,_,offset,size=struct.unpack_from('>4sIII',value,12+i*16)
            if offset+size>len(value):raise ValueError('PS字体数据无效')
            tables[tag]=(offset,size)
        if b'name' not in tables:raise ValueError('PS字体身份缺失')
        offset,size=tables[b'name'];_,records,strings=struct.unpack_from('>HHH',value,offset);names=[]
        if 6+records*12>size:raise ValueError('PS字体名称目录无效')
        for i in range(records):
            platform,encoding,_,name,length,start=struct.unpack_from('>HHHHHH',value,offset+6+i*12)
            if name!=6:continue
            if strings+start+length>size:raise ValueError('PS字体名称无效')
            raw=value[offset+strings+start:offset+strings+start+length]
            try:names.append(raw.decode('utf-16-be' if platform in (0,3) else 'mac-roman'))
            except UnicodeError:continue
        if postscript not in names:raise ValueError('PS字体文件身份不一致')
        if b'OS/2' in tables:
            at,length=tables[b'OS/2']
            if length<10 or struct.unpack_from('>H',value,at+8)[0]&2:raise ValueError('该字体不允许嵌入矢量输出')
        return base64.b64encode(value).decode('ascii')
    return None


def page(model):
    text_object.source(model)
    canvas=model['canvas'];raw=model['layer']['text'];dpi=canvas['resolution'];scale=96/dpi
    shape=raw.get('textShape',[{}])[0];transform=raw.get('transform',{})
    if (canvas['mode']!='RGB' or canvas['depth']!=8 or canvas['profile']!='sRGB IEC61966-2.1' or
            raw.get('orientation',{}).get('_value')!='horizontal' or len(raw.get('textShape',[]))!=1 or
            shape.get('char',{}).get('_value') not in ('box','paint') or raw.get('warp',{}).get('warpStyle',{}).get('_value')!='warpNone' or
            any(abs(transform.get(k,default)-default)>1e-6 for k,default in [('xx',1),('yy',1),('xy',0),('yx',0)]) or
            shape.get('columnCount',1)!=1 or shape.get('rowCount',1)!=1):
        raise ValueError('智能文字对象目前支持 sRGB／8位、水平未变形的单栏普通文字')
    def number(v,default=0):
        if v is None:return default
        # batchPlay normalizes untagged text-shape bounds to document pixels.
        if type(v) in (float,int):return float(v)*scale
        unit=v.get('_unit');value=v.get('_value')
        if type(value) not in (float,int) or unit not in ('pixelsUnit','pointsUnit'):raise ValueError('文字尺寸单位不受支持')
        return value*(96/72 if unit=='pointsUnit' else scale)
    runs=raw['textStyleRange'];fonts={}
    def css(style,paragraph):
        style=inherited(style);font=style.get('fontPostScriptName')
        if not isinstance(font,str) or not font or style.get('fontAvailable') is False:raise ValueError('文字字体不可用')
        if style.get('horizontalScale',100)!=100 or style.get('verticalScale',100)!=100:raise ValueError('智能文字对象暂不支持字符单独拉伸')
        if font not in fonts:fonts[font]={'name':'pxfont'+str(len(fonts)),'local':[font,' '.join(str(style.get(k,'')) for k in ('fontName','fontStyleName')).strip()]}
        size=number(style.get('size'))
        if not 0<size<=2000:raise ValueError('文字字号超出范围')
        color=style.get('color',{});channels=[color.get(k,0) for k in ('red','green','blue')]
        if color.get('_obj') not in (None,'RGBColor') or any(type(v) not in (int,float) or not 0<=v<=255 for v in channels):raise ValueError('智能文字对象需要RGB文字颜色')
        leading=size*float(paragraph.get('autoLeading',120))/100 if style.get('autoLeading',True) else number(style.get('leading'))
        if not math.isfinite(leading) or leading<=0:raise ValueError('文字行距无效')
        return {'font':fonts[font]['name'],'size':size,'leading':leading,
                'css':f'font-family:{fonts[font]["name"]};font-size:{size}px;line-height:{leading}px;color:rgb({",".join(str(v) for v in channels)});letter-spacing:{float(style.get("tracking",0))/1000}em;'+
                ('font-weight:bold;' if style.get('syntheticBold') else '')+('font-style:italic;' if style.get('syntheticItalic') else '')}
    text=raw['textKey'];offsets=[0]
    for char in text:offsets.append(offsets[-1]+len(char.encode('utf-16-le'))//2)
    def spans(start,end,paragraph):
        result=[]
        for run in runs:
            first=max(offsets[start],run['from']);last=min(offsets[end],run['to'])
            if last<=first:continue
            fragment=text.encode('utf-16-le')[first*2:last*2].decode('utf-16-le')
            style=css(run['textStyle'],paragraph)
            result.append('<span style="'+html.escape(style['css'],quote=True)+'">'+html.escape(fragment)+'</span>')
        return ''.join(result)
    options=text_list.read(model['layer']['xmp']);rows=[];start=0;paragraphs=raw['paragraphStyleRange'];index=0
    for line in text.split('\r'):
        while index<len(paragraphs)-1 and offsets[start]>=paragraphs[index]['to']:index+=1
        paragraph=inherited(paragraphs[index]['paragraphStyle'])
        if paragraph.get('align',{}).get('_value','left')!='left':raise ValueError('智能列表目前需要左对齐段落')
        content=start;marker='';level=len(line)-len(line.lstrip(' '));level=min(5,level//4)
        if options and line.strip():
            match=re.match(r'^ *(.*?)\t',line)
            if not match:raise ValueError('列表标记缺少正文分隔，请在列表页重新生成')
            marker=match[1];content=start+match.end()
        style=css(next(run['textStyle'] for run in runs if run['from']<=offsets[min(content,len(text)-1)]<run['to']),paragraph)
        if marker and any(ord(c)>127 for c in marker):
            if not text_list.symbol_glyphs(marker):raise ValueError('列表符号字体不含所需字形')
            fonts.setdefault('SegoeUISymbol',{'name':'pxfontSymbol','local':['SegoeUISymbol','Segoe UI Symbol']})
            marker_css=style['css']+'font-family:'+fonts['SegoeUISymbol']['name']+';'
        else:marker_css=style['css']
        rows.append({'html':f'<div class="row" data-level="{level}" style="font-size:{style["size"]}px;line-height:{style["leading"]}px;margin-top:{number(paragraph.get("spaceBefore"))}px;margin-bottom:{number(paragraph.get("spaceAfter"))}px"><span class="marker" style="{html.escape(marker_css,quote=True)}">{html.escape(marker)}</span><div class="body">{spans(content,start+len(line),paragraph) or "<br>"}</div></div>', 'list':bool(marker)})
        start+=len(line)+1
    click=raw.get('textClickPoint',{});x=click.get('horizontal',{});y=click.get('vertical',{})
    if x.get('_unit')!='percentUnit' or y.get('_unit')!='percentUnit':raise ValueError('文字锚点单位不受支持')
    width=canvas['width']*scale;height=canvas['height']*scale;left=x['_value']*width/100;top=y['_value']*height/100
    box=shape.get('bounds',{});box_width=number(box.get('right'))-number(box.get('left')) if shape['char']['_value']=='box' else width-left
    box_height=number(box.get('bottom'))-number(box.get('top')) if shape['char']['_value']=='box' else height-top
    if not 1<=box_width<=width or not 1<=box_height<=height:raise ValueError('文字框超出画布或没有可用尺寸')
    data={'fonts':list(fonts.values()),'rows':[v['list'] for v in rows],'height':box_height,'point':shape['char']['_value']=='paint'}
    if len(fonts)>32:raise ValueError('智能文字对象最多使用32款字体')
    for font,item in fonts.items():item['data']=private_font(font)
    if sum(len(item.get('data') or '') for item in fonts.values())>33554432:raise ValueError('文字字体数据超出上限')
    script='const DATA='+json.dumps(data,ensure_ascii=True).replace('<','\u003c')+';'+r'''(async()=>{try{
      for(const item of DATA.fonts){let loaded=null;if(item.data)loaded=await new FontFace(item.name,Uint8Array.from(atob(item.data),c=>c.charCodeAt(0))).load();else for(const name of item.local){try{loaded=await new FontFace(item.name,'local('+JSON.stringify(name)+')').load();break;}catch(_){}}if(!loaded)throw Error('本机排版组件无法读取字体：'+item.local[0]);document.fonts.add(loaded);}
      await document.fonts.ready;
      const rows=[...document.querySelectorAll('.row')],columns=new Map(),geometry=[];
      for(const row of rows){const marker=row.querySelector('.marker');const em=parseFloat(getComputedStyle(row).fontSize);if(marker.textContent)columns.set(row.dataset.level,Math.max(columns.get(row.dataset.level)||0,marker.getBoundingClientRect().width+em*.5));}
      for(const row of rows){const marker=row.querySelector('.marker'),body=row.querySelector('.body'),em=parseFloat(getComputedStyle(row).fontSize),level=Number(row.dataset.level),indent=marker.textContent?level*em*2:0,column=columns.get(row.dataset.level)||0;row.style.marginLeft=indent+'px';marker.style.width=column+'px';marker.style.paddingRight=marker.textContent?em*.5+'px':'0px';body.style.width='calc(100% - '+column+'px)';}
      if(DATA.point){const first=rows[0].querySelector('.body span'),c=document.createElement('canvas').getContext('2d'),s=getComputedStyle(first);c.font=s.font;const m=c.measureText('Mg'),ascent=m.fontBoundingBoxAscent||m.actualBoundingBoxAscent,descent=m.fontBoundingBoxDescent||m.actualBoundingBoxDescent;document.querySelector('#text').style.transform='translateY(-'+(ascent+(parseFloat(s.lineHeight)-ascent-descent)/2)+'px)';}
      const area=document.querySelector('#text');for(const row of rows){const b=row.querySelector('.body').getBoundingClientRect();if(b.width<1||row.scrollWidth>row.clientWidth+1)throw Error('列表缩进后正文宽度不足');geometry.push({level:Number(row.dataset.level),x:b.x,y:b.y,width:b.width,height:b.height});}
      if(area.scrollHeight>DATA.height+1||area.getBoundingClientRect().bottom>document.documentElement.clientHeight+1)throw Error('列表超出文字框，请减少内容或增加文字框高度');
      window.__vectorResult={ok:true,geometry};
    }catch(e){window.__vectorResult={ok:false,error:String(e.message||e)};}})();'''
    document=f'<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; script-src \'unsafe-inline\'; font-src \'self\'"><style>@page{{size:{width}px {height}px;margin:0}}html,body{{margin:0;width:{width}px;height:{height}px}}*{{box-sizing:border-box}}#text{{position:absolute;left:{left}px;top:{top}px;width:{box_width}px}}.row{{display:flex;align-items:baseline;break-inside:avoid}}.marker{{display:block;flex:none;white-space:pre;text-align:right}}.body{{flex:1;min-width:0;white-space:pre-wrap;overflow-wrap:anywhere}}</style></head><body><div id="text">'+''.join(v['html'] for v in rows)+'</div><script>'+script+'</script></body></html>'
    return document,width,height


def render(model,folder,identity):
    document,width,height=page(model);folder=Path(folder)
    page_path=folder/('text-object-page-'+identity+'.html');pdf_path=folder/('text-object-'+identity+'.pdf')
    if page_path.exists() or pdf_path.exists():raise FileExistsError('文字对象输出身份已存在；保留原记录')
    page_path.write_text(document,'utf-8')
    import win32api,win32con,win32event,win32job,win32process
    profile=Path(tempfile.mkdtemp(prefix='photoshop-vector-'));process=None;ws=None;assigned=False
    job=win32job.CreateJobObject(None,'');limits=win32job.QueryInformationJobObject(job,win32job.JobObjectExtendedLimitInformation)
    limits['BasicLimitInformation']['LimitFlags']|=win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;win32job.SetInformationJobObject(job,win32job.JobObjectExtendedLimitInformation,limits)
    async def run():
        nonlocal process,ws,assigned
        from tornado.httpclient import HTTPRequest
        from tornado.websocket import websocket_connect
        command=[str(edge_path()),'--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--disable-background-networking','--disable-component-update','--disable-extensions','--remote-debugging-address=127.0.0.1','--remote-debugging-port=0','--user-data-dir='+str(profile),'about:blank']
        # Frozen Python's DLL directory must not leak into the system browser.
        import ctypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True);kernel.GetDllDirectoryW.argtypes=[ctypes.c_uint,ctypes.c_wchar_p];kernel.SetDllDirectoryW.argtypes=[ctypes.c_wchar_p]
        old=ctypes.create_unicode_buffer(32768);kernel.GetDllDirectoryW(len(old),old)
        if getattr(sys,'frozen',False) and not kernel.SetDllDirectoryW(None):raise OSError(ctypes.get_last_error(),'Cannot isolate browser DLL search')
        try:
            process,thread,_,_=win32process.CreateProcess(None,subprocess.list2cmdline(command),None,None,False,win32con.CREATE_SUSPENDED|win32con.CREATE_NO_WINDOW,None,None,win32process.STARTUPINFO())
            try:win32job.AssignProcessToJobObject(job,process);assigned=True;win32process.ResumeThread(thread)
            finally:thread.Close()
        finally:
            if getattr(sys,'frozen',False) and not kernel.SetDllDirectoryW(old.value or None):raise OSError(ctypes.get_last_error(),'Cannot restore application DLL search')
        deadline=time.monotonic()+15
        port=profile/'DevToolsActivePort'
        while not port.exists():
            if win32event.WaitForSingleObject(process,0)==0 or time.monotonic()>deadline:raise ValueError('本机文字排版组件启动失败：'+str(win32process.GetExitCodeProcess(process)))
            await asyncio.sleep(.04)
        lines=port.read_text('utf-8').splitlines();ws=await websocket_connect(HTTPRequest('ws://127.0.0.1:'+lines[0]+lines[1],connect_timeout=3),max_message_size=33554432)
        serial=0
        async def call(method,params=None,session=None):
            nonlocal serial
            serial+=1;identity=serial;request={'id':identity,'method':method,'params':params or {}}
            if session:request['sessionId']=session
            await ws.write_message(json.dumps(request))
            while True:
                value=await asyncio.wait_for(ws.read_message(),15)
                if value is None:raise ValueError('本机文字排版组件提前退出')
                value=json.loads(value)
                if value.get('id')==identity:
                    if 'error' in value:raise ValueError('本机文字排版失败：'+str(value['error'].get('message')))
                    return value.get('result',{})
        try:
            target=(await call('Target.createTarget',{'url':'about:blank'}))['targetId'];session=(await call('Target.attachToTarget',{'targetId':target,'flatten':True}))['sessionId']
            if max(width,height)>32768:raise ValueError('文字画布超过排版组件范围')
            await call('Page.enable',session=session)
            await call('Emulation.setDeviceMetricsOverride',{'width':math.ceil(width),'height':math.ceil(height),'deviceScaleFactor':1,'mobile':False},session)
            await call('Page.navigate',{'url':page_path.as_uri()},session)
            result=None
            for _ in range(150):
                value=await call('Runtime.evaluate',{'expression':'window.__vectorResult||null','returnByValue':True},session);result=value.get('result',{}).get('value')
                if result is not None:break
                await asyncio.sleep(.04)
            if not result or not result.get('ok'):raise ValueError((result or {}).get('error','本机字体加载超时'))
            output=await call('Page.printToPDF',{'printBackground':True,'displayHeaderFooter':False,'preferCSSPageSize':True,'paperWidth':width/96,'paperHeight':height/96,'marginTop':0,'marginBottom':0,'marginLeft':0,'marginRight':0},session)
            pdf=base64.b64decode(output['data'],validate=True)
            if not pdf.startswith(b'%PDF-') or not 100<=len(pdf)<=16777216:raise ValueError('矢量输出格式或尺寸无效')
            with pdf_path.open('xb') as file:file.write(pdf)
            (folder/('text-object-layout-'+identity+'.json')).write_text(json.dumps(result,ensure_ascii=False),'utf-8')
            return pdf_path
        finally:
            try:await call('Browser.close')
            except Exception:pass
            if ws:ws.close()
    try:return asyncio.run(asyncio.wait_for(run(),30))
    finally:
        if process:
            if win32event.WaitForSingleObject(process,8000)!=0:
                if assigned:win32job.TerminateJobObject(job,1)
                else:win32api.TerminateProcess(process,1)
                win32event.WaitForSingleObject(process,5000)
            process.Close()
        job.Close()
        # This directory is created solely for this renderer, never the user's browser profile.
        if profile.resolve().parent==Path(tempfile.gettempdir()).resolve() and profile.name.startswith('photoshop-vector-'):
            shutil.rmtree(profile,ignore_errors=True)
