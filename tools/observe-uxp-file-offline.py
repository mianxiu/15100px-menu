"""Five-minute offline deployment/runtime experiment; never changes networking."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

root = Path(__file__).resolve().parents[1]
output = root / '.runtime/uxp-file-offline-observation.jsonl'
stop = root / '.runtime/stop-uxp-file-offline-observer'
source = root / 'uxp/offline-probe'
destination = Path(os.environ['APPDATA']) / 'Adobe/UXP/Plugins/External/com.15100px.menu.offline-probe_PS'
deployed = False
deadline = time.monotonic() + 300
while time.monotonic() < deadline and not stop.exists():
    sample = {'time_ms': int(time.time() * 1000), 'observation_version': 2}
    try:
        state = subprocess.run(['powershell.exe', '-NoProfile', '-Command',
            '$adapters = @(Get-NetAdapter | Select-Object Name,Status,InterfaceDescription,ifIndex); '
            '$up = @($adapters | Where-Object Status -eq Up | Select-Object -ExpandProperty ifIndex); '
            '$routes = @(Get-NetRoute -ErrorAction Stop | Where-Object { '
            '$_.InterfaceIndex -in $up -and $_.DestinationPrefix -in '
            '@("0.0.0.0/0","::/0","0.0.0.0/1","128.0.0.0/1","::/1","8000::/1") } '
            '| Select-Object DestinationPrefix,InterfaceIndex,NextHop); '
            '$ps = @(Get-Process Photoshop -ErrorAction SilentlyContinue | Select-Object Id,StartTime); '
            '@{adapters=$adapters;photoshop=$ps;active_egress_routes=$routes} | ConvertTo-Json -Depth 4 -Compress'],
            capture_output=True, text=True, timeout=8, creationflags=subprocess.CREATE_NO_WINDOW)
        if state.returncode or not state.stdout.strip():
            raise RuntimeError('Network/process observation failed')
        sample.update(json.loads(state.stdout))
        adapters = sample['adapters']
        # Strong evidence only when no enumerated adapter is Up. Up is not proof
        # of Internet access, but an Up adapter prevents an independent offline claim.
        sample['all_adapters_down'] = bool(adapters) and all(a['Status'] != 'Up' for a in adapters)
        # Xbox peripherals can stay Up without an Internet route. Record routes
        # as a separate observation; do not equate route absence with absolute
        # proof of offline operation through every possible LAN proxy.
        sample['no_active_egress_route'] = bool(adapters) and not sample['active_egress_routes']
        if sample['no_active_egress_route'] and not sample['photoshop'] and not deployed:
            assert destination.resolve().parent == (Path(os.environ['APPDATA']) / 'Adobe/UXP/Plugins/External').resolve()
            destination.mkdir(parents=True, exist_ok=True)
            hashes = {}
            for name in ('manifest.json', 'main.js', 'probe-config.js'):
                shutil.copy2(source / name, destination / name)
                expected = hashlib.sha256((source / name).read_bytes()).hexdigest()
                assert hashlib.sha256((destination / name).read_bytes()).hexdigest() == expected
                if name != 'probe-config.js': hashes[name] = expected
            sample['offline_deployment'] = {'version': '0.1.3', 'verified_hashes': hashes,
                                            'adobe_installer_used': False}
            deployed = True
        if sample['photoshop']:
            verified = subprocess.run([sys.executable, str(root / 'tools/verify-uxp-file-probe.py'),
                                       '--timeout', '1'], capture_output=True, text=True,
                                      timeout=3, creationflags=subprocess.CREATE_NO_WINDOW)
            if verified.returncode == 0:
                sample['uxp_response'] = json.loads(verified.stdout)
            else:
                sample['uxp_response'] = None
    except Exception as exc:
        sample['error'] = str(exc)
    with output.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(sample, ensure_ascii=False) + '\n')
    time.sleep(3)
