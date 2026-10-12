"""Local-only receiver for a read-only UXP installation probe. Never installs UDT."""
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import argparse
import json
import secrets
import time

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    config = root / '.runtime/uxp-offline-probe-config.json'
    evidence = root / '.runtime/uxp-offline-probe-events.jsonl'
    if args.prepare:
        if config.exists():
            raise RuntimeError('Existing probe config: preserve its evidence; do not silently replace token')
        config.parent.mkdir(parents=True, exist_ok=True)
        token = secrets.token_hex(24)
        config.write_text(json.dumps({'token':token,'prepared_at':time.time()}), encoding='utf-8')
        (root / 'uxp/offline-probe/probe-config.js').write_text(
            'module.exports = ' + json.dumps(token) + ';\n', encoding='utf-8')
        print('Probe prepared; no Photoshop settings or documents changed')
        return
    token = json.loads(config.read_text(encoding='utf-8'))['token']

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            if self.path != '/probe':
                self.send_error(404); return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 4096: raise ValueError('Invalid body length')
                body = json.loads(self.rfile.read(length))
                if not secrets.compare_digest(str(body.pop('token', '')), token):
                    self.send_error(403); return
                if body.get('plugin_id') != 'com.15100px.menu.offline-probe':
                    self.send_error(400); return
                with evidence.open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps({'received_at':time.time(), **body}, ensure_ascii=False)+'\n')
            except (ValueError, TypeError):
                self.send_error(400); return
            self.send_response(200); self.end_headers(); self.wfile.write(b'OK')
        def do_GET(self):
            if self.path != '/status':
                self.send_error(404); return
            events = [json.loads(line) for line in evidence.read_text(encoding='utf-8').splitlines()] if evidence.exists() else []
            self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers()
            self.wfile.write(json.dumps({'event_count':len(events),'latest':events[-1] if events else None}).encode())

    HTTPServer(('127.0.0.1',15154), Handler).serve_forever()

if __name__ == '__main__': main()
