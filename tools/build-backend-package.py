"""Distribute one main EXE with UXP resources and management in its backend."""
import hashlib
from pathlib import Path
import sys
import zipfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.version import APP_VERSION
from backend.uxp_management import UxpManager
from PyInstaller.archive.readers import CArchiveReader
import win32api

exe=ROOT/'dist/PhotoshopMenu.exe'
parts=[int(p) for p in APP_VERSION.split('.')]
info=win32api.GetFileVersionInfo(str(exe),'\\')
assert (info['FileVersionMS'],info['FileVersionLS'])==((parts[0]<<16)|parts[1],parts[2]<<16)
archive=CArchiveReader(str(exe));names={n.replace(chr(92),'/'):n for n in archive.toc}
resources={n for n in names if n.startswith('uxp/offline-probe/')}
assert resources=={'uxp/offline-probe/'+n for n in ('manifest.json','main.js','labels.js')},resources
for n in resources:assert archive.extract(names[n])==(ROOT/n).read_bytes()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
exe.with_suffix('.exe.sha256').write_text(sha(exe)+'  PhotoshopMenu.exe\n','ascii')
plugin=ROOT/('dist/PhotoshopMenu-UXP-'+APP_VERSION+'.zip')
plugin.write_bytes(UxpManager(ROOT/'.runtime',ROOT/'uxp/offline-probe',ROOT/'.runtime/unused-package-root').export_builtin())
output=ROOT/('dist/PhotoshopMenu-Backend-'+APP_VERSION+'.zip')
with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as bundle:
    for p in (exe,exe.with_suffix('.exe.sha256'),ROOT/'OFFLINE-INSTALL.md',ROOT/'PERFORMANCE.md',ROOT/'RELEASES.md',ROOT/'LICENSE',ROOT/'THIRD_PARTY_NOTICES.md',plugin):bundle.write(p,p.name)
    bundle.write(ROOT/'docs/CONTEXT-COVERAGE.md','docs/CONTEXT-COVERAGE.md')
    bundle.write(ROOT/'docs/UPDATES.md','docs/UPDATES.md')
    bundle.write(ROOT/'docs/READ-STRATEGIES.md','docs/READ-STRATEGIES.md')
    bundle.write(ROOT/'docs/UI-GUIDE.md','docs/UI-GUIDE.md')
    bundle.write(ROOT/'tools/inspect-panels.ps1','tools/inspect-panels.ps1')
    for notice in sorted((ROOT/'licenses').glob('*.txt')):bundle.write(notice,'licenses/'+notice.name)
    for source,target in ((ROOT/'native/fonts/OFL-1.1.txt','licenses/fonts-OFL-1.1.txt'),(ROOT/'native/fonts/COPYRIGHT.txt','licenses/fonts-COPYRIGHT.txt'),(ROOT/'native/vendor/imgui/LICENSE.txt','licenses/imgui.txt'),(ROOT/'native/vendor/json/LICENSE.MIT','licenses/json.txt'),(ROOT/'native/vendor/manifest.json','licenses/native-manifest.json')):bundle.write(source,target)
output.with_suffix('.zip.sha256').write_text(sha(output)+'  '+output.name+'\n','ascii')
print('Built unified backend:',output)
