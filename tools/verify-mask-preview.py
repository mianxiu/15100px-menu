"""Opt-in real UXP preview transactions on owned PS documents; no input injection.

Default: two logical processors and below-normal PS priority, short batches.
--normal adds the comparison without resource limits. Does not emulate RAM/GPU.
"""
import argparse,ast,asyncio,copy,json,shutil,sys,time
from pathlib import Path
from urllib.request import urlopen
from contextlib import nullcontext
import win32com.client,win32gui,win32process

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools'))
from backend.uxp_bridge import UxpBridge
from backend.mask_preview import MaskPreview
from benchmark_read_helpers import fixture
from quiet_ps_session import inventory,select,place,ResourceLease,save


def live_idle():
    state=json.load(urlopen('http://127.0.0.1:15151/api/status',timeout=5));ps=state['photoshop']
    if ps['busy'] or state['menu']['visible'] or state['photoshop_start']['active'] or ps.get('uxp_recovery',{}).get('active'):
        raise RuntimeError('Live service is not idle')
    if ps.get('uxp_version')!='0.3.24' or not ps.get('uxp_ready'):raise RuntimeError('Loaded UXP24 required')
    if (Path(state['data_dir'])/'uxp-pending.json').exists():raise RuntimeError('Live request unresolved')
    return state


async def main(normal=False):
    state=live_idle();folder=ROOT/'.runtime'/('mask-preview-live-'+str(time.time_ns()));folder.mkdir()
    window,monitor=select(inventory());placement=place(inventory(),folder/'placement.json')
    initial=win32gui.GetForegroundWindow()
    if win32process.GetWindowThreadProcessId(initial)[1]==window['pid']:raise RuntimeError('PS is in use; no test started')
    config=folder/'uxp-config.json';shutil.copy2(Path(state['data_dir'])/'uxp-config.json',config)
    bridge=UxpBridge(folder/'tasks.json',config)
    app=win32com.client.GetActiveObject('Photoshop.Application');previous=app.ActiveDocument if app.Documents.Count else None
    # Read constants without importing the older executable verification script.
    tree=ast.parse((ROOT/'tools/verify-shape-paint.py').read_text('utf-8'))
    read_script=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='READ' for t in n.targets))
    read=lambda:json.loads(app.DoJavaScript(read_script))
    owned=None;cases=[];complete=False
    def guard():
        live_idle()
        if (ROOT/'.runtime/quiet-ps.stop').exists() or win32gui.GetForegroundWindow()!=initial:
            raise RuntimeError('Foreground changed or cooperative stop requested; no next operation')
    bridge.execution_guard=guard
    async def inspect():return (await asyncio.to_thread(bridge.transport.call,'inspect',shape_inspect=True))['shape_editor']
    def equal_content(a,b):
        for k in ('layerID','layerKind','adjustment','AGMStrokeStyleInfo','path','order','hasUserMask','userMaskFeather','userMaskDensity','vectorMaskFeather','vectorMaskDensity'):
            assert a.get(k)==b.get(k),(k,a.get(k),b.get(k))
    async def run_case(name,end='commit',hold=0,combined=False,return_original=False,stream=False,edge=False):
        guard();data=await inspect();assert data.get('mask') is not None
        params={k:copy.deepcopy(data[k]) for k in ('revision','fill','stroke','mask')}
        target=await asyncio.to_thread(bridge._capture_target);before=read()
        preview=MaskPreview(1,params);stopped=asyncio.Event();renew=True;error=[]
        async def publish():
            while not stopped.is_set():
                try:
                    if win32gui.GetForegroundWindow()!=initial:preview.cancel()
                    if renew:await asyncio.to_thread(preview.publish)
                except Exception as e:error.append(str(e));preview.cancel();return
                await asyncio.sleep(.08)
        publisher=asyncio.create_task(publish());started=time.perf_counter()
        operation=asyncio.create_task(bridge.execute_shape(params,frozen_target=target,preview=preview))
        async def applied(minimum=1):
            deadline=time.monotonic()+12
            while time.monotonic()<deadline:
                if operation.done():
                    await operation
                    raise AssertionError('Preview terminated before live readback')
                if preview.binding:
                    path=preview.binding[0]/('mask-preview-status-'+preview.binding[1]['id']+'.json')
                    try:
                        value=json.loads(path.read_text('utf-8-sig'))
                        if value.get('id')==preview.binding[1]['id'] and value.get('seq',0)>=minimum:return value
                    except (OSError,ValueError):pass
                await asyncio.sleep(.01)
            raise RuntimeError('Preview acknowledgement timed out; not resending')
        try:
            first=await applied();assert first['mask']==params['mask']
            for i in range(1,101):
                params['mask']={'feather':i/4,'density':100-i/2}
                preview.update(params)
                if stream:await asyncio.sleep(.02)
            ack=await applied(preview.seq)
            assert abs(ack['mask']['feather']-25)<.01 and abs(ack['mask']['density']-50)<=100/255+.001
            assert not operation.done(),'Live values must precede confirmation'
            if stream:assert ack['updates']>3 and ack['updates']<100
            if edge:
                params['mask']={'feather':1000,'density':0};preview.update(params)
                ack=await applied(preview.seq)
                assert abs(ack['mask']['feather']-1000)<.01 and ack['mask']['density']==0
            live_ms=(time.perf_counter()-started)*1000
            if hold:await asyncio.sleep(hold)
            if end=='lease':renew=False
            elif end=='cancel':preview.cancel()
            else:
                params['mask']={'feather':0,'density':100} if return_original else {'feather':12.5,'density':42}
                if combined:params['fill']['rgb']=[25,75,160]
                preview.update(params,commit=True)
            result=await asyncio.wait_for(asyncio.shield(operation),18)
            assert not bridge.busy and not bridge.transport.pending.value and not error
            after=read()
            if end!='commit':
                equal_content(before,after);assert after['historyCursor']==before['historyCursor']
                assert json.loads(result['result'])['rollback_verified']
            else:
                def value(v):return v['_value'] if isinstance(v,dict) else v
                assert abs(value(after['vectorMaskFeather'])-params['mask']['feather'])<.01
                assert abs(value(after['vectorMaskDensity'])*100/255-params['mask']['density'])<=100/255+.001
                assert after['historyCursor']==before['historyCursor']+1
                for k in ('layerID','path','order','hasUserMask','userMaskFeather','userMaskDensity'):
                    assert before.get(k)==after.get(k),(name,k)
                if not combined:
                    assert before['adjustment']==after['adjustment'] and before.get('AGMStrokeStyleInfo')==after.get('AGMStrokeStyleInfo')
                app.DoJavaScript('var d=app.activeDocument;d.activeHistoryState=d.historyStates[d.historyStates.length-2];')
                equal_content(before,read())
            proof={'case':name,'end':end,'one_undo':end=='commit','cancel_restored':end!='commit',
                   'live_before_confirmation':True,'live_readback_ms':round(live_ms,2),
                   'published_updates':100,'applied_updates_before_finish':ack['updates'],
                   'total_ms':round((time.perf_counter()-started)*1000,2),'task_id':result['task_id']}
            cases.append(proof);print(json.dumps(proof),flush=True)
        finally:
            if not operation.done():
                preview.cancel()
                try:await asyncio.wait_for(asyncio.shield(operation),12)
                except Exception:pass
            stopped.set();await publisher;preview.close()
    try:
        with (nullcontext() if normal else ResourceLease(window['pid'],folder/'resources.json',seconds=120)):
            for kind,count,size in [('shape',4,181),('mixed',40,1024)]:
                guard();app.DoJavaScript(fixture(kind,count));owned=app.ActiveDocument
                if size>181:app.DoJavaScript(f'app.activeDocument.resizeCanvas(UnitValue({size},"px"),UnitValue({size},"px"));')
                app.DoJavaScript("var s=stringIDToTypeID,d=new ActionDescriptor(),r=new ActionReference();d.putClass(s('new'),s('channel'));r.putEnumerated(s('channel'),s('channel'),s('mask'));d.putReference(s('at'),r);d.putEnumerated(s('using'),s('userMaskEnabled'),s('revealAll'));executeAction(s('make'),d,DialogModes.NO);")
                # Building a mixed fixture through COM can silence UXP's
                # heartbeat. Wait only for fresh readiness, never replay work.
                for attempt in range(50):
                    try:guard();break
                    except RuntimeError as error:
                        if 'Loaded UXP24 required' not in str(error):raise
                        await asyncio.sleep(.2)
                else:raise RuntimeError('UXP heartbeat did not resume after fixture creation')
                await run_case(kind+'-live-commit');await asyncio.sleep(2)
                await run_case(kind+'-cancel','cancel');await asyncio.sleep(2)
                await run_case(kind+'-combined-return-original',combined=True,return_original=True)
                if kind=='mixed' and not normal:
                    await asyncio.sleep(2);await run_case('live-mask-boundaries',edge=True)
                if kind=='shape' and not normal:
                    await asyncio.sleep(2);await run_case('continuous-drag-coalesced',stream=True)
                    await asyncio.sleep(2);await run_case('long-hold-over-initial-expiry',hold=6)
                    await asyncio.sleep(2);await run_case('lost-publisher-lease','lease')
                assert not bridge.busy and not bridge.transport.pending.value
                guard();owned.Close(2);owned=None
                await asyncio.sleep(4)
        complete=True
    finally:
        if owned is not None and not bridge.busy and not bridge.transport.pending.value and win32process.GetWindowThreadProcessId(win32gui.GetForegroundWindow())[1]!=window['pid']:
            owned.Close(2);owned=None
        if previous is not None and owned is None and not bridge.busy:app.ActiveDocument=previous
        report={'runtime_version':state['version'],'executor_version':'0.3.24','complete':complete,'normal':normal,
                'scope':'real UXP with native readback acknowledgements before confirmation; independent COM after terminal; no synthesized input',
                'physical_input':False,'cases':cases,'foreground_preserved':win32gui.GetForegroundWindow()==initial,
                'owned_document_closed':owned is None,'unresolved':bool(bridge.busy or bridge.transport.pending.value),'placement':placement}
        save(folder/'report.json',report);print('REPORT '+str(folder/'report.json'),flush=True)
        await bridge.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--normal',action='store_true')
    asyncio.run(main(parser.parse_args().normal))
