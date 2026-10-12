"""Bounded read-only evidence: physical network status during the UXP restart test."""
from pathlib import Path
import json
import subprocess
import time

root = Path(__file__).resolve().parents[1]
output = root / '.runtime/uxp-offline-network.jsonl'
stop = root / '.runtime/stop-uxp-offline-observer'
for _ in range(180):  # At most 15 minutes; never disconnects or changes adapters.
    if stop.exists(): break
    try:
        result = subprocess.run(['powershell.exe','-NoProfile','-Command',
            'Get-NetAdapter -Physical | Select-Object Name,Status | ConvertTo-Json -Compress'],
            capture_output=True, text=True, timeout=8, creationflags=subprocess.CREATE_NO_WINDOW)
        record = {'time':time.time(),'adapters':json.loads(result.stdout),'error':result.stderr.strip()}
    except Exception as exc:
        record = {'time':time.time(),'error':str(exc)}
    with output.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(record, ensure_ascii=False)+'\n')
    time.sleep(5)
