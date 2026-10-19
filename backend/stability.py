"""One explicit, bounded, non-replaying real-host stability run."""
import asyncio
from copy import deepcopy
import json
import math
from pathlib import Path
import statistics
import time
import uuid

from .settings import atomic_json
from .uxp_bridge import UxpBridge, read_heartbeat
from .plugins import version
from .layer_context import validate, fresh
from .mask_preview import MaskPreview
from .stability_metrics import Metrics, machine_info, host_scope
from .version import APP_VERSION


class Stopped(RuntimeError):pass

STAGE_LABELS={'fixture':'正在创建隔离临时文档','idle-read':'正在检查闲置后的图层读取',
    'fixed-layer-label':'正在反复修改固定图层的标签','fixed-layer-read':'正在读取固定图层',
    'preview-commit-undo':'正在核验颜色／羽化确认与一次撤销','preview-cancel':'正在核验预览取消恢复',
    'grow-layer':'正在逐步增加图层','growing-layer-read':'正在读取新增图层',
    'select-many':'正在准备多选图层','multi-selection-read':'正在读取多选图层',
    'select-shape':'正在恢复测试形状选择','finish':'正在关闭测试文档并恢复原文档'}


def summary(rows):
    groups={}
    for row in rows:
        if row.get('state')=='passed':groups.setdefault(row['stage'],[]).append(row['elapsed_ms'])
    result={}
    for key,values in groups.items():
        ordered=sorted(values);part=max(1,len(values)//3)
        result[key]={'samples':len(values),'median_ms':statistics.median(values),
            'p95_ms':ordered[max(0,math.ceil(len(values)*.95)-1)],'max_ms':max(values),
            'first_third_median_ms':statistics.median(values[:part]),'last_third_median_ms':statistics.median(values[-part:])}
    return result


class StabilityTest:
    def __init__(self,app):
        self.app=app;self.folder=Path(app.runtime)/'stability-reports';self.task=None;self.active=False
        self.stop_requested=False;self.report={};self.write_lock=asyncio.Lock();self.preview=None
        try:
            value=json.loads((self.folder/'latest.json').read_text('utf-8'))
            if value.get('schema')==1:
                self.report=value
                if value.get('phase')=='running':
                    self.report.update(phase='interrupted',message='上次测试已中断；未自动续跑或清理临时文档',cleanup='retained-after-service-interruption')
                    for row in self.report.get('steps',[]):
                        if row.get('state')=='running':row['state']='interrupted'
                    try:
                        identity=self.report.get('run_id','')
                        if len(identity)==32 and all(c in '0123456789abcdef' for c in identity):atomic_json(self.folder/(identity+'.json'),self.report)
                        atomic_json(self.folder/'latest.json',self.report)
                    except OSError as error:self.report['save_error']=type(error).__name__
        except (OSError,ValueError):pass

    def snapshot(self):
        return {k:self.report.get(k) for k in ('run_id','phase','message','profile','round','rounds','stage','started_at','finished_at','error','summary','cleanup','save_error')} | {
            'active':self.active,'stop_requested':self.stop_requested,'ready':bool(self.report),
            'completed_steps':sum(row.get('state')!='running' for row in self.report.get('steps',[])), 'samples':len(self.report.get('system_samples',[]))}

    async def save(self):
        async with self.write_lock:
            data=deepcopy(self.report)
            await asyncio.to_thread(atomic_json,self.folder/(data['run_id']+'.json'),data)
            await asyncio.to_thread(atomic_json,self.folder/'latest.json',data)
        await self.app.broadcast({'type':'stability','data':self.snapshot()})

    async def start(self,profile='standard'):
        if profile not in ('standard','extended'):raise ValueError('未知测试模式')
        app=self.app
        if self.active or app.operation_lock.locked() or app.bridge.busy:raise RuntimeError('请等待当前操作结束；测试不排队')
        if not isinstance(app.bridge,UxpBridge):raise RuntimeError('自动测试需要 UXP 执行端')
        app.require_uxp_enabled()
        if getattr(app,'diagnostics',None) and app.diagnostics.snapshot().get('phase')=='collecting':raise RuntimeError('请等待只读诊断结束后再开始稳定性测试')
        if app.photoshop_launcher.active or app.desktop and app.desktop.visible:raise RuntimeError('请先收起菜单并等待 Photoshop 就绪')
        await app.operation_lock.acquire()
        self.active=True;self.stop_requested=False
        self.report={'schema':1,'run_id':uuid.uuid4().hex,'phase':'running','message':'正在准备隔离测试',
            'profile':profile,'rounds':3 if profile=='standard' else 10,'round':0,'stage':'preflight',
            'started_at':time.time(),'application_version':APP_VERSION,'steps':[],'system_samples':[],
            'cleanup':'not-created','scope':{'temporary_document_only':True,'changes_power_plan':False,
            'injects_input':False,'uploads':False,'original_documents_saved_or_closed':False},
            'not_tested':['physical_caps_and_UU_remote','mouse_hit_testing','visible_canvas','real_document_content',
                'GPU_causality','thermal_throttling_causality','other_OS_or_Photoshop_versions'],
            'skipped':[],'summary':{}}
        try:
            await self.save()
            await app.broadcast({'type':'operation','busy':True,'action':'stability.internal'})
        except Exception:
            self.active=False;app.operation_lock.release();raise
        self.task=asyncio.create_task(self.run())
        return self.snapshot()

    def stop(self):
        if self.active:
            self.stop_requested=True
            self.report['message']='停止后续测试；正在等待当前请求的真实结果'
            if self.preview:self.preview.cancel()
        return self.snapshot()

    def check(self):
        if self.stop_requested:raise Stopped('已停止后续测试')
        if time.time()-self.report['started_at']>1800:raise Stopped('已达到30分钟上限，停止后续测试')
        try:self.focus_check()
        except RuntimeError as error:raise Stopped(str(error)) from error

    async def before_dispatch(self,_):self.check()

    async def step(self,stage,operation):
        self.check();self.report.update(stage=stage,message=STAGE_LABELS.get(stage,stage))
        row={'stage':stage,'round':self.report['round'],'started_at':time.time(),'state':'running'}
        self.report['steps'].append(row);await self.save();started=time.monotonic()
        try:
            value=await operation()
            row.update(state='skipped' if isinstance(value,dict) and value.get('skipped') else 'passed',elapsed_ms=round((time.monotonic()-started)*1000,3))
            if row['state']=='skipped':self.report['skipped'].append({'stage':stage,'reason':value['skipped']})
            if isinstance(value,dict):row['evidence']=value
            return value
        except Exception as error:
            row.update(state='stopped' if isinstance(error,Stopped) else 'failed',elapsed_ms=round((time.monotonic()-started)*1000,3),error=str(error)[:500])
            raise
        finally:
            self.report['summary']=summary(self.report['steps']);await self.save()

    async def command(self,step,**values):
        result=await self.app.bridge.execute_stability(self.report['run_id'],step,self.before_dispatch,**values)
        value=json.loads(result['result']);value['task_id']=result['task_id']
        task=self.app.bridge.tasks.get(result['task_id'])
        value['task_timeline']=[{key:item.get(key) for key in ('state','start_elapsed_ms','duration_ms')} for item in task.get('timeline',[])]
        return value

    async def inspect(self):
        self.check()
        value=await asyncio.to_thread(self.app.bridge.transport.call,'inspect',stability_run=self.report['run_id'],shape_inspect=True)
        return {'stability':value['stability'],'shape_editor':value.get('shape_editor',{})}

    async def menu_read(self):
        expected=(await self.inspect())['stability']['target']
        bridge=self.app.bridge;started=time.monotonic()
        request=await asyncio.to_thread(bridge.request_menu_context,len(self.report['steps']))
        if not request:raise RuntimeError('图层读取请求不受支持')
        phases={};deadline=request['deadline']
        try:
            while time.monotonic()<deadline:
                self.check()
                try:
                    raw=await asyncio.to_thread((request['folder']/'menu-context-result.json').read_text,'utf-8-sig')
                    value=json.loads(raw)
                except (OSError,ValueError):value={}
                if value.get('session')==request['session'] and value.get('menu_request_id')==request['id']:
                    phase=value.get('menu_phase');phases.setdefault(str(phase),round((time.monotonic()-started)*1000,3))
                    if phase=='reading':deadline=request['completion_deadline']
                    if phase=='completed':
                        value=validate(value,request['session'])
                        if not fresh(value) or value.get('kind') in ('none','unknown') or any(value.get(k)!=expected[k] for k in ('document_id','layer_ids')):
                            raise RuntimeError('新鲜图层读取身份或能力校验失败')
                        return {'request_id':request['id'],'phases_ms':phases,'kind':value['kind'],
                            'mask':value['mask'],'quick_mask':value.get('quick_mask'),
                            'snapshot_age_ms':round(time.time()*1000-value['plugin_time_ms'],2),
                            'timings_ms':value.get('timings_ms',{})}
                await asyncio.sleep(.04)
            raise RuntimeError('图层读取超过固定期限；保留原请求，未重发')
        finally:await asyncio.to_thread(bridge.cancel_menu_context,request)

    async def paint(self,cancel=False):
        baseline=await self.inspect();shape=baseline['shape_editor'];checkpoint=baseline['stability']['history_id']
        if not shape.get('available') or 'mask' not in shape:raise RuntimeError('测试形状颜色／羽化能力缺失')
        params={k:deepcopy(shape[k]) for k in ('revision','fill','stroke','mask')}
        params['fill']['rgb']=[210,60,30];params['mask']={'feather':4.5,'density':77}
        bridge=self.app.bridge;frames=[]
        if shape.get('live_preview'):
            preview=self.preview=MaskPreview(len(self.report['steps']),params,trace=True)
            task=asyncio.create_task(bridge.execute_shape(params,before_dispatch=self.before_dispatch,preview=preview,_stability_run=self.report['run_id']))
            # Keep the original request alive only while we are testing it.
            async def pump():
                while not task.done():
                    await asyncio.to_thread(preview.publish);await asyncio.sleep(.08)
            publisher=asyncio.create_task(pump())
            try:
                for index in range(2):
                    limit=time.monotonic()+30
                    while True:
                        self.check()
                        if publisher.done():await publisher
                        if task.done():await task;raise RuntimeError('预览在确认前结束')
                        progress=await asyncio.to_thread(preview.progress)
                        if progress and progress['stage']=='ready' and progress['frame']>=preview.seq:
                            frames.append(progress);break
                        if time.monotonic()>limit:raise RuntimeError('预览帧等待超时，等待原请求恢复')
                        await asyncio.sleep(.08)
                    if index==0:
                        params['fill']['rgb']=[20,80,180];params['mask']={'feather':12.5,'density':42}
                        preview.update(params)
                if cancel:preview.cancel()
                else:preview.update(params,commit=True)
                result=await asyncio.wait_for(asyncio.shield(task),120)
            except Exception:
                preview.cancel()
                try:await asyncio.wait_for(asyncio.shield(task),120)
                except Exception:pass
                raise
            finally:
                publisher.cancel();await asyncio.gather(publisher,return_exceptions=True)
                preview.close();self.preview=None
                if not task.done():task.add_done_callback(lambda future:future.exception() if not future.cancelled() else None)
        else:
            if cancel:
                return {'skipped':'live-preview-unavailable','host_supports_commit_only':True}
            result=await bridge.execute_shape(params,before_dispatch=self.before_dispatch,_stability_run=self.report['run_id'])
        after=await self.inspect()
        def same_paint(left,right):
            for key in ('fill','stroke','mask'):
                if key=='mask':
                    if any(abs(left[key][field]-right[key][field])>.4 for field in ('feather','density')):return False
                elif key=='fill':
                    if any(abs(a-b)>1 for a,b in zip(left[key]['rgb'],right[key]['rgb'])):return False
                elif left[key]!=right[key]:return False
            return True
        if not same_paint(after['shape_editor'],shape if cancel else params):raise RuntimeError('颜色／羽化读回不匹配')
        if cancel:
            if after['stability']['history_id']!=checkpoint:raise RuntimeError('取消未恢复历史检查点')
        else:
            await self.command('undo',restore_history=checkpoint)
            restored=await self.inspect()
            if not same_paint(restored['shape_editor'],shape):raise RuntimeError('一次撤销未恢复原颜色／羽化')
        return {'live_preview':bool(shape.get('live_preview')),'engine':shape.get('preview_engine','uxp'),
            'frames':frames,'task_id':result['task_id'],'readback_verified':True,'cancel_restored':cancel,'one_undo_verified':not cancel}

    async def monitor(self):
        metrics=None;report=self.report
        try:
            metrics=await asyncio.to_thread(Metrics,self.host_pid)
            while self.active and self.report is report:
                await asyncio.sleep(1)
                row=await asyncio.to_thread(metrics.sample)
                if self.report is not report:break
                row['stage']=self.report.get('stage');row['round']=self.report.get('round')
                task_id=getattr(self.app.bridge,'_active_task_id',None)
                if task_id:
                    try:
                        task=self.app.bridge.tasks.get(task_id)
                        row['task']={k:task.get(k) for k in ('id','state','elapsed_ms')}
                    except ValueError:pass
                pending=self.app.bridge.transport.pending.value
                if pending:
                    row['request']={k:pending.get(k) for k in ('id','session','operation','task_id')}
                    try:
                        evidence=await asyncio.to_thread((Path(pending['folder'])/('execution-'+pending['id']+'.json')).read_text,'utf-8-sig')
                        value=json.loads(evidence)
                        if all(value.get(k)==pending[k] for k in ('id','session','operation')):
                            row['execution']={k:value.get(k) for k in ('stage','stage_started_at_ms','seq','plugin_time_ms')}
                    except (OSError,ValueError):pass
                self.report['system_samples'].append(row)
                if len(self.report['system_samples'])>1900:self.report['system_samples'].pop(0)
                try:await self.save()
                except Exception as error:self.report['save_error']=type(error).__name__;self.stop_requested=True
        except Exception as error:report['metrics_unavailable']=type(error).__name__
        finally:
            if metrics:await asyncio.to_thread(metrics.close)

    async def run(self):
        monitor=None;owned=False
        try:
            self.host_pid,self.focus_check=await asyncio.to_thread(host_scope)
            heartbeat=await asyncio.to_thread(lambda:read_heartbeat(self.app.bridge.transport.folder))
            self.report['versions']={k:heartbeat.get(k) for k in ('probe_version','photoshop_version','session','document_redraw_available','legacy_preview_available')}
            if version(heartbeat.get('probe_version'))<(0,3,46):raise RuntimeError('请先更新并实际加载 UXP 0.3.46')
            monitor=asyncio.create_task(self.monitor())
            self.report['machine']=await asyncio.to_thread(machine_info)
            desktop=self.app.desktop
            self.report['menu_components']={'renderer':getattr(desktop,'graphics',{}),
                'menu_process_alive':bool(desktop and desktop.process and desktop.process.poll() is None),
                'hotkey_process_alive':bool(desktop and desktop.native and desktop.native.poll() is None),
                'visible_content_and_physical_input_verified':False}
            self.report['cleanup']='fixture-started-outcome-not-yet-verified'
            await self.step('fixture',lambda:self.command('fixture'));owned=True;self.report['cleanup']='owned-document-retained'
            for round_number in range(1,self.report['rounds']+1):
                self.report['round']=round_number
                await self.step('idle-read',self.menu_read)
                for i in range(8):
                    await self.step('fixed-layer-label',lambda i=i:self.command('label',test_color='red' if i%2==0 else 'blue'))
                    await self.step('fixed-layer-read',self.menu_read)
                await self.step('preview-commit-undo',self.paint)
                await self.step('preview-cancel',lambda:self.paint(True))
                for i in range(8):
                    await self.step('grow-layer',lambda:self.command('layer.new'))
                    await self.step('growing-layer-read',self.menu_read)
                await self.step('select-many',lambda:self.command('select-many'))
                await self.step('multi-selection-read',self.menu_read)
                await self.step('select-shape',lambda:self.command('select-shape'))
                self.report.update(stage='idle',message='闲置后继续检查首次读取');await self.save()
                for _ in range(10):self.check();await asyncio.sleep(1)
            await self.step('finish',lambda:self.command('finish'));owned=False
            self.report.update(phase='completed',message='自动测试完成，报告已保存',cleanup='verified-closed-and-original-restored')
        except Stopped as error:
            self.report.update(phase='stopped',message=str(error))
        except Exception as error:
            self.report.update(phase='failed',message='测试已停止，已保留故障证据',error=str(error)[:500])
        finally:
            # Never guess whether a timed-out mutation finished. No rollback,
            # close, resend or new host reads from this failure path.
            if owned:self.report['cleanup']='retained-for-inspection-no-automatic-cleanup'
            self.report['original_request_pending']=bool(self.app.bridge.busy or self.app.bridge.transport.pending.value or self.app.bridge.transport.pending.error)
            self.active=False
            if monitor:
                try:await asyncio.wait_for(asyncio.shield(monitor),5)
                except asyncio.TimeoutError:pass
            self.report['finished_at']=time.time();self.report['summary']=summary(self.report['steps'])
            self.report['findings']=[]
            for stage,data in self.report['summary'].items():
                if data['samples']>=6 and data['last_third_median_ms']>max(500,2*data['first_third_median_ms']):
                    self.report['findings'].append({'code':'progressive-slowdown-observed','stage':stage})
            if self.report.get('metrics_unavailable') or any(x.get('unavailable') for x in self.report.get('system_samples',[])):
                self.report['findings'].append({'code':'some-system-counters-unavailable'})
            self.report['interpretation']='Timing and resource observations only; low total CPU or low frequency alone does not identify Windows, GPU, thermal or power causality.'
            try:await self.save()
            finally:
                self.app.operation_lock.release()
                await self.app.broadcast({'type':'operation','busy':self.app.bridge.busy})

    def export(self):
        if not self.report:raise ValueError('还没有测试报告')
        return deepcopy(self.report)

    async def close(self):
        self.stop()
        if self.task and not self.task.done():await asyncio.shield(self.task)
