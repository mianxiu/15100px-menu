"""Bounded native GPU/WARP comparison; never sends Photoshop actions or input."""
import argparse,json,subprocess,time
from pathlib import Path

def main():
    root=Path(__file__).resolve().parents[1]
    parser=argparse.ArgumentParser();parser.add_argument('--rounds',type=int,default=2);parser.add_argument('--output',type=Path,default=root/'.runtime/render-modes130.json');args=parser.parse_args()
    if not 1<=args.rounds<=5:raise ValueError('Use one to five bounded rounds')
    reports=[]
    for round_index in range(args.rounds):
        for mode in (('gpu','cpu') if round_index%2==0 else ('cpu','gpu')):
            path=args.output.with_name(args.output.stem+f'-{round_index+1}-{mode}.json')
            started=time.perf_counter()
            result=subprocess.run([str(root/'native/MenuHost.exe'),'--render-mode',mode,'--benchmark-shape-output',str(path),'--benchmark-render-completion'],
                capture_output=True,text=True,encoding='utf-8',timeout=90,creationflags=0x08000000)
            assert result.returncode==0 and 'self-test passed' in result.stdout,(mode,result.returncode,result.stderr)
            report=json.loads(path.read_text('utf-8'));assert report['graphics']['requested']==mode and report['graphics']['active']==mode,report['graphics']
            assert len(report['cases'])==16 and all(c['vertices']>0 for c in report['cases'])
            reports.append({'round':round_index+1,'mode':mode,'wall_seconds':round(time.perf_counter()-started,3),'report':report,'native_selftest_passed':True,'stderr':result.stderr})
            print(json.dumps({'round':round_index+1,'mode':mode,'adapter':report['graphics']['adapter'],'cases':len(report['cases']),'wall_seconds':reports[-1]['wall_seconds']}),flush=True)
    aggregate=[]
    for kind in ('plain','solid','gradient','pattern'):
        for mode in ('gpu','cpu'):
            cases=[c for r in reports if r['mode']==mode for c in r['report']['cases'] if c['kind']==kind]
            aggregate.append({'kind':kind,'mode':mode,'submission_median_mean_ms':sum(c['median_ms'] for c in cases)/len(cases),
                'completion_median_mean_ms':sum(c['completion_median_ms'] for c in cases)/len(cases),'worst_case_completion_p95_ms':max(c['completion_p95_ms'] for c in cases)})
    output={'scope':'Same 920x560 logical native UI, large cached font, four themes; 20 warm + 200 measured frames per case. DX11 EVENT waits include queue/driver/query synchronization, exclude Present/vsync and physical key latency. No Photoshop commands. Short bounded stability test, not long-run assurance.',
        'rendered_benchmark_frames':args.rounds*2*16*220,'native_selftests':len(reports),'summary':aggregate,'runs':reports}
    args.output.write_text(json.dumps(output,indent=2),'utf-8')
    print(json.dumps(output['summary'],indent=2),flush=True)
if __name__=='__main__':main()
