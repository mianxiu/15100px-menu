"""Read-only Windows counters. Missing/invalid counters remain missing, never zero."""
import ctypes
from ctypes import wintypes as w
import json
import math
import os
import platform
import subprocess
import time


def machine_info():
    script="""$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[Text.UTF8Encoding]::new();
    @{cpu=@(Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed);
      gpu=@(Get-CimInstance Win32_VideoController | Select-Object Name,DriverVersion);
      os=Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,BuildNumber,TotalVisibleMemorySize;
      power_plan=(powercfg /getactivescheme | Out-String).Trim()} | ConvertTo-Json -Depth 4 -Compress"""
    result={'platform':platform.platform(),'logical_processors':os.cpu_count()}
    try:
        raw=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],
            capture_output=True,timeout=20,creationflags=0x08000000,check=True)
        result.update(json.loads(raw.stdout.decode('utf-8-sig')))
    except Exception as error:result['inventory_unavailable']=type(error).__name__
    return result


def host_scope():
    """Pin the PS process; tests may run under any foreground app (user authorization)."""
    import win32api,win32process
    def identity(pid):
        handle=win32api.OpenProcess(0x410,False,pid)
        try:
            return (os.path.basename(win32process.GetModuleFileNameEx(handle,0)).lower(),
                    win32process.GetProcessTimes(handle)['CreationTime'])
        finally:handle.Close()
    hosts=[]
    for pid in win32process.EnumProcesses():
        try:
            value=identity(pid)
            if value[0]=='photoshop.exe':hosts.append((pid,value))
        except Exception:pass
    if len(hosts)!=1:raise RuntimeError('测试需要一个已运行的 Photoshop 实例')
    pid,original=hosts[0]
    def check():
        try:current=identity(pid)
        except Exception:raise RuntimeError('原 Photoshop 进程无法确认，测试停止；未提交下一步') from None
        if current!=original:raise RuntimeError('Photoshop 进程身份已变化，测试停止；未提交下一步')
    return pid,check


class CounterValue(ctypes.Structure):
    _fields_=[('status',w.DWORD),('value',ctypes.c_double)]


class Metrics:
    def __init__(self,pid):
        import win32api
        self.pid=pid;self.previous=None;self.query=w.HANDLE();self.counters={};self.unavailable={}
        self.process=win32api.OpenProcess(0x410,False,pid)
        self.pdh=ctypes.WinDLL('pdh')
        self.pdh.PdhOpenQueryW.argtypes=[w.LPCWSTR,ctypes.c_size_t,ctypes.POINTER(w.HANDLE)]
        self.pdh.PdhAddEnglishCounterW.argtypes=[w.HANDLE,w.LPCWSTR,ctypes.c_size_t,ctypes.POINTER(w.HANDLE)]
        self.pdh.PdhCollectQueryData.argtypes=[w.HANDLE]
        self.pdh.PdhGetFormattedCounterValue.argtypes=[w.HANDLE,w.DWORD,ctypes.POINTER(w.DWORD),ctypes.POINTER(CounterValue)]
        self.pdh.PdhCloseQuery.argtypes=[w.HANDLE]
        if self.pdh.PdhOpenQueryW(None,0,ctypes.byref(self.query)):
            self.process.Close();raise RuntimeError('PDH unavailable')
        paths={'cpu_total_percent':r'\Processor(_Total)\% Processor Time',
            'cpu_frequency_mhz':r'\Processor Information(_Total)\Processor Frequency',
            'cpu_performance_percent':r'\Processor Information(_Total)\% Processor Performance',
            'available_memory_bytes':r'\Memory\Available Bytes',
            'disk_queue':r'\PhysicalDisk(_Total)\Current Disk Queue Length',
            'disk_transfer_seconds':r'\PhysicalDisk(_Total)\Avg. Disk sec/Transfer'}
        for i in range(min(os.cpu_count() or 1,256)):paths['cpu_'+str(i)+'_percent']=rf'\Processor({i})\% Processor Time'
        for key,path in paths.items():
            counter=w.HANDLE();status=self.pdh.PdhAddEnglishCounterW(self.query,path,0,ctypes.byref(counter))
            if status:self.unavailable[key]=hex(status & 0xffffffff)
            else:self.counters[key]=counter
        self.pdh.PdhCollectQueryData(self.query)

    def sample(self):
        import win32process
        started=time.monotonic();row={'time_ms':int(time.time()*1000),'unavailable':dict(self.unavailable)}
        collected=self.pdh.PdhCollectQueryData(self.query)
        for key,counter in self.counters.items():
            value=CounterValue();status=self.pdh.PdhGetFormattedCounterValue(counter,0x200,None,ctypes.byref(value))
            if not collected and not status and value.status in (0,1) and math.isfinite(value.value):row[key]=round(value.value,4)
            else:row['unavailable'][key]=hex((collected or status or value.status)&0xffffffff)
        try:
            times=win32process.GetProcessTimes(self.process)
            seconds=(times['KernelTime']+times['UserTime'])/10000000
            if self.previous:
                elapsed=started-self.previous[0]
                row['ps_cpu_one_core_percent']=round(100*(seconds-self.previous[1])/elapsed,3)
                row['ps_cpu_total_percent']=row['ps_cpu_one_core_percent']/(os.cpu_count() or 1)
            self.previous=(started,seconds)
            memory=win32process.GetProcessMemoryInfo(self.process)
            row.update(ps_working_set_bytes=memory['WorkingSetSize'],ps_private_bytes=memory.get('PagefileUsage'))
            row['ps_priority_class']=win32process.GetPriorityClass(self.process)
            row['ps_affinity_mask']=win32process.GetProcessAffinityMask(self.process)[0]
        except Exception as error:row['unavailable']['photoshop_process']=type(error).__name__
        row['collector_ms']=round((time.monotonic()-started)*1000,3)
        return row

    def close(self):
        self.pdh.PdhCloseQuery(self.query);self.process.Close()
