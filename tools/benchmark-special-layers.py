"""Real Photoshop special-layer/count coverage for the scoped read experiment.

Diagnostic modes require the companion fixture; --production uses the installed
executor. Normally stop the live service, or explicitly use --live-idle.
Setup/readback/undo are outside timing; no retry of a submitted operation.
"""
import argparse, asyncio, hashlib, json, shutil, sys, time
from pathlib import Path
from urllib.request import urlopen
import win32com.client
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.uxp_bridge import UxpBridge
from benchmark_read_helpers import ACTIONS, MODES, summary, native, fixture, TREE, SEMANTIC

async def main(args):
    try:urlopen('http://127.0.0.1:15151/api/health',timeout=1)
    except OSError:pass
    else:
        if not args.live_idle:raise RuntimeError('Normally stop the idle live service first, or explicitly use --live-idle')
        live=json.load(urlopen('http://127.0.0.1:15151/api/status',timeout=5))
        assert not live['photoshop']['busy'] and not live['menu']['visible'] and not live['photoshop_start']['active']
        assert not live['photoshop'].get('uxp_recovery',{}).get('active')
        assert not (Path(live['data_dir'])/'uxp-pending.json').exists()
        assert not any(t['state'] in ('capturing','running','result-unknown') for t in live['tasks']['items'])
    folder=ROOT/'.runtime'/('special-read-benchmark-'+str(time.time_ns()));folder.mkdir()
    config=folder/'uxp-config.json';shutil.copy2(args.config,config)
    bridge=UxpBridge(folder/'tasks.json',config)
    app=win32com.client.GetActiveObject('Photoshop.Application');previous=app.ActiveDocument if app.Documents.Count else None
    scratch=None;fixture_id=None;report={'photoshop':str(app.Version),'plugin':None,'checks':[],'rounds':{},'complete':False,'production':args.production}
    def js(code):return app.DoJavaScript(code)
    def tree():return str(js(TREE))
    def semantic():return str(js(SEMANTIC))
    def save():args.output.write_text(json.dumps(report,indent=2),'utf-8')
    async def inspect(**payload):return await asyncio.to_thread(bridge.transport.call,'inspect',**payload)
    async def ready():
        # Large COM fixture/undo work can suppress UXP timers. This read-only
        # setup barrier is outside timing and publishes/replays no request.
        deadline=time.monotonic()+12
        while time.monotonic()<deadline:
            try:
                folder=bridge.transport.folder
                beat=json.loads((folder/'probe-last.json').read_text('utf-8-sig'))
                if 0<=time.time()*1000-beat['plugin_time_ms']<6000:return
            except (OSError,ValueError,RuntimeError):pass
            await asyncio.sleep(.05)
        raise RuntimeError('UXP heartbeat not fresh after scratch setup; no operation submitted')
    async def configure(mode):
        await ready()
        if args.production:return
        identity=int(js('app.activeDocument.id;'))
        value=await inspect(read_experiment={'mode':mode,'refresh':'poll','document_id':identity})
        assert value['read_experiment']['mode']==mode and value['read_experiment']['document_id']==identity
    def create(kind,count):
        nonlocal scratch,fixture_id
        guard='var creationFixtureDeadline=(new Date()).getTime()+'+str(args.max_setup_seconds*1000)+';function creationFixtureDuplicate(layer){if((new Date()).getTime()>creationFixtureDeadline)throw Error("Owned creation fixture setup budget exceeded");return layer.duplicate();}'
        code=guard+fixture(kind,count).replace('templates[i%templates.length].duplicate();','creationFixtureDuplicate(templates[i%templates.length]);').replace('anchor.duplicate();','creationFixtureDuplicate(anchor);')
        try:js(code)
        except Exception:
            if str(app.ActiveDocument.Name).startswith('Read strategy benchmark scratch'):app.ActiveDocument.Close(2)
            raise
        scratch=app.ActiveDocument
        fixture_id=int(js('app.activeDocument.id;'))
        return tree(),semantic(),int(js('app.activeDocument.historyStates.length-1;'))
    def close():
        nonlocal scratch
        app.ActiveDocument=scratch;scratch.Close(2);scratch=None
    def restore(index,before,original):
        js('app.activeDocument.activeHistoryState=app.activeDocument.historyStates['+str(index)+'];')
        assert tree()==before,'Original tree/order/name/parent changed'
        assert semantic()==original,'Original special-layer payload/mask changed'
        js('app.activeDocument.activeLayer=app.activeDocument.artLayers.getByName("Anchor");')
    async def sequence(mode,before,original,index):
        await configure(mode);target=await asyncio.to_thread(bridge._capture_target)
        assert target['document_id']==fixture_id,'Owned fixture is no longer active; no operation submitted'
        samples=[];started=time.perf_counter()
        for action in ACTIONS:
            frozen={key:target[key] for key in ('session','document_id','layer_ids')};frozen['active_layer_id']=frozen['layer_ids'][0]
            step=time.perf_counter();result=await bridge.execute(action,frozen_target=frozen);elapsed=(time.perf_counter()-step)*1000
            creation=json.loads(result['result']);target=bridge.layer_context
            assert creation['verified'] and creation['placement_moves']==0
            assert target['document_id']==frozen['document_id'] and target['layer_ids']==[creation['layer_id']] and target['quick_mask']==127
            assert not bridge.busy and not bridge.transport.pending.value
            samples.append({'action':action,'ms':round(elapsed,3),'timings_ms':creation.get('timings_ms',{}),'placeholder_used':creation['placeholder_used'],
                'tree_reader':creation.get('tree_reader','dom'),'tree_count':creation.get('tree_count')})
        total=(time.perf_counter()-started)*1000
        after=tree().splitlines();old=before.splitlines();ids={line.split('\t')[1] for line in old}
        assert [line for line in after if line.split('\t')[1] in ids]==old
        assert len(after)==len(old)+len(ACTIONS)
        assert semantic()==original,'Special-layer payload changed during creation'
        js('app.activeDocument.activeHistoryState=app.activeDocument.historyStates[app.activeDocument.historyStates.length-2];')
        assert len(tree().splitlines())==len(old)+len(ACTIONS)-1
        restore(index,before,original)
        return {'total_ms':round(total,3),'samples':samples,'original_preserved':True,'one_undo_last':True}
    try:
        report['plugin']=(await inspect())['probe_version']
        if not args.production:assert report['plugin']=='0.3.11','Diagnostic fixture not loaded'
        kinds=args.kinds.split(',')
        if args.phase in ('all','audit'):
            for kind in kinds:
                before,original,index=create(kind,4)
                raw=(await inspect(read_probe=True))['read_probe'];snapshots=raw['snapshots']
                assert all(v['value']==snapshots['dom']['value'] for v in snapshots.values()),{'kind':kind,'snapshots':snapshots}
                report['checks'].append({'kind':kind,'parity':True,'raw_kind':raw['result'][0].get('layerKind'),'vector_path_present':'vectorPath:' in original,'semantic_sha256':hashlib.sha256(original.encode()).hexdigest()})
                if kind=='shape':assert raw['result'][0]['layerKind']==4 and 'vectorPath:' in original,'Fixture must be a true vector shape'
                else:assert raw['result'][0]['layerKind']=={'solid':11,'gradient':9,'text':3,'smart':5,'curves':2,'levels':2,'masked':1}[kind],('Wrong fixture type',kind,raw['result'][0])
                # Every command is compared with PS native insertion/default
                # name, checked independently, and reversed by exactly one undo.
                for action in dict.fromkeys(ACTIONS):
                    js(native(action));expected=tree().splitlines();made=int(js('app.activeDocument.activeLayer.id;'))
                    expected_line=next(line for line in expected if int(line.split('\t')[1])==made)
                    parent,_,name=expected_line.split('\t',2)
                    siblings=[line for line in expected if line.split('\t')[0]==parent]
                    at=siblings.index(expected_line);next_name=siblings[at+1].split('\t')[2] if at+1<len(siblings) else None
                    restore(index,before,original)
                    for mode in MODES:
                        await configure(mode);target=await asyncio.to_thread(bridge._capture_target)
                        result=await bridge.execute(action,frozen_target=target);creation=json.loads(result['result']);after=tree().splitlines()
                        added=[line for line in after if line.split('\t')[1] not in {row.split('\t')[1] for row in before.splitlines()}]
                        assert len(added)==1 and creation['placement_moves']==0
                        p,_,n=added[0].split('\t',2);same=[line for line in after if line.split('\t')[0]==p];at=same.index(added[0])
                        nxt=same[at+1].split('\t')[2] if at+1<len(same) else None
                        assert (p,n,nxt)==(parent,name,next_name),(kind,action,mode,(p,n,nxt),(parent,name,next_name))
                        original_rows=[line for line in after if line not in added]
                        if action=='layer.group':
                            group_id=added[0].split('\t')[1]
                            original_rows=[parent+'\t'+line.split('\t',1)[1] if line.split('\t')[0]==group_id else line for line in original_rows]
                        assert original_rows==before.splitlines()
                        assert semantic()==original
                        js('app.activeDocument.activeHistoryState=app.activeDocument.historyStates[app.activeDocument.historyStates.length-2];')
                        assert tree()==before and semantic()==original
                        report['checks'].append({'kind':kind,'action':action,'mode':mode,'native_name_position':True,'one_undo':True,'original_preserved':True})
                # Fresh PS identity check must refuse stale selections, all modes.
                for mode in MODES:
                    await configure(mode);target=await asyncio.to_thread(bridge._capture_target)
                    js('app.activeDocument.activeLayer=app.activeDocument.artLayers.getByName("Upper");')
                    stale_tree=tree()
                    try:await bridge.execute('layer.new',frozen_target=target)
                    except RuntimeError:pass
                    else:raise AssertionError('Stale target accepted')
                    assert tree()==stale_tree and not bridge.transport.pending.value
                    js('app.activeDocument.activeLayer=app.activeDocument.artLayers.getByName("Anchor");')
                    report['checks'].append({'kind':kind,'mode':mode,'stale_refused':True})
                print(json.dumps({'audit':kind,'cases':len(report['checks'])}),flush=True);close();save()
        if args.phase in ('all','timing'):
            cases=([] if args.counts_only else [(kind,4) for kind in kinds])+([] if args.small_only else [(kind,count) for kind,count in [
                ('shape',10),('shape',100),('shape',300),('mixed',10),('mixed',100),('mixed',300),('text',100),('smart',100)]]
            )
            cases=[row for row in cases if row[0]+str(row[1]) not in args.exclude_cases.split(',')]
            if args.cases:cases=[row for row in cases if row[0]+str(row[1]) in args.cases.split(',')]
            for kind,count in cases:
                before,original,index=create(kind,count);key=kind+str(count);modes=['dom'] if args.production else MODES;rows={mode:[] for mode in modes};report['rounds'][key]=rows
                print(json.dumps({'fixture':key,'actual_layers':len(before.splitlines())}),flush=True)
                for cycle in range(args.samples+1):
                    order=modes[cycle%len(modes):]+modes[:cycle%len(modes)]
                    for mode in order:
                        value=await sequence(mode,before,original,index)
                        if cycle:rows[mode].append(value)
                        print(json.dumps({'case':key,'cycle':cycle,'mode':mode,'ms':value['total_ms'],'warmup':cycle==0}),flush=True)
                    save()
                close()
            report['totals']={case:{mode:summary([r['total_ms'] for r in rows]) for mode,rows in data.items()} for case,data in report['rounds'].items()}
        report['complete']=True;save()
        print(json.dumps({'complete':True,'checks':len(report['checks']),'totals':report.get('totals',{})}),flush=True)
    finally:
        if not bridge.transport.pending.value:
            try:
                if not args.production:await inspect(read_experiment=None)
            except Exception:pass
            if scratch:close()
            if previous is not None:app.ActiveDocument=previous
        await bridge.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--samples',type=int,default=3)
    p.add_argument('--kinds',default='shape,solid,gradient,text,smart,curves,levels,masked')
    p.add_argument('--small-only',action='store_true');p.add_argument('--production',action='store_true')
    p.add_argument('--counts-only',action='store_true')
    p.add_argument('--live-idle',action='store_true',help='Explicitly permit an idle production service; this test is the only PS command producer during the run')
    p.add_argument('--max-setup-seconds',type=int,default=300,choices=range(10,301),metavar='10..300',help='Cooperative fixture budget outside measured operations; never forcibly stops a native call')
    p.add_argument('--exclude-cases',default='')
    p.add_argument('--cases',default='')
    p.add_argument('--phase',choices=['all','audit','timing'],default='all');p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.production and args.phase!='timing':p.error('--production supports timing only; no experimental diagnostics')
    asyncio.run(main(args))
