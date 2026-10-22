"""Bounded Windows self-update helper; never kills Photoshop or the service."""
import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.request import build_opener, ProxyHandler
from .application_updates import HASH, executable_version, sha256, version
from .settings import atomic_json


def validate_job(path, executable):
    path=Path(path).resolve();folder=path.parent
    if path.name!='job.json' or folder.parent.name!='application-updates':raise ValueError('更新任务路径无效')
    data=json.loads(path.read_text('utf-8'))
    runtime=Path(data['runtime']).resolve();target=Path(data['target']).resolve()
    if (data['schema']!=1 or data['id']!=folder.name or len(folder.name)!=32 or
        any(c not in '0123456789abcdef' for c in folder.name) or
        runtime/'application-updates'/data['id']!=folder or
        Path(executable).resolve()!=folder/'update-host.exe' or
        target.name!='PhotoshopMenu.exe' or target.is_relative_to(folder.parent)):
        raise ValueError('更新任务身份或安装目标无效')
    if version(data['new_version'])<=version(data['old_version']):raise ValueError('更新版本必须更高')
    for name in ('new_sha256','old_sha256'):
        if not isinstance(data[name],str) or not HASH.fullmatch(data[name]):raise ValueError('更新摘要无效')
    if not isinstance(data['pids'],list) or not 1<=len(data['pids'])<=2 or any(type(p) is not int or p<=0 for p in data['pids']):
        raise ValueError('更新进程无效')
    if type(data['port']) is not int or not 1<=data['port']<=65535:raise ValueError('更新端口无效')
    if any(type(data[name]) is not bool for name in ('headless','no_desktop')):raise ValueError('启动选项无效')
    source=folder/'PhotoshopMenu.exe'
    if sha256(source)!=data['new_sha256'] or executable_version(source)!=data['new_version']:
        raise ValueError('新应用文件校验失败')
    if sha256(target)!=data['old_sha256'] or executable_version(target)!=data['old_version']:
        raise ValueError('实际运行入口已改变')
    if sha256(executable)!=data['new_sha256']:raise ValueError('更新助手文件校验失败')
    return data,folder,target,source


def open_processes(pids, target):
    # Pin handles and image paths before signaling readiness, guarding PID reuse.
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    handles=[]
    try:
        for pid in pids:
            handle=kernel.OpenProcess(0x100000|0x1000,False,pid)
            if not handle:raise OSError('无法等待原服务进程')
            handles.append(handle);text=ctypes.create_unicode_buffer(32768);size=wintypes.DWORD(len(text))
            if not kernel.QueryFullProcessImageNameW(handle,0,text,ctypes.byref(size)) or Path(text.value).resolve()!=target:
                raise ValueError('原进程不属于当前运行入口')
        return kernel,handles
    except Exception:
        for handle in handles:kernel.CloseHandle(handle)
        raise


def wait_processes(kernel, handles, seconds=45):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        values=[kernel.WaitForSingleObject(handle,0) for handle in handles]
        if all(value==0 for value in values):return
        if any(value not in (0,258) for value in values):raise OSError('等待旧进程失败')
        time.sleep(.1)
    raise TimeoutError('后台未正常退出，更新已取消；没有替换运行文件')


def replace(source, target):
    temporary=target.with_name(target.name+'.update-new')
    if temporary.exists():raise RuntimeError('已有待处理的更新临时文件，请检查后再更新')
    shutil.copy2(source,temporary)
    try:
        if sha256(temporary)!=sha256(source):raise ValueError('复制应用校验失败')
        deadline=time.monotonic()+5
        while True:
            try:os.replace(temporary,target);return
            except PermissionError:
                if time.monotonic()>=deadline:raise
                time.sleep(.1)
    finally:temporary.unlink(missing_ok=True)


def update_receipt(runtime, target, old_hash, new_hash, new_version):
    path=runtime/'offline-install.json'
    if not path.exists():return
    data=json.loads(path.read_text('utf-8-sig'))
    if data.get('owned',{}).get(str(target))!=old_hash:return
    data['version']=new_version;data['owned'][str(target)]=new_hash;atomic_json(path,data)


def launch(target, data):
    command=[str(target),'--port',str(data['port']),'--data-dir',data['runtime']]
    if data['headless']:command.append('--headless')
    if data['no_desktop']:command.append('--no-desktop')
    return subprocess.Popen(command,cwd=str(target.parent),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)


def health_matches(health, target, expected):
    return (health.get('app')=='photoshop-menu' and health.get('version')==expected and health.get('ready') is True and
            Path(health.get('executable','')).resolve()==target and type(health.get('pid')) is int)


def apply(path):
    folder=Path(path).resolve().parent;handles=[];kernel=None;changed=False;process=None;old_exited=False
    def report(phase,message,**extra):atomic_json(folder/'result.json',{'phase':phase,'message':message,**extra})
    try:
        data,folder,target,source=validate_job(path,sys.executable)
        kernel,handles=open_processes(data['pids'],target)
        report('waiting','等待后台正常退出；Photoshop 保持运行')
        atomic_json(folder/'helper-ready.json',{'id':data['id'],'ready':True})
        wait_processes(kernel,handles)
        old_exited=True
        if sha256(target)!=data['old_sha256']:raise ValueError('运行入口在等待期间已改变，未安装更新')
        if sha256(source)!=data['new_sha256'] or executable_version(source)!=data['new_version']:
            raise ValueError('暂存应用在等待期间已改变，未安装更新')
        backup=folder/'previous-PhotoshopMenu.exe';shutil.copy2(target,backup)
        receipt=Path(data['runtime'])/'offline-install.json'
        if receipt.exists():shutil.copy2(receipt,folder/'previous-offline-install.json')
        report('replacing','安装已校验的应用；保留旧版本以便恢复')
        replace(source,target);changed=True
        update_receipt(Path(data['runtime']),target,data['old_sha256'],data['new_sha256'],data['new_version'])
        process=launch(target,data)
        client=build_opener(ProxyHandler({}));deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            try:
                with client.open(f"http://127.0.0.1:{data['port']}/api/health",timeout=1) as response:health=json.load(response)
                if health_matches(health,target,data['new_version']) and sha256(target)==data['new_sha256']:
                    report('completed','应用更新完成，启动入口已就绪；UXP 安装状态请在插件管理中查看',version=data['new_version']);return
            except (OSError,ValueError):pass
            if process.poll() is not None:break
            time.sleep(.5)
        raise RuntimeError('新后台尚未确认启动及桌面组件就绪，检查更新记录；不会强制结束进程')
    except Exception as error:
        if not (folder/'helper-ready.json').exists():
            atomic_json(folder/'helper-ready.json',{'id':folder.name,'ready':False,'error':str(error)[:600]})
        # Restore only when the new entry is not running. Never force-stop it.
        if changed and process is not None and process.poll() is None:
            report('error',str(error)[:600],manual_recovery=str(folder/'previous-PhotoshopMenu.exe'));return
        if changed:
            try:
                replace(folder/'previous-PhotoshopMenu.exe',target)
                saved=folder/'previous-offline-install.json'
                if saved.exists():shutil.copy2(saved,Path(data['runtime'])/'offline-install.json')
                launch(target,data)
                report('rolled-back','新版启动失败，已恢复旧后台；未修改配置和 Photoshop 文档',error=str(error)[:600]);return
            except Exception as rollback_error:
                report('error',str(error)[:400]+'；恢复失败：'+str(rollback_error)[:200],manual_recovery=str(folder/'previous-PhotoshopMenu.exe'));return
        if old_exited:
            try:
                if sha256(target)==data['old_sha256']:
                    launch(target,data)
                    report('rolled-back','安装未完成，已重新启动原后台；没有修改 Photoshop 文档',error=str(error)[:600]);return
            except Exception:pass
        report('error',str(error)[:600])
    finally:
        if kernel:
            for handle in handles:kernel.CloseHandle(handle)


def cli():
    parser=argparse.ArgumentParser();parser.add_argument('job',type=Path)
    apply(parser.parse_args().job)
