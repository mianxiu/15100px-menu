"""Opt-in, bounded native-window diagnostic. No Photoshop requests or input."""
import asyncio,json,os,uuid,time,math
from pathlib import Path

def trigger_summary(evidence):
    if evidence.get('enabled') is False:return 'menu_disabled'
    events=evidence.get('events',[])
    down=[e for e in events if e.get('message') in (0x100,0x104)]
    if not down:return 'no_trigger_keydown_observed'
    if any(e.get('matched_action')=='hold_begin' for e in down):return 'native_open_action_emitted'
    if not any(e.get('process_scope') for e in down):return 'outside_recognized_ps_process'
    if not any(e.get('activation_allowed') for e in down):return 'activation_not_qualified'
    if not any(e.get('command_scope') for e in down):return 'workspace_scope_rejected'
    return 'key_received_without_open_match'

class Diagnostics:
    def __init__(self,runtime,script,port):
        self.folder=Path(runtime)/'diagnostics';self.script=Path(script);self.port=port
        self.provider=None;self.listener=None;self.deadline=0;self.task=None;self.report=None;self.state={'phase':'idle','message':'尚未采集诊断'}

    def snapshot(self):
        return {**self.state,'ready':self.report is not None,
                'remaining_ms':max(0,math.ceil((self.deadline-time.monotonic())*1000)) if self.deadline else 0}

    def progress(self,stage,message,duration=0,**extra):
        self.deadline=time.monotonic()+duration/1000 if duration else 0
        self.state.update(stage=stage,message=message,**extra)
        if self.listener:self.listener(self.snapshot())

    async def read_progress(self,process):
        async for raw in process.stdout:
            line=raw.decode('utf-8',errors='replace').strip()
            if not line.startswith('PSMENU_PROGRESS '):continue
            try:
                event=json.loads(line[len('PSMENU_PROGRESS '):])
                stage=event['stage'];remaining=event.get('remaining_ms',0);completed=event.get('samples_done',0)
                if stage not in ('sampling','processing') or type(remaining) is not int or not 0<=remaining<=30000 or type(completed) is not int or not 0<=completed<=10:continue
            except (ValueError,KeyError,TypeError):continue
            self.progress(stage,'正在采集：请在PS中按菜单唤出键' if stage=='sampling' else '采集结束，正在整理报告',remaining,samples_done=completed,samples_total=10)


    def start(self):
        if self.task and not self.task.done():raise RuntimeError('诊断正在采集，请稍候')
        self.report=None;self.state={'phase':'collecting'};self.progress('prepare','准备：请切回PS并点击图层列表',5000,samples_done=0,samples_total=10)
        self.task=asyncio.create_task(self.collect());return self.snapshot()

    async def collect(self):
        process=None
        try:
            await asyncio.sleep(5)
            self.progress('starting','正在启动只读检测，请保持PS前台')
            self.folder.mkdir(parents=True,exist_ok=True)
            path=self.folder/(uuid.uuid4().hex+'.json')
            exe=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
            process=await asyncio.create_subprocess_exec(str(exe),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(self.script),'-BackendPort',str(self.port),'-OutputPath',str(path),'-DelaySeconds','0','-ProgressStream',stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,creationflags=0x08000000)
            await asyncio.wait_for(asyncio.gather(process.wait(),self.read_progress(process)),35)
            if process.returncode!=0 or not path.is_file():raise RuntimeError('native diagnostic failed')
            if path.stat().st_size>2*1024*1024:raise ValueError('report too large')
            report=json.loads(path.read_text('utf-8-sig'))
            if report.get('schema')!=2 or report.get('read_only') is not True:raise ValueError('invalid report')
            if self.provider:
                report['trigger_decisions']=self.provider()
                report['trigger_summary']=trigger_summary(report['trigger_decisions'])
            path.write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
            self.report=report;self.state={'phase':'completed'};self.progress('completed','诊断采集完成，可导出报告')
        except asyncio.CancelledError:
            self.state={'phase':'cancelled'};self.progress('cancelled','诊断采集已取消');raise
        except Exception:
            self.state={'phase':'failed'};self.progress('failed','诊断采集失败，请检查运行日志或使用独立检测脚本')
        finally:
            if process and process.returncode is None:
                process.kill();await process.wait() # Only our read-only diagnostic child.

    def export(self):
        if self.report is None:raise RuntimeError('请先完成一次诊断采集')
        return self.report

    async def close(self):
        if self.task and not self.task.done():
            self.task.cancel();await asyncio.gather(self.task,return_exceptions=True)
