"""Maintain only our entry in an existing per-user UXP index.

An absent index stays absent so Photoshop continues scanning External.
The shared index is never treated as an application-owned file.
"""
import copy
import json
import os
from pathlib import Path
import tempfile


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError('UXP 加载索引含重复字段，已保留')
        result[key] = value
    return result


class UxpRegistration:
    def __init__(self, path, plugin, plugin_id):
        self.path, self.plugin, self.plugin_id = Path(path), Path(plugin), plugin_id
        self.load_path = '$localPlugins\\External\\'+self.plugin.name

    def read(self):
        try:
            with self.path.open('rb') as stream: raw = stream.read(2*1024*1024+1)
        except FileNotFoundError: return None, None, None
        if len(raw) > 2*1024*1024: raise ValueError('UXP 加载索引过大，已保留')
        try: data = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=unique_object)
        except (ValueError, UnicodeError) as error: raise ValueError('UXP 加载索引无法安全读取，已保留') from error
        if not isinstance(data, dict) or not isinstance(data.get('plugins'), list) or any(not isinstance(p, dict) for p in data['plugins']):
            raise ValueError('UXP 加载索引结构无法识别，已保留')
        entries = [p for p in data['plugins'] if p.get('pluginId') == self.plugin_id]
        if len(entries) > 1: raise ValueError('UXP 加载索引含重复插件登记，已保留')
        entry = entries[0] if entries else None
        if entry is not None:
            path = entry.get('path')
            if not isinstance(path, str): raise ValueError('本插件加载登记路径无效，已保留')
            normalized = path.replace('\\', '/').rstrip('/').casefold()
            expected = ('$localPlugins/External/'+self.plugin.name).casefold()
            if normalized != expected and os.path.normcase(os.path.abspath(path)) != os.path.normcase(str(self.plugin.resolve())):
                raise ValueError('本插件已登记到其他路径，已保留；请先检查原安装')
        return raw, data, entry

    def status(self, manifest=None):
        try:
            raw, _, entry = self.read()
            if raw is None: state = 'directory'
            elif entry is None: state = 'missing'
            elif entry.get('status') != 'enabled': state = 'disabled'
            elif manifest and (entry.get('path') != self.load_path or any(entry.get(k) != v for k, v in self.metadata(manifest).items())): state = 'outdated'
            else: state = 'registered'
            return {'state':state, 'index_path':str(self.path), 'needs_repair':state in ('missing','disabled','outdated'), 'auto_repair':state in ('missing','outdated'), 'error':''}
        except (OSError, ValueError) as error:
            return {'state':'invalid', 'index_path':str(self.path), 'needs_repair':False, 'auto_repair':False, 'error':str(error)}

    def metadata(self, manifest):
        return {'hostMinVersion':manifest['host']['minVersion'], 'name':manifest['name'], 'type':'uxp', 'versionString':manifest['version']}

    def snapshot(self):
        raw, _, entry = self.read()
        return raw, {'entry':entry}

    def prepare(self, manifest=None, *, enable=False, restore=None):
        raw, data, entry = self.read()
        if raw is None:
            if restore and restore['entry'] is not None: raise ValueError('原 UXP 加载索引已移除，未自动重建共享索引')
            return raw, None
        if restore is not None: wanted = copy.deepcopy(restore['entry'])
        elif manifest is None: wanted = None
        else:
            wanted = {**(entry or {}), **self.metadata(manifest), 'pluginId':self.plugin_id,
                      'path':self.load_path,
                      'status':'enabled' if enable or entry is None else entry.get('status')}
        if wanted == entry: return raw, None
        result = copy.deepcopy(data)
        result['plugins'] = [wanted if p.get('pluginId') == self.plugin_id else p for p in result['plugins']]
        if wanted is None: result['plugins'] = [p for p in result['plugins'] if p is not None]
        elif entry is None: result['plugins'].append(wanted)
        return raw, result

    def commit(self, plan):
        raw, data = plan
        # Check no-op plans too: a newly created index could hide the plugin.
        current, _, _ = self.read()
        if current != raw: raise RuntimeError('UXP 加载索引已被其他程序修改，请刷新后重试；未覆盖')
        if data is None: return
        content = (json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
        fd, temp = tempfile.mkstemp(prefix='PS.menu-',suffix='.tmp',dir=self.path.parent)
        try:
            with os.fdopen(fd,'wb') as stream: stream.write(content);stream.flush();os.fsync(stream.fileno())
            if self.path.read_bytes() != raw: raise RuntimeError('UXP 加载索引已被其他程序修改，请刷新后重试；未覆盖')
            os.replace(temp,self.path)
        finally:
            if os.path.exists(temp): os.unlink(temp)
