"""Build a distributable self-contained EXE without copying local credentials."""
import argparse,hashlib,json,shutil,subprocess,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.version import APP_VERSION
parser=argparse.ArgumentParser()
parser.add_argument('--exe',type=Path,default=ROOT/'dist/PhotoshopMenu.exe')
args=parser.parse_args()
import win32api
info=win32api.GetFileVersionInfo(str(args.exe),'\\')
parts=[int(p) for p in APP_VERSION.split('.')]
if (info['FileVersionMS'],info['FileVersionLS'])!=((parts[0]<<16)|parts[1],(parts[2]<<16)|0):
    raise RuntimeError('Offline package requires PhotoshopMenu '+APP_VERSION)
stage=ROOT/'.runtime/offline-payload/payload'
(stage/'plugin').mkdir(parents=True,exist_ok=True)
shutil.copy2(args.exe,stage/'PhotoshopMenu.exe')
for name in ('manifest.json','main.js','labels.js'):
    shutil.copy2(ROOT/'uxp/offline-probe'/name,stage/'plugin'/name)
allowed=['PhotoshopMenu.exe','plugin/manifest.json','plugin/main.js','plugin/labels.js']
extras=[p for p in stage.rglob('*') if p.is_file() and p.relative_to(stage).as_posix() not in allowed+['SHA256.json']]
if extras:raise RuntimeError('Unexpected payload files; clean the staging folder: '+str(extras))
(stage/'SHA256.json').write_text(json.dumps({p:hashlib.sha256((stage/p).read_bytes()).hexdigest() for p in allowed},indent=2),'utf-8')
version=ROOT/'.runtime/offline-setup-version.txt'
version.write_text((ROOT/'tools/windows-version.txt').read_text('utf-8-sig').replace(
    'Photoshop Menu desktop application','Photoshop Menu offline installer').replace(
    "'OriginalFilename', 'PhotoshopMenu.exe'","'OriginalFilename', 'OfflineSetup.exe'"),'utf-8')
subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--onefile','--windowed',
    '--name','PhotoshopMenu-OfflineSetup-'+APP_VERSION,'--distpath',str(ROOT/'dist'),
    '--workpath',str(ROOT/'build/offline-setup'),'--specpath',str(ROOT/'.runtime'),
    '--paths',str(ROOT/'tools'),'--paths',str(ROOT),'--hidden-import','win32timezone',
    '--icon',str(ROOT/'frontend/public/icon.ico'),'--version-file',str(version),'--add-data',str(stage)+';payload',
    str(ROOT/'tools/offline_setup.py')],check=True)
output=ROOT/('dist/PhotoshopMenu-OfflineSetup-'+APP_VERSION+'.exe')
output.with_suffix('.exe.sha256').write_text(hashlib.sha256(output.read_bytes()).hexdigest()+'  '+output.name+'\n','ascii')
archive=ROOT/('dist/PhotoshopMenu-Offline-'+APP_VERSION+'.zip')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as bundle:
    for file in (output,output.with_suffix('.exe.sha256'),ROOT/'OFFLINE-INSTALL.md',ROOT/'PERFORMANCE.md'):
        bundle.write(file,file.name)
    report=ROOT/'.runtime/execution-performance-0.4.70.json'
    if report.exists():bundle.write(report,'execution-performance.json')
    for source,target in ((ROOT/'native/vendor/imgui/LICENSE.txt','licenses/imgui.txt'),
                          (ROOT/'native/vendor/json/LICENSE.MIT','licenses/json.txt'),
                          (ROOT/'native/vendor/manifest.json','licenses/native-manifest.json')):
        bundle.write(source,target)
archive.with_suffix('.zip.sha256').write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n','ascii')
print('Built offline setup:',output)
