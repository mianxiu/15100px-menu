"""Experimental serialized client; never silently falls back to COM or retries."""
import json
import os
from pathlib import Path
import secrets
import threading
import time

class Client:
    def __init__(self):
        root = Path(__file__).resolve().parents[1]
        self.token = json.loads((root/'.runtime/uxp-offline-probe-config.json').read_text('utf-8'))['token']
        self.folder = Path(os.environ['APPDATA'])/'Adobe/UXP/PluginsStorage/PHSP/24/External/com.15100px.menu.offline-probe/PluginData'
        self.lock = threading.Lock()
        self.uncertain = False

    def call(self, operation, **payload):
        if not self.lock.acquire(blocking=False):
            raise RuntimeError('Busy: request rejected, not queued')
        try:
            if self.uncertain:
                raise RuntimeError('Previous result unknown; inspect Photoshop before continuing')
            identity = secrets.token_hex(16)
            request = {**payload,'id':identity,'token':self.token,'operation':operation,
                       'expires_at_ms':int(time.time()*1000)+5000}
            temporary = self.folder/('request-'+identity+'.tmp')
            temporary.write_text(json.dumps(request),'utf-8')
            os.replace(temporary,self.folder/'probe-request.json')
            end = time.monotonic()+8
            while time.monotonic()<end:
                try:
                    response=json.loads((self.folder/'probe-response.json').read_text('utf-8'))
                    if response.get('id')==identity:
                        if response.get('phase')!='completed':
                            raise RuntimeError(response.get('error','UXP failed'))
                        return response
                except (FileNotFoundError,json.JSONDecodeError): pass
                time.sleep(.02)
            self.uncertain=True
            raise TimeoutError('UXP result unknown; no automatic retry or COM fallback')
        finally:
            self.lock.release()
