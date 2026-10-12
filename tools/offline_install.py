"""Per-user, network-free deployment. All writes are confined to our own files."""
import hashlib
import json
from pathlib import Path
import secrets
import shutil
import time
from backend.version import APP_VERSION
from backend.photoshop_version import MIN_PHOTOSHOP_TEXT
from backend.uxp_management import validate as validate_uxp

PLUGIN_ID = 'com.15100px.menu.offline-probe'
PLUGIN_FILES = ('manifest.json', 'main.js', 'labels.js', 'probe-config.js')

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

class OfflineInstall:
    def __init__(self, local, roaming, shortcuts=None):
        self.root = Path(local).resolve() / 'PhotoshopMenu'
        if (self.root/'uxp-config.json').is_file():
            self.root=(self.root/'uxp-config.json').resolve().parent
        self.plugin = Path(roaming).resolve() / 'Adobe/UXP/Plugins/External' / (PLUGIN_ID+'_PS')
        self.receipt = self.root / 'offline-install.json'
        self.shortcuts = list(shortcuts or [])
        self.files = [self.root/'app/PhotoshopMenu.exe', self.root/'app/OfflineSetup.exe',
                      self.root/'uxp-config.json', self.receipt,
                      *(self.plugin/name for name in PLUGIN_FILES), *self.shortcuts]

    def snapshot(self):
        backup = self.root / 'install-backups' / (str(time.time_ns())+'-'+secrets.token_hex(3))
        backup.mkdir(parents=True)
        present=[]
        for i, path in enumerate(self.files):
            if path.is_file():
                shutil.copy2(path, backup/str(i)); present.append(i)
        (backup/'snapshot.json').write_text(json.dumps({'files':[str(p) for p in self.files], 'present':present}), 'utf-8')
        return backup

    def restore(self, backup):
        backup = Path(backup).resolve()
        if backup.parent != (self.root/'install-backups').resolve():
            raise RuntimeError('Backup path is outside this installation')
        data=json.loads((backup/'snapshot.json').read_text('utf-8'))
        if data['files'] != [str(p) for p in self.files]:
            raise RuntimeError('Backup belongs to a different installation')
        for i,path in enumerate(self.files):
            if i in data['present']:
                path.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(backup/str(i),path)
            elif path.is_file():path.unlink()

    def plugin_is_current(self,payload,allow_min_version_change=False):
        try:
            config=json.loads((self.root/'uxp-config.json').read_text('utf-8-sig'))
            text=(self.plugin/'probe-config.js').read_text('utf-8-sig').strip()
            token=json.loads(text.removeprefix('module.exports').lstrip().removeprefix('=').strip().removesuffix(';'))
            wanted=json.loads((Path(payload)/'plugin/manifest.json').read_text('utf-8-sig'))
            current=json.loads((self.plugin/'manifest.json').read_text('utf-8-sig'))
            if allow_min_version_change:current['host']['minVersion']=wanted['host']['minVersion']
            return token==config['token'] and current==wanted and all(
                digest(self.plugin/name)==digest(Path(payload)/'plugin'/name) for name in ('main.js','labels.js'))
        except (OSError,ValueError,KeyError):return False

    def install(self, payload, setup, make_shortcuts=lambda:None, preserve_plugin=False):
        payload=Path(payload)
        hashes=json.loads((payload/'SHA256.json').read_text('utf-8'))
        expected={'PhotoshopMenu.exe', 'plugin/manifest.json', 'plugin/main.js', 'plugin/labels.js'}
        if set(hashes)!=expected:raise RuntimeError('Unexpected package contents')
        for relative,wanted in hashes.items():
            if digest(payload/relative)!=wanted:raise RuntimeError('Package checksum mismatch: '+relative)
        manifest=validate_uxp(payload/'plugin')
        if manifest['host']['minVersion']!=MIN_PHOTOSHOP_TEXT:raise RuntimeError('Incompatible Photoshop version floor')
        if (self.plugin/'manifest.json').exists():
            installed=json.loads((self.plugin/'manifest.json').read_text('utf-8-sig'))
            if installed.get('id')!=PLUGIN_ID:raise RuntimeError('Plugin directory belongs to a different plugin; preserved')
        if preserve_plugin and not self.plugin_is_current(payload,True):raise RuntimeError('Running plugin differs from package; close Photoshop first')
        config=self.root/'uxp-config.json'
        token=secrets.token_hex(32)
        if config.exists():
            existing=json.loads(config.read_text('utf-8-sig')).get('token')
            if not isinstance(existing,str) or len(existing)<32:raise RuntimeError('Invalid existing credentials; preserved')
            token=existing
        backup=self.snapshot()
        try:
            (self.root/'app').mkdir(parents=True,exist_ok=True)
            self.plugin.mkdir(parents=True,exist_ok=True)
            shutil.copy2(payload/'PhotoshopMenu.exe',self.files[0])
            shutil.copy2(setup,self.files[1])
            if not preserve_plugin:
                for name in PLUGIN_FILES[:-1]:shutil.copy2(payload/'plugin'/name,self.plugin/name)
                (self.plugin/'probe-config.js').write_text('module.exports = '+json.dumps(token)+';\n','utf-8')
                config.write_text(json.dumps({'token':token,'protocol_version':1}), 'utf-8')
            elif digest(self.plugin/'manifest.json')!=digest(payload/'plugin/manifest.json'):
                # Only the compatible minimum-host declaration can differ here.
                temporary=self.plugin/'manifest.install.tmp'
                try:
                    shutil.copy2(payload/'plugin/manifest.json',temporary)
                    temporary.replace(self.plugin/'manifest.json')
                finally:
                    if temporary.exists():temporary.unlink()
            make_shortcuts()
            owned={str(p):digest(p) for p in self.files if p!=self.receipt and p.exists()}
            self.receipt.write_text(json.dumps({'version':APP_VERSION,'plugin_version':manifest['version'], 'minimum_photoshop':MIN_PHOTOSHOP_TEXT, 'backup':str(backup), 'owned':owned},indent=2),'utf-8')
        except Exception:
            self.restore(backup);raise
        return {'executable':str(self.files[0]), 'backup':str(backup), 'version':APP_VERSION}

    def uninstall(self):
        receipt=json.loads(self.receipt.read_text('utf-8'))
        allowed={str(p):p for p in self.files if p!=self.receipt}
        for path,wanted in receipt['owned'].items():
            if path not in allowed:raise RuntimeError('Unexpected owned path')
            file=allowed[path]
            if file.exists() and digest(file)!=wanted:raise RuntimeError('File modified; preserved: '+path)
        backup=self.snapshot()
        try:
            for path in receipt['owned']:
                file=allowed[path]
                # Retain credentials, settings, task history and all backup folders.
                if file!=self.root/'uxp-config.json' and file.exists():file.unlink()
            self.receipt.unlink()
        except Exception:
            self.restore(backup);raise
        return {'backup':str(backup), 'user_data_preserved':True}

    def rollback(self):
        receipt=json.loads(self.receipt.read_text('utf-8'))
        self.restore(receipt['backup'])
        return {'restored':True}
