"""Anonymous real GitHub download into an isolated profile; never installs."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.application_updates import ApplicationUpdates

parser=argparse.ArgumentParser()
parser.add_argument('--current',default='0.4.117')
parser.add_argument('--output',type=Path,default=ROOT/'.runtime/github-update-source.json')
args=parser.parse_args()
runtime=ROOT/'.runtime'/('github-update-check-'+str(time.time_ns()));runtime.mkdir()
updater=ApplicationUpdates(runtime,args.current)
updater.check();assert updater.snapshot()['available'],'Test version must be lower than the published release'
updater.download();result=updater.snapshot()
assert result['phase']=='ready' and result['staged']['version']==result['release']['version']
report={key:result[key] for key in ('current','release','staged','phase','message','progress')}
report['anonymous_download']=True;report['installed']=False
args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps({'version':result['release']['version'],'phase':result['phase'],'download_verified':True},ensure_ascii=False))
