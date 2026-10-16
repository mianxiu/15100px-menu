"""Create a small public update fallback from a verified published Release."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.application_updates import select_release,ApplicationUpdates
from backend.version import APP_VERSION

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--release-json',type=Path,required=True)
parser.add_argument('--output',type=Path,default=ROOT/'dist/PhotoshopMenu-update.json')
args=parser.parse_args()
raw=json.loads(args.release_json.read_text('utf-8'))
value=select_release(raw,APP_VERSION)
if value['version']!=APP_VERSION:raise ValueError('Manifest must match the current build')
# Export only public release metadata, never tokens or local configuration.
document=ApplicationUpdates._release_document(value)
select_release(document,APP_VERSION)
args.output.write_text(json.dumps(document,ensure_ascii=False,indent=2)+'\n','utf-8')
print('Built public update manifest:',args.output)
