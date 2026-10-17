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
    if ps.get('uxp_version')!='0.3.25' or not ps.get('uxp_ready'):raise RuntimeError('Loaded UXP25 required')
    if (Path(state['data_dir'])/'uxp-pending.json').exists():raise RuntimeError('Live request unresolved')
    return state


async def main(normal=False):
    state=live_idle();folder=ROOT/'.runtime'/('paint-preview-live-'+str(time.time_ns()));folder.mkdir()
    window,monitor=select(inventory());placement=place(inventory(),folder/'placement.json')
    initial=win32gui.GetForegroundWindow()
    if win32process.GetWindowThreadProcessId(initial)[1]==window['pid']:raise RuntimeError('PS is in use; no test started')
    config=folder/'uxp-config.json';shutil.copy2(Path(state['data_dir'])/'uxp-config.json',config)
    bridge=UxpBridge(folder/'tasks.json',config)
    app=win32com.client.GetActiveObject('Photoshop.Application');previous=app.ActiveDocument if app.Documents.Count else None
    # Read constants without importing the older executable verification script.
    tree=ast.parse((ROOT/'tools/verify-shape-paint.py').read_text('utf-8'))
    helper=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='make_content')
    namespace={'json':json};exec(compile(ast.Module(body=[helper],type_ignores=[]),'owned-fill-fixture','exec'),namespace)
    make_content=namespace['make_content']
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
    async def run_case(name,channel='fill',end='commit',gradient=False,stream=False,cross=False):
        guard();data=await inspect()
        if gradient and data[channel]['kind']!='gradient':
            setup={k:copy.deepcopy(data[k]) for k in ('revision','fill','stroke','mask') if k in data}
            setup[channel]={'kind':'gradient','enabled':True,'stops':[{'location':0,'rgb':[12,34,56]},{'location':4096,'rgb':[220,230,240]}],**({'width':3} if channel=='stroke' else {})}
            await bridge.execute_shape(setup,frozen_target=await asyncio.to_thread(bridge._capture_target))
            data=await inspect()
        params={k:copy.deepcopy(data[k]) for k in ('revision','fill','stroke','mask') if k in data}
        target=await asyncio.to_thread(bridge._capture_target);before=read()
        preview=MaskPreview(1,params);stopped=asyncio.Event();error=[]
        async def publish():
            while not stopped.is_set():
                try:
                    if win32gui.GetForegroundWindow()!=initial:preview.cancel()
                    await asyncio.to_thread(preview.publish)
                except Exception as e:error.append(str(e));preview.cancel();return
                await asyncio.sleep(.08)
        publisher=asyncio.create_task(publish());started=time.perf_counter()
        operation=asyncio.create_task(bridge.execute_shape(params,frozen_target=target,preview=preview))
        async def applied(minimum=1):
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                if operation.done():
                    await operation
                    raise AssertionError('Preview terminated before live color readback')
                if preview.binding:
                    path=preview.binding[0]/('mask-preview-status-'+preview.binding[1]['id']+'.json')
                    try:
                        value=json.loads(path.read_text('utf-8-sig'))
                        if value.get('id')==preview.binding[1]['id'] and value.get('seq',0)>=minimum:return value
                    except (OSError,ValueError):pass
                await asyncio.sleep(.01)
            raise RuntimeError('Preview acknowledgement timed out; not resending')
        def color(p):return p['stops'][0]['rgb'] if p['kind']=='gradient' else p['rgb']
        def alter(rgb):
            p=params[channel];p['enabled']=True
            if p['kind']=='gradient':p['stops'][0]['rgb']=rgb
            else:p['rgb']=rgb
            if channel=='stroke':p['width']=3
        try:
            await applied()
            for i in range(1,101):
                alter([i,70,190]);preview.update(params)
                if stream:await asyncio.sleep(.02)
            ack=await applied(preview.seq)
            assert all(abs(a-b)<=1 for a,b in zip(color(ack[channel]),[100,70,190])),ack
            assert not operation.done(),'Live color must precede confirmation'
            if stream:assert 3<ack['updates']<100
            if cross:
                params['fill']['enabled']=False;preview.update(params)
                ack=await applied(preview.seq)
                assert not ack['fill']['enabled'] and ack['stroke']['enabled']
                assert all(abs(a-b)<=1 for a,b in zip(color(ack['stroke']),[100,70,190]))
            live_ms=(time.perf_counter()-started)*1000
            if end=='cancel':preview.cancel()
            else:alter([17,61,153]);preview.update(params,commit=True)
            result=await asyncio.wait_for(asyncio.shield(operation),20)
            assert not bridge.busy and not bridge.transport.pending.value and not error
            after=read()
            save(folder/(name+'-readback.json'),{'before':before,'after':after})
            if end=='cancel':
                equal_content(before,after);assert after['historyCursor']==before['historyCursor']
                assert json.loads(result['result'])['rollback_verified']
            else:
                assert after['historyCursor']==before['historyCursor']+1
                confirmed=await inspect()
                if cross:assert not confirmed['fill']['enabled'] and confirmed['stroke']['enabled']
                assert all(abs(a-b)<=1 for a,b in zip(color(confirmed[channel]),[17,61,153]))
                for k in ('layerID','layerKind','path','order','hasUserMask','userMaskFeather','userMaskDensity','vectorMaskFeather','vectorMaskDensity'):
                    assert before.get(k)==after.get(k),(name,k)
                if channel=='stroke':assert before['adjustment']==after['adjustment']
                if channel=='fill':assert before.get('AGMStrokeStyleInfo')==after.get('AGMStrokeStyleInfo')
                if gradient:
                    old=before['adjustment'][0] if channel=='fill' else before['AGMStrokeStyleInfo']['strokeStyleContent']
                    new=after['adjustment'][0] if channel=='fill' else after['AGMStrokeStyleInfo']['strokeStyleContent']
                    for k in ('angle','scale','type','align','reverse','dither'):assert old.get(k)==new.get(k),(name,k)
                    assert old['gradient']['transparency']==new['gradient']['transparency']
                    assert [v['midpoint'] for v in old['gradient']['colors']]==[v['midpoint'] for v in new['gradient']['colors']]
                app.DoJavaScript('var d=app.activeDocument;d.activeHistoryState=d.historyStates[d.historyStates.length-2];')
                equal_content(before,read())
            proof={'case':name,'end':end,'channel':channel,'one_undo':end=='commit','cancel_restored':end=='cancel',
                   'live_before_confirmation':True,'live_readback_ms':round(live_ms,2),
                   'published_updates':100,'applied_updates_before_finish':ack['updates'],
                   'max_write_ms':ack['max_write_ms'],'total_ms':round((time.perf_counter()-started)*1000,2),'task_id':result['task_id']}
            cases.append(proof);print(json.dumps(proof),flush=True)
        finally:
            if not operation.done():
                preview.cancel()
                try:await asyncio.wait_for(asyncio.shield(operation),12)
                except Exception:pass
            stopped.set();await publisher;preview.close()
    try:
        with (nullcontext() if normal else ResourceLease(window['pid'],folder/'resources.json',seconds=240)):
            for kind,count,size in [('shape',4,181),('mixed',40,1024)]:
                guard();app.DoJavaScript(fixture(kind,count));owned=app.ActiveDocument
                if size>181:app.DoJavaScript(f'app.activeDocument.resizeCanvas(UnitValue({size},"px"),UnitValue({size},"px"));')
                app.DoJavaScript("var s=stringIDToTypeID,d=new ActionDescriptor(),r=new ActionReference();d.putClass(s('new'),s('channel'));r.putEnumerated(s('channel'),s('channel'),s('mask'));d.putReference(s('at'),r);d.putEnumerated(s('using'),s('userMaskEnabled'),s('revealAll'));executeAction(s('make'),d,DialogModes.NO);")
                # Building a mixed fixture through COM can silence UXP's
                # heartbeat. Wait only for fresh readiness, never replay work.
                for attempt in range(50):
                    try:guard();break
                    except RuntimeError as error:
                        if 'Loaded UXP25 required' not in str(error):raise
                        await asyncio.sleep(.2)
                else:raise RuntimeError('UXP heartbeat did not resume after fixture creation')
                await run_case(kind+'-fill-commit');await asyncio.sleep(2)
                await run_case(kind+'-fill-cancel',end='cancel');await asyncio.sleep(2)
                await run_case(kind+'-stroke-commit',channel='stroke');await asyncio.sleep(2)
                await run_case(kind+'-stroke-then-fill-toggle',channel='stroke',cross=True);await asyncio.sleep(2)
                if not normal:
                    await run_case(kind+'-cross-cancel',channel='stroke',cross=True,end='cancel');await asyncio.sleep(2)
                    await run_case(kind+'-stroke-cancel',channel='stroke',end='cancel');await asyncio.sleep(2)
                    await run_case(kind+'-gradient-fill',gradient=True);await asyncio.sleep(2)
                    await run_case(kind+'-gradient-fill-cancel',gradient=True,end='cancel');await asyncio.sleep(2)
                    await run_case(kind+'-gradient-stroke',channel='stroke',gradient=True);await asyncio.sleep(2)
                    if kind=='shape':
                        await run_case('continuous-color-drag-coalesced',gradient=True,stream=True);await asyncio.sleep(2)
                    # Plain solid fill: same editor, no vector-mask getters or type conversion.
                    app.DoJavaScript("var s=stringIDToTypeID,d=new ActionDescriptor(),r=new ActionReference();r.putClass(s('contentLayer'));d.putReference(s('null'),r);var t=new ActionDescriptor(),f=new ActionDescriptor(),c=new ActionDescriptor();c.putDouble(s('red'),30);c.putDouble(s('grain'),60);c.putDouble(s('blue'),90);f.putObject(s('color'),s('RGBColor'),c);t.putObject(s('type'),s('solidColorLayer'),f);d.putObject(s('using'),s('contentLayer'),t);executeAction(s('make'),d,DialogModes.NO);")
                    await run_case(kind+'-plain-fill-commit');await asyncio.sleep(2)
                    await run_case(kind+'-plain-fill-cancel',end='cancel')
                    raw_gradient={'_obj':'gradientLayer','type':{'_enum':'gradientType','_value':'linear'},
                        'angle':{'_unit':'angleUnit','_value':37},'scale':{'_unit':'percentUnit','_value':82},
                        'gradient':{'_obj':'gradientClassEvent','name':'Menu owned preview',
                            'gradientForm':{'_enum':'gradientForm','_value':'customStops'},'interfaceIconFrameDimmed':4096,
                            'colors':[{'_obj':'colorStop','color':{'_obj':'RGBColor','red':c,'grain':c,'blue':c},
                                'type':{'_enum':'colorStopType','_value':'userStop'},'location':loc,'midpoint':37} for c,loc in ((0,0),(255,4096))],
                            'transparency':[{'_obj':'transferSpec','opacity':{'_unit':'percentUnit','_value':73},
                                'location':loc,'midpoint':29} for loc in (0,4096)]}}
                    guard();app.DoJavaScript(make_content(raw_gradient))
                    await run_case(kind+'-plain-gradient-commit',gradient=True);await asyncio.sleep(2)
                    await run_case(kind+'-plain-gradient-cancel',gradient=True,end='cancel')
                assert not bridge.busy and not bridge.transport.pending.value
                guard();owned.Close(2);owned=None
                await asyncio.sleep(4)
        complete=True
    finally:
        if owned is not None and not bridge.busy and not bridge.transport.pending.value and win32process.GetWindowThreadProcessId(win32gui.GetForegroundWindow())[1]!=window['pid']:
            owned.Close(2);owned=None
        if previous is not None and owned is None and not bridge.busy:app.ActiveDocument=previous
        report={'runtime_version':state['version'],'executor_version':'0.3.25','complete':complete,'normal':normal,
                'scope':'real UXP with native readback acknowledgements before confirmation; independent COM after terminal; no synthesized input',
                'physical_input':False,'cases':cases,'foreground_preserved':win32gui.GetForegroundWindow()==initial,
                'owned_document_closed':owned is None,'unresolved':bool(bridge.busy or bridge.transport.pending.value),'placement':placement}
        save(folder/'report.json',report);print('REPORT '+str(folder/'report.json'),flush=True)
        await bridge.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--normal',action='store_true')
    asyncio.run(main(parser.parse_args().normal))
