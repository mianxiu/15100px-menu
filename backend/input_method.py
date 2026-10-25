"""Temporarily close the PS IME context; never select another keyboard layout."""
import ctypes
from ctypes import wintypes as W
import hashlib
import json
import math
import time
from .input_language import InputLanguage,process_exited,read_layout_journal
from .input_accessibility import FocusAccessibility,control_state,CONTAINERS
from .settings import atomic_json
from .input_context import NativeImeContext


def ime_target(value):
    return value.get('identity'),value.get('ime'),value.get('layout'),value.get('context_nonce')


class ImePolicy:
    def __init__(self):
        self.owned=None;self.pending=None;self.attempted=None;self.manual=None
        self.state='unknown';self.confirmed_disables=0;self.confirmed_restores=0

    def step(self,sample,intent,now):
        self.state=sample.get('state','unknown')
        if not sample.get('ime') or type(sample.get('ime_open')) is not int:return
        if self.state=='input':self.manual=None;self.attempted=None
        if self.pending:
            request=self.pending
            if ime_target(sample)!=ime_target(request):return
            if sample['ime_open']!=request['wanted']:
                if now-request['time']>1:self.state='request-not-confirmed'
                return
            self.pending=None
            self.owned=request if request['disable'] else None
            if request['disable']:self.confirmed_disables+=1
            else:
                self.confirmed_restores+=1
                if request['input_restore']:self.attempted=None
        if self.owned:
            if ime_target(sample)!=ime_target(self.owned):return
            if sample['ime_open']!=0:
                self.owned=None
                if sample.get('native_restored'):
                    self.confirmed_restores+=1;self.manual=None;self.attempted=None
                    if self.state=='non-input' and intent is not None:
                        self.attempted=intent;return self.request(sample,True,now)
                    return
                if self.state!='input':self.manual=ime_target(sample);self.state='manual-change'
                return
            if self.state!='non-input':return self.request(sample,False,now)
        elif (intent is not None and intent!=self.attempted and self.state=='non-input' and
              sample['ime_open']==1 and ime_target(sample)!=self.manual):
            self.attempted=intent
            return self.request(sample,True,now)

    def request(self,sample,disable,now):
        self.pending={k:sample[k] for k in ('root','identity','focus','layout','ime')}
        if sample.get('context_nonce') is not None:self.pending['context_nonce']=sample['context_nonce']
        self.pending.update(wanted=0 if disable else 1,original=1,disable=disable,
                            input_restore=not disable and sample['state']=='input',time=now)
        return dict(self.pending)


class ImeContext:
    def __init__(self,user):
        self.user=user
        self.imm=ctypes.WinDLL('imm32')
        self.imm.ImmGetDefaultIMEWnd.argtypes=[W.HWND];self.imm.ImmGetDefaultIMEWnd.restype=W.HWND

    def read(self,sample):
        import win32gui,win32process
        value={**sample,'ime':None,'ime_open':None}
        if not sample.get('root'):return value
        hwnd=self.imm.ImmGetDefaultIMEWnd(sample['focus'])
        if (not hwnd or not win32gui.IsWindow(hwnd) or win32gui.GetClassName(hwnd)!='IME' or
            list(win32process.GetWindowThreadProcessId(hwnd))!=[sample['identity'][3],sample['identity'][1]]):return value
        opened=win32gui.SendMessageTimeout(hwnd,0x283,5,0,2,200)[1]
        if type(opened) is int and opened in (0,1):value.update(ime=hwnd,ime_open=opened)
        return value

    def send(self,request):
        import win32gui
        # SETOPENSTATUS is synchronous-only. No character or layout message is sent.
        win32gui.SendMessageTimeout(request['ime'],0x283,6,request['wanted'],2,200)

    def observe_owned(self,owned):
        import win32gui,win32process,win32api
        identity=owned['identity'];root,pid,created,thread=identity
        if not win32gui.IsWindow(root) or list(win32process.GetWindowThreadProcessId(root))!=[thread,pid]:return {'state':'outside'}
        handle=win32api.OpenProcess(0x1000,False,pid)
        try:
            if str(win32process.GetProcessTimes(handle)['CreationTime'])!=created:return {'state':'outside'}
        finally:handle.Close()
        class Info(ctypes.Structure):
            _fields_=[('cbSize',W.DWORD),('flags',W.DWORD),('active',W.HWND),('focus',W.HWND),
                      ('capture',W.HWND),('menu',W.HWND),('move',W.HWND),('caret',W.HWND),('rect',W.RECT)]
        info=Info(cbSize=ctypes.sizeof(Info))
        if not self.user.GetGUIThreadInfo(thread,ctypes.byref(info)):return {'state':'outside'}
        focus=info.focus or (owned['focus'] if win32gui.IsWindow(owned['focus']) else root)
        # Attached menu input queues can expose another process's focused HWND.
        if list(win32process.GetWindowThreadProcessId(focus))!=[thread,pid]:
            focus=owned['focus'] if win32gui.IsWindow(owned['focus']) else root
            if list(win32process.GetWindowThreadProcessId(focus))!=[thread,pid]:return {'state':'outside'}
        return self.read({'root':root,'identity':identity,'focus':focus,'layout':self.user.GetKeyboardLayout(thread),'state':'outside'})


class InputMethod(InputLanguage):
    def __init__(self,desktop):
        super().__init__(desktop)
        self.policy=ImePolicy();self.legacy=None;self.legacy_saved=None;self.ime=None
        self.context_schema=1
        self.report={'state':'unknown','scope':'photoshop-temporary-ime','layout_requests':0,
                     'disable_requests':0,'restore_requests':0}

    def saved(self):return {'schema':self.context_schema,'owned':self.policy.owned,'pending':self.policy.pending}

    def load(self,path):
        if not path.exists():return
        if path.stat().st_size>16384:raise ValueError('IME journal size')
        value=json.loads(path.read_text('utf-8'))
        if not isinstance(value,dict) or set(value)!={'schema','owned','pending'} or type(value['schema']) is not int or value['schema'] not in (1,2):raise ValueError('IME journal schema')
        self.context_schema=value['schema']
        fields={'root','identity','focus','layout','ime','wanted','original','disable','input_restore','time'}
        if self.context_schema==2:fields.add('context_nonce')
        for row in (value['owned'],value['pending']):
            if row is None:continue
            if (not isinstance(row,dict) or set(row)!=fields or
                self.context_schema==2 and (type(row['context_nonce']) is not int or not 1<=row['context_nonce']<=0x7fffffff) or
                any(type(row[k]) is not int or row[k]<=0 for k in ('root','focus','layout','ime')) or
                not isinstance(row['identity'],list) or len(row['identity'])!=4 or row['identity'][0]!=row['root'] or
                any(type(row['identity'][i]) is not int or row['identity'][i]<=0 for i in (0,1,3)) or
                not isinstance(row['identity'][2],str) or not row['identity'][2] or
                type(row['wanted']) is not int or row['wanted'] not in (0,1) or type(row['original']) is not int or row['original']!=1 or
                type(row['disable']) is not bool or row['wanted']!=int(not row['disable']) or
                type(row['input_restore']) is not bool or row['disable'] and row['input_restore'] or
                type(row['time']) not in (int,float) or not math.isfinite(row['time'])):raise ValueError('IME journal record')
        if value['owned'] and not value['owned']['disable']:raise ValueError('IME unconfirmed ownership')
        self.policy.owned=value['owned'];self.policy.pending=value['pending']
        if self.policy.pending:self.policy.pending['time']=time.monotonic()-2

    def retire(self,path,reason):
        owned=self.policy.owned
        if not owned or self.policy.pending:return
        key=hashlib.sha256(json.dumps(owned,sort_keys=True).encode()).hexdigest()
        atomic_json(path.parent/('input-method-retired-'+key+'.json'),{'owned':owned,'reason':reason,'restore_sent':False})
        atomic_json(path,{'schema':self.context_schema,'owned':None,'pending':None})
        self.policy.owned=None;self.policy.attempted=None

    def legacy_step(self,sample):
        if not self.legacy:return True
        legacy=self.legacy;path=self.desktop.runtime/'input-language-owned.json'
        legacy.retire_exited_owner()
        if not legacy.policy.owned and not legacy.policy.pending:
            self.legacy=None;self.report['legacy_pending']=False;return True
        sample={**sample,'state':'unknown'}
        request=legacy.policy.step(sample,None,None,time.monotonic())
        if request:
            if request['switch']:raise ValueError('Legacy new layout switch prohibited')
            fresh=self.sample()
            if any(fresh.get(k)!=sample.get(k) for k in ('identity','focus','layout')):
                legacy.policy.pending=None;legacy.policy.restore_attempt=None
            else:
                atomic_json(path,{'owned':legacy.policy.owned,'pending':legacy.policy.pending})
                self.user.PostMessageW(request['focus'],0x50,0,request['wanted'])
                self.report['legacy_restore_requests']=self.report.get('legacy_restore_requests',0)+1
        saved={'owned':legacy.policy.owned,'pending':legacy.policy.pending}
        if saved!=self.legacy_saved:atomic_json(path,saved);self.legacy_saved=json.loads(json.dumps(saved))
        self.report.update(state='legacy-layout-recovery',legacy_pending=bool(legacy.policy.pending))
        return False

    def read_tool(self):
        self.report['tool_reads']+=1
        try:return self.desktop.input_language_tool()
        except Exception as error:self.report['tool_error_type']=type(error).__name__

    def run(self):
        import pythoncom
        pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
        self.user=ctypes.WinDLL('user32',use_last_error=True)
        self.user.GetKeyboardLayout.argtypes=[W.DWORD];self.user.GetKeyboardLayout.restype=W.HANDLE
        self.user.GetKeyboardLayoutList.argtypes=[ctypes.c_int,ctypes.POINTER(W.HANDLE)]
        self.user.PostMessageW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM]
        path=self.desktop.runtime/'input-method-owned.json';persisted=None
        try:
            self.ime=ImeContext(self.user)
            try:
                self.load(path)
                layouts=(W.HANDLE*64)();count=self.user.GetKeyboardLayoutList(64,layouts)
                saved=read_layout_journal(self.desktop.runtime/'input-language-owned.json',list(layouts)[:count])
                if saved['owned'] or saved['pending']:
                    self.legacy=InputLanguage(self.desktop);self.legacy.policy.owned=saved['owned'];self.legacy.policy.pending=saved['pending']
                    if self.legacy.policy.pending:self.legacy.policy.pending['time']=time.monotonic()-2
            except Exception as error:self.report.update(state='journal-invalid',error_type=type(error).__name__);return
            try:self.accessibility=FocusAccessibility()
            except Exception as error:self.report['uia_error_type']=type(error).__name__
            self.report.update(uia_available=self.accessibility is not None,tool_reads=0)
            old_context=self.context_schema==1 and bool(self.policy.owned or self.policy.pending)
            if not old_context:self.ime=NativeImeContext(self.user);self.context_schema=2
            self.report['mechanism']='open-close-recovery' if old_context else 'ps-thread-context-association'
            examined=None;tool=None;scope_before=None;episode=0;blocked_before=False
            while not self.desktop.stop.is_set():
                self.wake.wait(.05);self.wake.clear()
                if self.desktop.stop.is_set():break
                try:
                    serial,epoch,protected,_=self.snapshot();sample=self.sample()
                    if not self.legacy_step(sample):continue
                    if self.policy.owned and not self.policy.pending and process_exited(self.policy.owned['identity']):self.retire(path,'original-process-exited')
                    scope=tuple(sample.get('identity',[]))
                    if scope!=scope_before:episode+=1;scope_before=scope;examined=None;tool=None
                    mouse=bool(self.user.GetAsyncKeyState(1)&0x8000)
                    blocked=mouse or sample.get('blocked') or self.desktop.visible or self.busy() or not self.desktop.settings['enabled'] or old_context
                    if bool(blocked)!=blocked_before:episode+=1;blocked_before=bool(blocked)
                    if blocked:examined=None;tool=None
                    row=sample.get('accessibility',{});context=(scope,sample.get('focus'),serial)
                    needs_tool=(sample.get('workspace') and sample.get('state')=='unknown' and control_state(row,sample.get('pid'))!='input' and
                                (row.get(30003) in CONTAINERS or protected or self.accessibility is None))
                    reconcile=getattr(self.desktop,'input_language_reconcile',None)
                    if needs_tool and context==examined and tool is None and not blocked and reconcile and reconcile():examined=None
                    if needs_tool and context!=examined and not blocked:
                        examined=context;tool=self.read_tool();sample=self.sample()
                    same=(tuple(sample.get('identity',[])),sample.get('focus'),self.snapshot()[0])==context
                    evidence=tool if same and examined==context else None
                    if sample.get('root'):
                        protected=protected and not (isinstance(evidence,dict) and evidence.get('isModal') is False)
                        sample['state']='input' if protected else self.focus_state(sample,evidence)
                        if blocked:sample['state']='unknown'
                        sample=self.ime.read(sample)
                    elif self.policy.owned or self.policy.pending:
                        sample=self.ime.observe_owned(self.policy.pending or self.policy.owned)
                    if self.policy.owned and not self.policy.pending and sample.get('identity')==self.policy.owned['identity'] and sample.get('layout')!=self.policy.owned['layout']:
                        self.retire(path,'manual-keyboard-layout-change');self.policy.manual=ime_target(sample)
                    if self.policy.owned and not self.policy.pending and sample.get('identity')==self.policy.owned['identity'] and sample.get('ime') and sample['ime']!=self.policy.owned['ime']:
                        self.retire(path,'original-ime-window-ended')
                    eligible=same and not blocked and sample.get('state')=='non-input' and sample.get('ime') is not None
                    token=(scope,sample.get('focus'),row.get(30003),epoch,episode,serial) if eligible else None
                    request=self.policy.step(sample,token,time.monotonic())
                    if self.policy.owned and not self.policy.pending and not blocked and callable(getattr(self.ime,'renew',None)):
                        self.ime.renew(self.policy.owned,sample)
                    if request:
                        if request['disable'] and needs_tool and self.read_tool()!=tool:
                            self.policy.pending=None;self.policy.attempted=None;examined=None;continue
                        fresh=self.ime.read(self.sample()) if request['disable'] else self.ime.observe_owned(request)
                        valid=(ime_target(fresh)==ime_target(request) and fresh.get('focus')==request['focus'] and fresh.get('ime_open')==sample.get('ime_open'))
                        if request['disable']:
                            valid=bool(valid and eligible and self.snapshot()[0]==serial and not self.desktop.visible and not self.busy() and
                                       not fresh.get('blocked') and self.focus_state(fresh,tool)=='non-input' and
                                       not any(self.user.GetAsyncKeyState(k)&0x8000 for k in range(1,256)))
                        if valid:
                            atomic_json(path,self.saved());acknowledged=self.ime.send(request)
                            if self.context_schema==2 and acknowledged:
                                if acknowledged.get('rejected'):
                                    key=hashlib.sha256(json.dumps(request,sort_keys=True).encode()).hexdigest()
                                    atomic_json(path.parent/('input-method-rejected-'+key+'.json'),{'request':request,'native_reply':'not-armed','marked_success':False})
                                    self.policy.pending=None;self.policy.state='request-rejected'
                                else:
                                    self.policy.step(acknowledged,token,time.monotonic())
                                    sample.update(ime_open=acknowledged['ime_open'],tsf_disabled=acknowledged['tsf_disabled'])
                            key='disable_requests' if request['disable'] else 'restore_requests';self.report[key]+=1
                        else:
                            self.policy.pending=None
                            if request['disable']:self.policy.attempted=None
                    self.report.update(state=self.policy.state,pending=bool(self.policy.pending),owned=bool(self.policy.owned),
                        confirmed_disables=self.policy.confirmed_disables,confirmed_restores=self.policy.confirmed_restores,
                        ime_open=sample.get('ime_open'),keyboard_layout=sample.get('layout'),focus_class=sample.get('class'),
                        tsf_disabled=sample.get('tsf_disabled'),
                        tool=tool.get('classID') if isinstance(tool,dict) else None)
                    saved=self.saved()
                    if saved!=persisted:atomic_json(path,saved);persisted=json.loads(json.dumps(saved))
                    if old_context and not self.policy.owned and not self.policy.pending:
                        self.ime=NativeImeContext(self.user);self.context_schema=2;old_context=False;examined=None
                        self.report['mechanism']='ps-thread-context-association'
                except Exception as error:self.report.update(state='unknown',error_type=type(error).__name__)
        finally:
            if self.ime and (self.policy.owned or self.policy.pending):
                try:
                    sample=self.ime.observe_owned(self.policy.pending or self.policy.owned)
                    request=self.policy.step(sample,None,time.monotonic())
                    if request and not request['disable']:
                        fresh=self.ime.observe_owned(request)
                        if ime_target(fresh)==ime_target(request) and fresh.get('ime_open')==sample.get('ime_open'):
                            atomic_json(path,self.saved());acknowledged=self.ime.send(request)
                            if self.context_schema==2 and acknowledged:self.policy.step(acknowledged,None,time.monotonic())
                    until=time.monotonic()+.6
                    while self.policy.pending and time.monotonic()<until:
                        self.policy.step(self.ime.observe_owned(self.policy.pending),None,time.monotonic());time.sleep(.02)
                    atomic_json(path,self.saved())
                except Exception:self.report['state']='shutdown-restore-unconfirmed'
            if self.ime and callable(getattr(self.ime,'close',None)):self.ime.close()
            self.accessibility=None;pythoncom.CoUninitialize()
