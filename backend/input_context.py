"""PS-thread IME association lease; keyboard layouts and conversion modes stay intact."""
import ctypes
from ctypes import wintypes as W
import os
import secrets
import hashlib
from .paths import resource_root,runtime_dir


class NativeImeContext:
    def __init__(self,user):
        self.user=user;self.hooks={};self.controls={};self.library=None
        self.user.RegisterWindowMessageW.argtypes=[W.LPCWSTR];self.user.RegisterWindowMessageW.restype=W.UINT
        self.user.GetPropW.argtypes=[W.HWND,W.LPCWSTR];self.user.GetPropW.restype=W.HANDLE
        self.user.SetWindowsHookExW.argtypes=[ctypes.c_int,ctypes.c_void_p,W.HINSTANCE,W.DWORD];self.user.SetWindowsHookExW.restype=W.HANDLE
        self.user.UnhookWindowsHookEx.argtypes=[W.HANDLE]
        self.attach=self.user.RegisterWindowMessageW('PhotoshopMenu.InputContext.Attach.v1')
        self.message=self.user.RegisterWindowMessageW('PhotoshopMenu.InputContext.Control.v1')
        if not self.attach or not self.message:raise OSError('Cannot register IME context protocol')

    def control(self,sample):
        import win32gui,win32process
        root=sample['root'];thread,pid=sample['identity'][3],sample['identity'][1]
        window=self.controls.get(tuple(sample['identity']))
        if window and win32gui.IsWindow(window) and win32gui.GetClassName(window)=='PhotoshopMenu.InputContext.v1' and list(win32process.GetWindowThreadProcessId(window))==[thread,pid]:
            if sample.get('state')=='outside' or self.user.GetPropW(window,'PhotoshopMenu.InputContext.Owner.v1')==os.getpid():return window
        if sample.get('state')=='outside':return None
        # One thread-specific hook; no global injection or keyboard callback.
        if self.library is None:
            content=(resource_root()/'native/InputContext.dll').read_bytes()
            folder=runtime_dir()/'input-context'/hashlib.sha256(content).hexdigest();folder.mkdir(parents=True,exist_ok=True)
            library=folder/'InputContext.dll'
            if not library.exists():
                temporary=folder/'InputContext.tmp';temporary.write_bytes(content);os.replace(temporary,library)
            if library.read_bytes()!=content:raise RuntimeError('PS输入保护组件校验失败')
            self.library=ctypes.WinDLL(str(library))
        identity=tuple(sample['identity'])
        if identity not in self.hooks:
            hook=self.user.SetWindowsHookExW(4,ctypes.cast(self.library.InputContextHook,ctypes.c_void_p),self.library._handle,thread)
            if not hook:raise ctypes.WinError()
            self.hooks[identity]=hook
        nonce=secrets.randbelow(0x7ffffffe)+1
        win32gui.SendMessageTimeout(root,self.attach,os.getpid(),nonce,2,200)
        window=self.user.GetPropW(root,'PhotoshopMenu.InputContext.Window.v1')
        if not window or not win32gui.IsWindow(window) or win32gui.GetClassName(window)!='PhotoshopMenu.InputContext.v1' or list(win32process.GetWindowThreadProcessId(window))!=[thread,pid] or self.user.GetPropW(window,'PhotoshopMenu.InputContext.Owner.v1')!=os.getpid():raise RuntimeError('PS线程内输入保护未就绪或由另一服务持有')
        self.controls[identity]=window;return window

    def command(self,window,operation,focus):
        import win32gui
        nonce=self.user.GetPropW(window,'PhotoshopMenu.InputContext.Nonce.v1')
        if not nonce:raise RuntimeError('PS输入保护身份已失效')
        return win32gui.SendMessageTimeout(window,self.message,(nonce<<8)|operation,focus,2,1000)[1]

    def read(self,sample):
        value={**sample,'ime':None,'ime_open':None}
        if not sample.get('root'):return value
        window=self.control(sample)
        if not window:return value
        status=self.command(window,1,sample['focus'])
        if not status&1 or status&8:raise RuntimeError('PS输入上下文恢复待核对')
        value.update(ime=window,ime_open=int(bool(status&4)),native_restored=bool(status&16),tsf_disabled=bool(status&32),context_nonce=self.user.GetPropW(window,'PhotoshopMenu.InputContext.Nonce.v1'))
        return value

    def renew(self,owned,sample):
        if (sample.get('state')=='non-input' and sample.get('identity')==owned['identity'] and sample.get('layout')==owned['layout'] and
            sample.get('ime')==owned['ime'] and sample.get('focus')==owned['focus'] and sample.get('context_nonce')==owned['context_nonce']):
            self.command(owned['ime'],4,owned['focus'])

    def send(self,request):
        if self.user.GetPropW(request['ime'],'PhotoshopMenu.InputContext.Nonce.v1')!=request['context_nonce']:raise RuntimeError('PS输入保护会话已变化；保留原记录')
        status=self.command(request['ime'],2 if request['wanted']==0 else 3,request['focus'])
        if request['wanted']==0 and status&1 and status&8 and not status&2:return {'rejected':True}
        if not status&1 or status&8:return None
        if request['wanted']==0 and status&2 and not status&4:return {**request,'ime_open':0,'tsf_disabled':bool(status&32),'state':'non-input'}
        if request['wanted']==1 and not status&2 and status&4:return {**request,'ime_open':1,'tsf_disabled':False,'state':'input' if request['input_restore'] else 'outside'}

    def observe_owned(self,owned):
        from .input_method import ImeContext
        self.controls[tuple(owned['identity'])]=owned['ime']
        return ImeContext.observe_owned(self,owned)

    def close(self):
        for hook in self.hooks.values():self.user.UnhookWindowsHookEx(hook)
        self.hooks.clear()
