"""Bounded real UXP read-only request/response check. No COM or Internet calls."""
import argparse
import json
import os
from pathlib import Path
import secrets
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--timeout', type=float, default=10)
    args = parser.parse_args()
    if not 1 <= args.timeout <= 30:
        parser.error('timeout must be 1..30 seconds')
    root = Path(__file__).resolve().parents[1]
    folder = Path(os.environ['APPDATA']) / (
        'Adobe/UXP/PluginsStorage/PHSP/24/External/'
        'com.15100px.menu.offline-probe/PluginData')
    if not folder.is_dir():
        raise RuntimeError('PluginData missing; wait for real Photoshop startup')
    token = json.loads((root / '.runtime/uxp-offline-probe-config.json').read_text('utf-8'))['token']
    request_id = secrets.token_hex(16)
    started = time.perf_counter()
    created_ms = int(time.time() * 1000)
    request = {'id': request_id, 'token': token, 'operation': 'inspect',
               'expires_at_ms': created_ms + int(args.timeout * 1000)}
    temporary = folder / ('probe-request-' + request_id + '.tmp')
    temporary.write_text(json.dumps(request), encoding='utf-8')
    os.replace(temporary, folder / 'probe-request.json')
    result = None
    deadline = started + args.timeout
    while time.perf_counter() < deadline:
        try:
            response = json.loads((folder / 'probe-response.json').read_text('utf-8'))
            if (response.get('id') == request_id and response.get('probe_version') in ('0.1.3','0.2.0')
                    and response.get('operation') == 'inspect' and response.get('phase') == 'completed'):
                result = {'request_id': request_id, 'response': response,
                          'roundtrip_ms': round((time.perf_counter() - started) * 1000, 2)}
                break
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        time.sleep(.02)
    if result is None:
        raise RuntimeError('No matching UXP response; stale heartbeat is not acceptance')
    evidence = root / '.runtime/uxp-file-probe-verification.jsonl'
    with evidence.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps({'verified_at_ms': int(time.time() * 1000), **result}) + '\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
