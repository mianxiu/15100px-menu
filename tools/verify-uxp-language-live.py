"""Read the actual installed backend and fresh Photoshop UXP metadata."""
import argparse, hashlib, json, sys, time
from pathlib import Path
from urllib.request import urlopen
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.language import plugin_name, COMMAND_NAMES
from backend.uxp_bridge import UxpTransport
from backend.version import APP_VERSION

parser=argparse.ArgumentParser()
parser.add_argument('--language',choices=('zh-CN','en'),required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
deadline=time.monotonic()+95
while time.monotonic()<deadline:
    status=json.load(urlopen('http://127.0.0.1:15151/api/status',timeout=5))
    if status['photoshop_start']['phase']=='ready' and status['photoshop']['uxp_ready']:
        try:
            folder=UxpTransport(Path(status['data_dir'])/'uxp-config.json').folder
            heartbeat=json.loads((folder/'probe-last.json').read_text('utf-8-sig'))
            if int(heartbeat['session'].split('-')[0])>=status['photoshop_start']['started_at_ms']:break
        except (OSError,ValueError,RuntimeError):pass
    time.sleep(.5)
else:raise RuntimeError('No fresh UXP session after launch')
assert status['version']==APP_VERSION and status['language']==args.language
assert status['uxp']['installation']=='installed' and not status['uxp']['language_pending']
assert status['uxp']['name']==heartbeat['plugin_name']==plugin_name(args.language,heartbeat['probe_version'])
assert heartbeat['command_label']==COMMAND_NAMES[args.language]
assert heartbeat['probe_version']==status['uxp']['version']
manifest=json.loads((Path(status['uxp']['plugin_dir'])/'manifest.json').read_text('utf-8'))
assert manifest['id']=='com.15100px.menu.offline-probe'
assert manifest['name']==plugin_name(args.language,heartbeat['probe_version'])
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(Path(status['service']['executable']))==sha(ROOT/'dist/PhotoshopMenu.exe')
report={'version':status['version'],'language':status['language'],'uxp':status['uxp'],
        'heartbeat':heartbeat,'service':status['service'],'startup':status['photoshop_start'],
        'installed_equals_dist':True,'scope':'Real frozen backend and fresh UXP runtime manifest metadata. Native PS menu text not captured; no physical keyboard gesture acceptance.'}
args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps({'language':args.language,'plugin_name':heartbeat['plugin_name'],
                  'command_label':heartbeat['command_label'],'fresh_uxp_session':True,'version':status['version']},ensure_ascii=False))
