"""PS-only input language transitions; no work runs in keyboard callbacks."""
import ctypes
from ctypes import wintypes as W
import threading
import time
import math


class LanguagePolicy:
    def __init__(self):
        self.owned=None
        self.pending=None
        self.attempted=None
        self.restore_attempt=None
        self.confirmed_switches=0;self.confirmed_restores=0
        self.state='unknown'

    def step(self, sample, intent, english, now):
        self.state=sample.get('state','unknown')
        if not sample.get('root'):return None
        root,layout=sample['root'],sample['layout']
        if self.pending:
            request=self.pending
            if sample.get('identity')!=request.get('identity'):return None
            if layout==request['wanted']:
                self.owned=request if request['switch'] else None
                if request['switch']:self.confirmed_switches+=1
                else:self.confirmed_restores+=1
                self.pending=None
            elif now-request['time']>1:
                self.state='request-not-confirmed';return None
            else:return None
        if self.owned:
            if sample.get('identity')!=self.owned.get('identity'):return None
            if layout!=self.owned['wanted']:
                self.owned=None;self.state='manual-change';return None
            if self.state!='non-input':
                token=(sample.get('identity'),sample['focus'],layout)
                if token==self.restore_attempt:return None
                self.restore_attempt=token
                return self.request(sample,self.owned['original'],False,now)
        elif (self.state=='non-input' and intent and intent!=self.attempted and english and layout!=english):
            self.attempted=intent
            return self.request(sample,english,True,now)
        return None

    def request(self,sample,wanted,switch,now):
        if switch:self.restore_attempt=None
        original=sample['layout'] if switch else self.owned['original']
        self.pending={'root':sample['root'],'identity':sample.get('identity'),'focus':sample['focus'],'wanted':wanted,'original':original,'switch':switch,'time':now}
        return dict(self.pending)


class InputLanguage:
    # A canvas click with a verified non-text tool is positive evidence;
    # absence of Edit/caret alone never grants a switch.
    TOOLS=frozenset({'moveTool','marqueeRectTool','marqueeEllipTool','lassoTool','polySelTool',
                     'magicWandTool','quickSelectTool','paintbrushTool','pencilTool','eraserTool',
                     'gradientTool','bucketTool','handTool','zoomTool','cropTool'})

    def __init__(self,desktop):
        self.desktop=desktop;self.lock=threading.Lock();self.intent=None;self.serial=0
        self.wake=threading.Event()
        self.policy=LanguagePolicy();self.report={'state':'unknown','switch_requests':0,'restore_requests':0}
        self.thread=threading.Thread(target=self.run,name='photoshop-input-language',daemon=True)

    def click(self,hwnd,root):
        with self.lock:
            self.serial+=1;self.intent=(self.serial,hwnd,root)
        self.wake.set()

    def protect(self):
        with self.lock:self.serial+=1;self.intent=None
        self.wake.set()

    def busy(self):
        check=getattr(self.desktop,'input_language_busy',None)
        return bool(check and check())

    def sample(self):
        import win32gui,win32process,win32api
        from .photoshop_windows import workspace_root
        gui=win32gui;foreground=gui.GetForegroundWindow();root=workspace_root(gui,foreground)
        if not foreground:return {'state':'outside'}
        thread,pid=win32process.GetWindowThreadProcessId(foreground)
        restore_only=False
        if not root or not self.desktop._is_photoshop(foreground):
            tracked=self.policy.owned or self.policy.pending
            if not tracked or [pid,thread]!=[tracked['identity'][1],tracked['identity'][3]]:return {'state':'outside'}
            root=tracked['root'];restore_only=True
        class Info(ctypes.Structure):
            _fields_=[('cbSize',W.DWORD),('flags',W.DWORD),('active',W.HWND),('focus',W.HWND),
                      ('capture',W.HWND),('menu',W.HWND),('move',W.HWND),('caret',W.HWND),('rect',W.RECT)]
        info=Info(cbSize=ctypes.sizeof(Info))
        if not self.user.GetGUIThreadInfo(thread,ctypes.byref(info)):return {'state':'unknown'}
        focus=info.focus or 0;layout=self.user.GetKeyboardLayout(thread)
        if not focus or not layout:return {'state':'unknown'}
        if restore_only:
            if win32process.GetWindowThreadProcessId(focus)[1]!=pid:return {'state':'unknown'}
        elif workspace_root(gui,focus)!=root:return {'state':'unknown'}
        name=gui.GetClassName(focus) if focus and gui.IsWindow(focus) else ''
        state='input' if restore_only or info.caret or name in ('Edit','RichEdit20W','RichEdit50W','ComboBox') else 'unknown'
        handle=win32api.OpenProcess(0x410,False,pid)
        try:
            if win32process.GetModuleFileNameEx(handle,0).rsplit('\\',1)[-1].casefold()!='photoshop.exe':return {'state':'outside'}
            created=str(win32process.GetProcessTimes(handle)['CreationTime'])
        finally:handle.Close()
        return {'root':root,'identity':[root,pid,created,thread],'focus':focus,'layout':layout,'state':state,'restore_only':restore_only,'blocked':bool(info.capture or info.menu or info.move or info.flags&30),'class':name}

    def run(self):
        import pythoncom,win32com.client,json
        from .settings import atomic_json
        pythoncom.CoInitialize()
        self.user=ctypes.WinDLL('user32',use_last_error=True)
        self.user.GetKeyboardLayout.argtypes=[W.DWORD];self.user.GetKeyboardLayout.restype=W.HANDLE
        self.user.GetKeyboardLayoutList.argtypes=[ctypes.c_int,ctypes.POINTER(W.HANDLE)]
        self.user.PostMessageW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM]
        try:
            journal=self.desktop.runtime/'input-language-owned.json'
            layouts=(W.HANDLE*64)();count=self.user.GetKeyboardLayoutList(64,layouts)
            installed=list(layouts)[:count]
            if journal.exists():
                try:
                    if journal.stat().st_size>16384:raise ValueError('size')
                    saved=json.loads(journal.read_text('utf-8'))
                    if set(saved)!={'owned','pending'}:raise ValueError('fields')
                    for row in saved.values():
                        if row is None:continue
                        if (set(row)!={'root','identity','focus','wanted','original','switch','time'} or
                            any(type(row[k]) is not int or row[k]<=0 for k in ['root','focus','wanted','original']) or
                            row['wanted'] not in installed or row['original'] not in installed or type(row['switch']) is not bool or
                            not isinstance(row['time'],(int,float)) or not math.isfinite(row['time']) or
                            not isinstance(row['identity'],list) or len(row['identity'])!=4 or row['identity'][0]!=row['root'] or
                            any(type(row['identity'][i]) is not int for i in [0,1,3]) or not isinstance(row['identity'][2],str)):
                            raise ValueError('record')
                    self.policy.owned=saved['owned'];self.policy.pending=saved['pending']
                    if self.policy.pending:self.policy.pending['time']=time.monotonic()-2
                except Exception:
                    self.report['state']='journal-invalid';return
            persisted=None
            english=next((v for v in list(layouts)[:count] if v and (v&0xffff)==0x409),None)
            examined=None;tool=None;stable=None
            while not self.desktop.stop.is_set():
                self.wake.wait(.05);self.wake.clear()
                if self.desktop.stop.is_set():break
                try:
                    with self.lock:intent=self.intent
                    sample=self.sample()
                    if not sample.get('root') or sample.get('restore_only'):
                        if intent:self.protect()
                        intent=None;examined=None;tool=None
                    mouse_down=bool(self.user.GetAsyncKeyState(1)&0x8000)
                    if intent and intent!=examined and sample.get('root')==intent[2] and not mouse_down and not sample.get('blocked'):
                        examined=intent;tool=None
                        if self.desktop.settings['enabled'] and not self.desktop.visible and sample['state']=='unknown' and not self.busy() and self.desktop.panel_context.describe(intent[1],intent[2])=='canvas':
                            tool=str(win32com.client.GetActiveObject('Photoshop.Application').DoJavaScript('String(app.currentTool);'))
                        sample=self.sample()
                    eligible=(self.desktop.settings['enabled'] and not self.busy() and not mouse_down and not self.desktop.visible and intent and
                              sample.get('root')==intent[2] and sample.get('class') in ('OWL.Document','PSViewC') and
                              self.desktop.panel_context.describe(sample['focus'],intent[2])=='canvas' and
                              self.desktop.panel_context.describe(intent[1],intent[2])=='canvas' and
                              tool in self.TOOLS and sample['state']=='unknown' and not sample.get('blocked'))
                    token=(intent,sample.get('root'),sample.get('focus')) if eligible else None
                    if eligible and token==stable:sample['state']='non-input'
                    stable=token
                    request=self.policy.step(sample,intent if eligible else None,english,time.monotonic())
                    if request:
                        if request['switch'] and str(win32com.client.GetActiveObject('Photoshop.Application').DoJavaScript('String(app.currentTool);')) not in self.TOOLS:
                            self.policy.pending=None;continue
                        fresh=self.sample()
                        with self.lock:unchanged=intent==self.intent
                        valid=(fresh.get('identity')==request['identity'] and fresh.get('focus')==request['focus'] and fresh.get('layout')==sample['layout'] and
                               (not request['switch'] or unchanged and eligible and not self.busy() and not fresh.get('blocked') and fresh['state']=='unknown'))
                        if valid:
                            atomic_json(journal,{'owned':self.policy.owned,'pending':self.policy.pending})
                        if valid and self.user.PostMessageW(request['focus'],0x50,0,request['wanted']):
                            key='switch_requests' if request['switch'] else 'restore_requests';self.report[key]+=1
                        else:self.policy.pending=None
                    self.report.update(state=self.policy.state,pending=bool(self.policy.pending),owned=bool(self.policy.owned),english_available=bool(english),confirmed_switches=self.policy.confirmed_switches,confirmed_restores=self.policy.confirmed_restores,focus_class=sample.get('class'),tool=tool)
                    saved={'owned':self.policy.owned,'pending':self.policy.pending}
                    if saved!=persisted:
                        atomic_json(journal,saved);persisted=json.loads(json.dumps(saved))
                except Exception as error:
                    self.report.update(state='unknown',error_type=type(error).__name__)
        finally:
            # Restore only our confirmed change, still on the same foreground PS thread.
            if self.policy.owned or self.policy.pending:
                try:
                    sample=self.sample();sample['state']='unknown'
                    request=self.policy.step(sample,None,None,time.monotonic())
                    if request and not request['switch']:
                        fresh=self.sample()
                        if fresh.get('identity')==request['identity'] and fresh.get('focus')==request['focus'] and fresh.get('layout')==sample['layout']:
                            atomic_json(journal,{'owned':self.policy.owned,'pending':self.policy.pending})
                            self.user.PostMessageW(request['focus'],0x50,0,request['wanted'])
                    until=time.monotonic()+.5
                    while self.policy.pending and time.monotonic()<until:
                        self.policy.step(self.sample(),None,None,time.monotonic());time.sleep(.02)
                    atomic_json(journal,{'owned':self.policy.owned,'pending':self.policy.pending})
                except Exception:self.report['state']='shutdown-restore-unconfirmed'
            pythoncom.CoUninitialize()
