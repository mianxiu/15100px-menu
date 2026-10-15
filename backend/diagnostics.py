"""Opt-in, bounded native-window diagnostic. No Photoshop requests or input."""
import asyncio,json,os,uuid
from pathlib import Path

class Diagnostics:
    def __init__(self,runtime,script,port):
        self.folder=Path(runtime)/'diagnostics';self.script=Path(script);self.port=port
        self.task=None;self.report=None;self.state={'phase':'idle','message':'尚未采集诊断'}

    def snapshot(self):return {**self.state,'ready':self.report is not None}

    def start(self):
        if self.task and not self.task.done():raise RuntimeError('诊断正在采集，请稍候')
        self.report=None;self.state={'phase':'collecting','message':'5秒内切回 PS，按当前菜单唤出键并停留约10秒'}
        self.task=asyncio.create_task(self.collect());return self.snapshot()

    async def collect(self):
        process=None
        try:
            self.folder.mkdir(parents=True,exist_ok=True)
            path=self.folder/(uuid.uuid4().hex+'.json')
            exe=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
            process=await asyncio.create_subprocess_exec(str(exe),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(self.script),'-BackendPort',str(self.port),'-OutputPath',str(path),stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL,creationflags=0x08000000)
            await asyncio.wait_for(process.wait(),35)
            if process.returncode!=0 or not path.is_file():raise RuntimeError('native diagnostic failed')
            if path.stat().st_size>2*1024*1024:raise ValueError('report too large')
            report=json.loads(path.read_text('utf-8-sig'))
            if report.get('schema')!=2 or report.get('read_only') is not True:raise ValueError('invalid report')
            self.report=report;self.state={'phase':'completed','message':'诊断采集完成，可导出报告'}
        except asyncio.CancelledError:raise
        except Exception:
            self.state={'phase':'failed','message':'诊断采集失败，请检查运行日志或使用独立检测脚本'}
        finally:
            if process and process.returncode is None:
                process.kill();await process.wait() # Only our read-only diagnostic child.

    def export(self):
        if self.report is None:raise RuntimeError('请先完成一次诊断采集')
        return self.report

    async def close(self):
        if self.task and not self.task.done():
            self.task.cancel();await asyncio.gather(self.task,return_exceptions=True)
