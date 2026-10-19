"""Frozen offline installer entry point; never launches or closes Photoshop."""
import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import shutil
if not getattr(sys,'frozen',False):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from offline_install import OfflineInstall
from backend.photoshop_version import MIN_PHOTOSHOP_TEXT,installed_paths,check_install_hosts,exe_version,require_version

running_host_paths=[]

def running_names():
    class Entry(ctypes.Structure):
        _fields_=[('size',wintypes.DWORD),('usage',wintypes.DWORD),('pid',wintypes.DWORD),
                  ('heap',ctypes.c_size_t),('module',wintypes.DWORD),('threads',wintypes.DWORD),
                  ('parent',wintypes.DWORD),('priority',wintypes.LONG),('flags',wintypes.DWORD),('name',wintypes.WCHAR*260)]
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.CreateToolhelp32Snapshot.restype=wintypes.HANDLE
    api.Process32FirstW.argtypes=[wintypes.HANDLE,ctypes.POINTER(Entry)]
    api.Process32NextW.argtypes=[wintypes.HANDLE,ctypes.POINTER(Entry)]
    api.CloseHandle.argtypes=[wintypes.HANDLE]
    api.OpenProcess.restype=wintypes.HANDLE
    api.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
    handle=api.CreateToolhelp32Snapshot(2,0)
    if handle==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
    names=[]; entry=Entry(); entry.size=ctypes.sizeof(entry)
    try:
        ok=api.Process32FirstW(handle,ctypes.byref(entry))
        while ok:
            names.append(entry.name.lower())
            if entry.name.lower()=='photoshop.exe':
                process=api.OpenProcess(0x1000,False,entry.pid)
                path=None
                if process:
                    try:
                        buffer=ctypes.create_unicode_buffer(32768);length=wintypes.DWORD(len(buffer))
                        if api.QueryFullProcessImageNameW(process,0,buffer,ctypes.byref(length)):path=buffer.value
                    finally:api.CloseHandle(process)
                running_host_paths.append(path)
            ok=api.Process32NextW(handle,ctypes.byref(entry))
    finally:api.CloseHandle(handle)
    return names

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--operation',choices=('install','uninstall','rollback'),default='install')
    parser.add_argument('--quiet',action='store_true')
    parser.add_argument('--no-launch',action='store_true')
    parser.add_argument('--result-file',type=Path)
    parser.add_argument('--wait-for-pid',type=int,default=0,help=argparse.SUPPRESS)
    parser.add_argument('--data-root',type=Path,help=argparse.SUPPRESS)
    parser.add_argument('--photoshop-exe',type=Path,help='Photoshop.exe in a custom installation folder')
    args=parser.parse_args()
    try:
        if args.wait_for_pid:
            api=ctypes.WinDLL('kernel32',use_last_error=True)
            api.OpenProcess.restype=wintypes.HANDLE
            api.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
            api.CloseHandle.argtypes=[wintypes.HANDLE]
            handle=api.OpenProcess(0x100000,False,args.wait_for_pid)
            if handle:
                try:
                    if api.WaitForSingleObject(handle,10000)!=0:raise RuntimeError('Previous installer did not exit')
                finally:api.CloseHandle(handle)
        # Execute maintenance from a temporary copy so Windows permits restoring
        # or removing the installed uninstaller itself. No process is killed.
        installed=Path(sys.executable).resolve()
        if getattr(sys,'frozen',False) and installed.name=='OfflineSetup.exe' and installed.parent.name=='app':
            temporary=Path(tempfile.mkdtemp(prefix='PhotoshopMenu-maintenance-'))/'OfflineSetup.exe'
            shutil.copy2(sys.executable,temporary)
            rootargs=[] if args.data_root else ['--data-root',str(installed.parent.parent)]
            subprocess.Popen([str(temporary),*sys.argv[1:],*rootargs,'--wait-for-pid',str(os.getpid())],creationflags=subprocess.CREATE_NO_WINDOW)
            return 0
        names=running_names()
        if 'photoshopmenu.exe' in names:
            raise RuntimeError('请等待操作完成，再从托盘退出 Photoshop Menu，然后重新运行安装包。安装器不会强制结束进程。')
        local=Path(os.environ['LOCALAPPDATA']); roaming=Path(os.environ['APPDATA'])
        if args.data_root:
            if args.data_root.name!='PhotoshopMenu':raise RuntimeError('Invalid installation root')
            local=args.data_root.parent
        start=roaming/'Microsoft/Windows/Start Menu/Programs/Photoshop Menu'
        shortcuts=[start/'Photoshop Menu.lnk',start/'Uninstall.lnk',start/'Rollback.lnk']
        if not args.data_root and shortcuts[0].is_file():
            import win32com.client
            existing=Path(win32com.client.Dispatch('WScript.Shell').CreateShortcut(str(shortcuts[0])).TargetPath).resolve()
            candidate=existing.parent.parent
            if existing.name=='PhotoshopMenu.exe' and existing.parent.name=='app' and candidate.name=='PhotoshopMenu' and (candidate/'offline-install.json').is_file() and (candidate/'uxp-config.json').is_file():
                # A subsequent installer launched outside the original host must
                # update its existing root rather than create a second profile.
                local=candidate.parent
        installer=OfflineInstall(local,roaming,shortcuts)
        def links():
            import win32com.client
            start.mkdir(parents=True,exist_ok=True)
            shell=win32com.client.Dispatch('WScript.Shell')
            concrete=(installer.root/'uxp-config.json').resolve().parent
            for path,target,arguments in zip(shortcuts,
                [installer.files[0],installer.files[1],installer.files[1]],
                ['--data-dir "'+str(concrete)+'"','--operation uninstall --data-root "'+str(concrete)+'"','--operation rollback --data-root "'+str(concrete)+'"']):
                link=shell.CreateShortcut(str(path));link.TargetPath=str(target.resolve())
                link.Arguments=arguments;link.WorkingDirectory=str(installer.root/'app');link.Save()
        if args.operation=='install':
            hosts=check_install_hosts(installed_paths(args.photoshop_exe))
            for host in running_host_paths:
                if host is None:raise RuntimeError('无法核验运行中的 Photoshop 版本，请正常关闭 PS 后再安装')
                require_version(exe_version(host))
            source=Path(sys._MEIPASS) if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]/'.runtime/offline-payload'
            running='photoshop.exe' in names
            if running and not installer.plugin_is_current(source/'payload',True):
                raise RuntimeError('请先保存并正常关闭 Photoshop，再重新运行安装包。插件版本或凭据有变化，需要下次启动重新加载。')
            result=installer.install(source/'payload',Path(sys.executable) if getattr(sys,'frozen',False) else Path(__file__),links,preserve_plugin=running)
            result['minimum_photoshop']=MIN_PHOTOSHOP_TEXT;result['photoshop_installations']=hosts
            message='离线安装完成。请正常打开 Photoshop，再通过开始菜单运行 Photoshop Menu。插件会随 PS 自动加载。'
            if not args.no_launch:
                concrete=(installer.root/'uxp-config.json').resolve().parent
                subprocess.Popen([str(Path(result['executable']).resolve()),'--data-dir',str(concrete)],creationflags=subprocess.CREATE_NO_WINDOW)
        elif args.operation=='uninstall':
            if 'photoshop.exe' in names:raise RuntimeError('请先保存并正常关闭 Photoshop，再卸载。')
            result=installer.uninstall();message='已卸载菜单程序和自有插件，设置、任务记录和备份已保留。'
        else:
            if 'photoshop.exe' in names:raise RuntimeError('请先保存并正常关闭 Photoshop，再回退版本。')
            result=installer.rollback();message='已恢复安装前版本。请正常打开 Photoshop 和菜单程序。'
        if args.result_file:args.result_file.write_text(json.dumps({'ok':True,**result},indent=2),'utf-8')
        if not args.quiet:ctypes.windll.user32.MessageBoxW(None,message,'Photoshop Menu',0x40)
        return 0
    except Exception as error:
        if args.result_file:args.result_file.write_text(json.dumps({'ok':False,'error':str(error)}),'utf-8')
        if not args.quiet:ctypes.windll.user32.MessageBoxW(None,str(error),'Photoshop Menu',0x10)
        return 1

if __name__=='__main__':sys.exit(main())
