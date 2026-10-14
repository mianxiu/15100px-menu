"""Compare complete protected consecutive creation, not isolated getter speed.

Only fixed metadata policies on disposable document IDs; no arbitrary plugin
scripts, writes on user documents, queueing, or unknown-result replays.
"""
import argparse,asyncio,json,math,random,shutil,statistics,sys,time
from pathlib import Path
from urllib.request import urlopen
import win32com.client
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.uxp_bridge import UxpBridge
from benchmark_read_helpers import ACTIONS, MODES, summary
COUNT='(function(){function n(ls){var v=0;for(var i=0;i<ls.length;i++){v++;if(ls[i].typename==="LayerSet")v+=n(ls[i].layers);}return v;}return n(app.activeDocument.layers);})();'

async def main(args):
    try:urlopen('http://127.0.0.1:15151/api/health',timeout=1)
    except OSError:pass
    else:raise RuntimeError('Normally stop the idle live service first; no competing hotkeys/status worker during timings')
    folder=ROOT/'.runtime'/('read-strategy-benchmark-'+str(time.time_ns()));folder.mkdir()
    config=folder/'uxp-config.json';shutil.copy2(args.config,config)
    bridge=UxpBridge(folder/'tasks.json',config)
    app=win32com.client.GetActiveObject('Photoshop.Application');previous=app.ActiveDocument if app.Documents.Count else None
    results={};checks=[];scratch=None
    def js(code):return app.DoJavaScript(code)
    async def inspect(**payload):return await asyncio.to_thread(bridge.transport.call,'inspect',**payload)
    async def configure(mode,refresh,format=None):
        value={'mode':mode,'refresh':refresh,'document_id':int(js('app.activeDocument.id;'))}
        if format:value['notification_format']=format
        response=await inspect(read_experiment=value);assert response['read_experiment']['mode']==mode
    def create(scenario):
        nonlocal scratch
        js('app.documents.add(UnitValue(181,"px"),UnitValue(181,"px"),72,"Read strategy benchmark scratch '+scenario+'",NewDocumentMode.RGB,DocumentFill.TRANSPARENT);'+
           'var d=app.activeDocument;var lower=d.artLayers.add();lower.name="Lower";var anchor=d.artLayers.add();anchor.name="Anchor";var upper=d.artLayers.add();upper.name="Upper";d.activeLayer=anchor;'+
           ('' if scenario=='empty' else 'd.selection.selectAll();d.selection.fill(app.foregroundColor);d.selection.deselect();')+
           ('var p=null;for(var i=0;i<4;i++){p=p?p.layerSets.add():d.layerSets.add();}anchor.move(p,ElementPlacement.INSIDE);d.activeLayer=anchor;for(var i=0;i<80;i++)d.artLayers.add();d.activeLayer=anchor;' if scenario=='nested80' else ''))
        scratch=app.ActiveDocument
    def close():
        nonlocal scratch
        app.ActiveDocument=scratch;scratch.Close(2);scratch=None
    async def sequence(mode,refresh,scenario,record=True):
        create(scenario);await configure(mode,refresh)
        before=int(js(COUNT));target=await asyncio.to_thread(bridge._capture_target);samples=[]
        started=time.perf_counter()
        for action in ACTIONS:
            frozen={key:target[key] for key in ('session','document_id','layer_ids')};frozen['active_layer_id']=frozen['layer_ids'][0]
            step=time.perf_counter();result=await bridge.execute(action,frozen_target=frozen);elapsed=(time.perf_counter()-step)*1000
            created=json.loads(result['result']);target=bridge.layer_context
            assert created['verified'] and created['placement_moves']==0
            assert target['document_id']==frozen['document_id'] and target['layer_ids']==[created['layer_id']] and target['quick_mask']==127
            assert not bridge.busy and not bridge.transport.pending.value
            samples.append({'action':action,'elapsed_ms':round(elapsed,3),'timings_ms':created.get('timings_ms',{}),
                            'parent_id':created['parent_id'],'placeholder_used':created['placeholder_used']})
        total=(time.perf_counter()-started)*1000
        assert int(js(COUNT))==before+len(ACTIONS)
        assert int(js('app.activeDocument.activeLayer.id;'))==target['layer_ids'][0]
        # Audit outside timing: final native blank has exactly one undo step.
        js('app.activeDocument.activeHistoryState=app.activeDocument.historyStates[app.activeDocument.historyStates.length-2];')
        assert int(js(COUNT))==before+len(ACTIONS)-1
        close()
        return {'total_ms':round(total,3),'samples':samples,'count_verified':True,'single_undo_last':True}
    async def probe_case(name,setup):
        if setup:js(setup)
        response=await inspect(read_probe=True)
        snapshots=response['read_probe']['snapshots'];base=snapshots['dom']['value']
        assert all(value['value']==base for value in snapshots.values()),{'case':name,'snapshots':snapshots}
        checks.append({'case':name,'equivalent':True,'read_ms':{mode:data['ms'] for mode,data in snapshots.items()}})
    try:
        create('filled')
        await probe_case('pixel','')
        await probe_case('position lock','app.activeDocument.activeLayer.positionLocked=true;')
        await probe_case('position unlock','app.activeDocument.activeLayer.positionLocked=false;')
        await probe_case('text','var text=app.activeDocument.artLayers.add();text.kind=LayerKind.TEXT;text.textItem.contents="test";')
        await probe_case('smart','executeAction(stringIDToTypeID("newPlacedLayer"),undefined,DialogModes.NO);')
        await probe_case('nested parent lock','var g=app.activeDocument.layerSets.add();var l=g.artLayers.add();app.activeDocument.activeLayer=l;g.allLocked=true;')
        await probe_case('nested parent unlock','app.activeDocument.activeLayer.parent.allLocked=false;')
        close()
        for scenario in ('filled','empty','nested80'):
            by_mode={mode:[] for mode in MODES};results[scenario]=by_mode
            for cycle in range(args.samples+1):
                order=MODES[cycle%3:]+MODES[:cycle%3]
                for mode in order:
                    value=await sequence(mode,'poll',scenario)
                    if cycle:by_mode[mode].append(value)
                    print(json.dumps({'scenario':scenario,'cycle':cycle,'mode':mode,'total_ms':value['total_ms'],'warmup':cycle==0}),flush=True)
                args.output.write_text(json.dumps({'partial':True,'checks':checks,'results':results},indent=2),'utf-8')
        aggregate={mode:statistics.mean(statistics.median([r['total_ms'] for r in results[scenario][mode]]) for scenario in results) for mode in MODES}
        best=min(aggregate,key=aggregate.get)
        # Avoid selecting a method on noise: require >=5% end-to-end improvement
        # in every scenario and no worse measured tail. Keep DOM otherwise.
        if best!='dom':
            for scenario in results:
                dom=summary([r['total_ms'] for r in results[scenario]['dom']]);candidate=summary([r['total_ms'] for r in results[scenario][best]])
                if candidate['median_ms']>dom['median_ms']*.95 or candidate['p95_ms']>dom['p95_ms']*1.05:best='dom';break
        events={'poll':[],'events':[]}
        for cycle in range(args.samples+1):
            for refresh in (['poll','events'] if cycle%2==0 else ['events','poll']):
                value=await sequence(best,refresh,'nested80')
                if cycle:events[refresh].append(value)
                print(json.dumps({'event_test':True,'cycle':cycle,'mode':best,'refresh':refresh,'total_ms':value['total_ms'],'warmup':cycle==0}),flush=True)
        create('filled')
        refresh_tests=[];idle=[];format_checks=[]
        for format in ('strings','objects'):
            await configure(best,'events',format)
            stats=(await inspect(refresh_probe=True))['refresh_probe']
            js('app.activeDocument.activeLayer=app.activeDocument.artLayers.getByName("Upper");app.activeDocument.activeLayer=app.activeDocument.artLayers.getByName("Anchor");')
            await asyncio.sleep(.25)
            latest=(await inspect(refresh_probe=True))['refresh_probe']
            format_checks.append({'format':format,'ready':latest['notification_ready'],'events':latest['notifications']-stats['notifications']})
        selected_format=max(format_checks,key=lambda row:row['events'])['format']
        for refresh in ('poll','events'):
            await configure(best,refresh,selected_format);await asyncio.sleep(.2)
            stats=(await inspect(refresh_probe=True))['refresh_probe'];await asyncio.sleep(2.5)
            final=(await inspect(refresh_probe=True))['refresh_probe']
            idle.append({'refresh':refresh,'seconds':2.5,'reads':final['reads']-stats['reads'],'notifications':final['notifications']-stats['notifications'],'ready':final['notification_ready']})
            for case,script,key,wanted in (
                ('selection','app.activeDocument.activeLayer=app.activeDocument.artLayers.getByName("Upper");','layer_ids',None),
                ('selection middle','app.activeDocument.activeLayer=app.activeDocument.artLayers.getByName("Anchor");','layer_ids',None),
                ('lock','app.activeDocument.activeLayer.positionLocked=true;','locked',True),
                ('unlock','app.activeDocument.activeLayer.positionLocked=false;','locked',False),
                ('new','app.activeDocument.artLayers.add();','layer_ids',None),
                ('delete','app.activeDocument.activeLayer.remove();','layer_ids',None),
                ('parent lock','var pg=app.activeDocument.layerSets.add();var pl=pg.artLayers.add();app.activeDocument.activeLayer=pl;pg.allLocked=true;','quick_mask',0),
                ('parent unlock','app.activeDocument.activeLayer.parent.allLocked=false;','quick_mask',127)):
                epoch=time.time()*1000;started=time.perf_counter();identity=int(js(script+'app.activeDocument.activeLayer.id;'))
                document_id=int(js('app.activeDocument.id;'))
                path=bridge.transport.folder/'layer-context.json';deadline=time.perf_counter()+2.5
                value={}
                while time.perf_counter()<deadline:
                    try:value=json.loads(path.read_text('utf-8-sig'))
                    except (OSError,json.JSONDecodeError):await asyncio.sleep(.005);continue
                    if value.get('document_id')==document_id and value.get('plugin_time_ms',0)>=epoch and value.get('layer_ids')==[identity] and (key=='layer_ids' or value.get(key)==wanted):break
                    await asyncio.sleep(.005)
                else:raise AssertionError({'case':case,'refresh':refresh,'last':value})
                latency=(time.perf_counter()-started)*1000
                refresh_tests.append({'refresh':refresh,'case':case,'ms':round(latency,2)})
        close()
        for mode in MODES:
            create('filled');await configure(mode,'poll');target=await asyncio.to_thread(bridge._capture_target)
            before=int(js(COUNT));js('app.activeDocument.activeLayer=app.activeDocument.artLayers.getByName("Upper");')
            try:await bridge.execute('layer.new',frozen_target=target)
            except RuntimeError:pass
            else:raise AssertionError('Stale target accepted by '+mode)
            assert int(js(COUNT))==before and not bridge.transport.pending.value
            checks.append({'case':'stale target '+mode,'rejected_before_write':True});close()
        totals={scenario:{mode:summary([row['total_ms'] for row in rows]) for mode,rows in data.items()} for scenario,data in results.items()}
        event_totals={mode:summary([row['total_ms'] for row in rows]) for mode,rows in events.items()}
        event_safe=all(row['ms']<=200 for row in refresh_tests if row['refresh']=='events')
        event_faster=event_totals['events']['median_ms']<=event_totals['poll']['median_ms']*.95 and event_totals['events']['p95_ms']<=event_totals['poll']['p95_ms']*1.05
        report={'photoshop':str(app.Version),'plugin':'0.3.11','checks':checks,'totals':totals,'rounds':results,
                'chosen_read_mode':best,'event_totals':event_totals,'event_rounds':events,'refresh_tests':refresh_tests,
                'idle':idle,'notification_formats':format_checks,'chosen_refresh':'events' if event_safe and event_faster else 'poll',
                'scope':'Complete production UXP bridge execute -> committed history -> prepared fresh selection -> persisted final receipt -> next target ready. Ten immediate creations, balanced mode order, one warmup per mode, no intermediate COM/capture/poll/wait/retry. Setup/final count/undo outside timings; not physical gesture-to-screen latency. Only type/background/lock metadata varies; document mode/depth, topology and live target validation remain common.'}
        args.output.write_text(json.dumps(report,indent=2),'utf-8')
        print(json.dumps({'totals':totals,'chosen_read_mode':best,'event_totals':event_totals,'chosen_refresh':report['chosen_refresh'],'notification_formats':format_checks,'idle':idle}),flush=True)
    finally:
        if not bridge.transport.pending.value:
            try:await inspect(read_experiment=None)
            except Exception:pass
            if scratch:close()
            if previous is not None:app.ActiveDocument=previous
        await bridge.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=6);parser.add_argument('--output',type=Path,required=True)
    asyncio.run(main(parser.parse_args()))
