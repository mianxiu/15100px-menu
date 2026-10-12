"""Read Photoshop's local MRU presets, without changing its preferences."""
import hashlib
import json
import math
import os
from pathlib import Path
from .clipboard_preset import image_metadata, clipboard_document

UNITS = {'pixelsUnit':'px', 'millimetersUnit':'mm', 'centimetersUnit':'cm',
         'inchesUnit':'in', 'pointsUnit':'pt', 'picasUnit':'pc'}


def preset_id(preset):
    return hashlib.sha256(json.dumps(preset, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()[:24]


def valid_preset(preset):
    if not isinstance(preset, dict) or preset.get('units') not in UNITS:
        return False
    if any(type(preset.get(k)) not in (float, int) or not math.isfinite(preset[k]) or
           not 0 < preset[k] <= 300000 for k in ('width', 'height')):
        return False
    return len(json.dumps(preset, ensure_ascii=False).encode('utf-8')) <= 3000


def display(preset):
    def number(value):return f'{value:.2f}'.rstrip('0').rstrip('.')
    resolution = preset.get('resolution')
    density = ('印刷' if resolution == 'print' else
               f'{resolution:g} ppi' if type(resolution) in (float, int) else str(resolution or '默认'))
    if preset.get('resolutionUnits') == 'centimetersUnit' and type(resolution) in (float, int):
        density = f'{resolution:g} px/cm'
    name = str(preset.get('name') or '自定')[:80]
    if name in ('Custom', '自定'): name = '自定'
    return {'id':preset_id(preset), 'name':name,
            'size':f"{number(preset['width'])} × {number(preset['height'])} {UNITS[preset['units']]}",
            'detail':density + ' · ' + str(preset.get('mode') or '默认'),
            'last_used':preset.get('lastUsedTime', 0)}


class RecentDocuments:
    def __init__(self, roaming=None, clipboard_reader=None):
        self.adobe = Path(roaming or os.environ.get('APPDATA', '')) / 'Adobe'
        self.signature = None
        self.presets = {}
        self.snapshot = {'items':[], 'message':'等待读取 Photoshop 最近预设'}
        self.clipboard_reader=clipboard_reader or image_metadata
        self.clipboard_identity=None

    def with_clipboard(self):
        try:metadata=self.clipboard_reader()
        except (OSError,ValueError):metadata=None
        self.clipboard_identity=None
        item={'id':'','name':'剪贴板','size':'—','detail':'','available':False}
        if metadata:
            preset=clipboard_document(metadata)
            if valid_preset(preset):
                identity='clipboard_'+preset_id(metadata)
                self.clipboard_identity=identity
                item={**display(preset),'id':identity,'name':'剪贴板','available':True}
        return {**self.snapshot,'items':[item,*self.snapshot['items'][:8]]}

    def refresh(self, host_version):
        # Match the running UXP host, never whichever installed PS is newest.
        try: year = int(host_version.split('.')[0]) + 1999
        except (ValueError, AttributeError):
            self.presets = {};self.signature = None
            self.snapshot = {'items':[], 'message':'等待读取 Photoshop 版本'}
            return dict(self.snapshot)
        path = self.adobe / f'Adobe Photoshop {year}' / f'Adobe Photoshop {year} Settings' / 'MRU New Doc Sizes.json'
        if self.signature and self.signature[0]!=str(path):
            self.signature=None;self.presets={};self.snapshot={'items':[], 'message':'最近预设暂不可读'}
        try:
            stat = path.stat()
            signature = (str(path), stat.st_mtime_ns, stat.st_size)
            if signature == self.signature:return self.with_clipboard()
            if stat.st_size > 1024*1024:raise ValueError('最近预设文件过大')
            data = json.loads(path.read_text('utf-8-sig'))
            presets = data['presets']
            if not isinstance(presets, list):raise ValueError('最近预设格式无法识别')
            records = [p for p in presets[:128] if valid_preset(p)]
            records.sort(key=lambda p: p.get('lastUsedTime', 0) if type(p.get('lastUsedTime', 0)) in (int, float) else 0, reverse=True)
            records = records[:8]
            self.presets = {preset_id(p):p for p in records}
            self.snapshot = {'items':[display(p) for p in self.presets.values()],
                             'message':'' if records else '暂无最近新建预设'}
            self.signature = signature
        except (OSError, ValueError, KeyError, TypeError):
            # PS writes this file non-atomically. Keep a previous valid snapshot
            # through a partial write; retry next poll, never replace it empty.
            if self.signature is None:
                self.snapshot = {'items':[], 'message':'最近预设暂不可读'}
        return self.with_clipboard()

    def resolve(self, identity):
        if isinstance(identity,str) and identity.startswith('clipboard_'):
            metadata=self.clipboard_reader()
            if not metadata or identity!=self.clipboard_identity or identity!='clipboard_'+preset_id(metadata):
                raise ValueError('剪贴板图像已改变，请重新打开菜单')
            return clipboard_document(metadata)
        if not isinstance(identity, str) or identity not in self.presets:
            raise ValueError('最近预设已改变，请重新打开菜单')
        # A detached copy freezes exactly the settings the user saw.
        return json.loads(json.dumps(self.presets[identity]))
