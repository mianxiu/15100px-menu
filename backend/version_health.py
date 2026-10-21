"""Automatic, cached-state-only checks. Never queries or modifies Photoshop."""
import asyncio
import copy
import hashlib
import json
import platform
import re
import time
import uuid
from pathlib import Path

from .diagnostics import runtime_report
from .photoshop_version import MIN_PHOTOSHOP, version_tuple
from .settings import atomic_json
from .version import APP_VERSION

VERSION = re.compile(r'\d+(?:\.\d+){1,3}')
REPORT = re.compile(r'[a-f0-9]{32}\.json')


def error_codes(value):
    ps = value.get('photoshop', {})
    sources = [ps.get('message'), value.get('uxp', {}).get('error'),
               value.get('application_update', {}).get('error')]
    for name in ('background', 'menu'):
        row = (ps.get('layer_observation') or {}).get(name, {})
        sources += [row.get('error'), row.get('shape_error')]
    sources += [row.get('error') for row in value.get('tasks', {}).get('items', [])[:4]]
    return sorted({m.lower() for source in sources if isinstance(source, str)
                   for m in re.findall(r'\b0x[0-9a-fA-F]{8}\b', source[:4096])})[:16]


def version(value):
    return value if isinstance(value, str) and VERSION.fullmatch(value) else None


def os_version():
    if platform.system() == 'Windows':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Windows NT\CurrentVersion') as key:
                return winreg.QueryValueEx(key, 'CurrentBuild')[0]+'.'+str(winreg.QueryValueEx(key, 'UBR')[0])
        except OSError:
            pass
    return platform.version()[:80]


def assessment(value, system):
    """Whitelist metadata; raw messages, paths, document text and tokens stay out."""
    ps, uxp = value.get('photoshop', {}), value.get('uxp', {})
    versions = {'application':version(value.get('version')), 'photoshop':version(ps.get('photoshop_version')),
                'installed_uxp':version(uxp.get('version')), 'loaded_uxp':version(ps.get('uxp_version')),
                'bundled_uxp':version(uxp.get('bundled_version')), 'windows':system}
    ready = ps.get('uxp_ready') is True
    capability = ps.get('document_redraw_available')
    capability = capability if type(capability) is bool and ready else None
    findings = []
    def add(code, severity='warning'):
        findings.append({'code':code, 'severity':severity})
    if value.get('_status_unavailable') is True:
        add('status_unavailable')
        return versions, capability, findings, True
    if value.get('_status_format_unknown') is True:
        add('status_format_unknown')
        return versions, capability, findings, True
    recovery = ps.get('uxp_recovery') or {}
    running = (recovery.get('state') == 'checking' and recovery.get('session_current') is True
               and recovery.get('execution_exited') is not True
               and any(task.get('id') == recovery.get('task_id') and task.get('id')
                       and task.get('state') == 'running' and not task.get('restored')
                       and task.get('channel') == 'uxp-local-files'
                       for task in value.get('tasks', {}).get('items', [])))
    if recovery.get('active') and not running:
        add('result_unconfirmed')
    latest = (value.get('tasks', {}).get('items') or [{}])[0]
    if latest.get('state') in ('failed', 'result-unknown'):
        add('task_result_unknown' if latest['state']=='result-unknown' else 'task_failed')
    if uxp.get('enabled') is False:
        return versions, capability, findings, False
    if uxp.get('error'):
        add('plugin_installation_invalid')
    startup = value.get('photoshop_start') or {}
    host_expected = ready or ps.get('connected') is True or startup.get('phase') in ('started', 'failed')
    if host_expected and not ready:
        add('plugin_not_ready')
    if ready:
        if not versions['photoshop']:
            add('host_version_unrecognized')
        elif version_tuple(versions['photoshop']) < MIN_PHOTOSHOP:
            add('host_version_unsupported')
        if not versions['loaded_uxp']:
            add('plugin_version_unrecognized')
        if versions['loaded_uxp'] != versions['installed_uxp']:
            add('plugin_reload_required')
        if versions['photoshop'] and version_tuple(versions['photoshop']) >= (24, 1, 0):
            if capability is False:
                add('redraw_api_missing')
            elif capability is None:
                add('redraw_capability_unreported')
        elif versions['photoshop']:
            add('legacy_preview_available' if ps.get('legacy_preview_available') is True else 'legacy_preview_pending', 'info')
    return versions, capability, findings, ready or host_expected or bool(findings)


class VersionHealth:
    def __init__(self, runtime, *, clock=time.monotonic, wall=time.time, system=None, settle=6):
        self.root = Path(runtime)/'version-health'
        self.clock, self.wall = clock, wall
        self.system = os_version() if system is None else system
        self.settle = settle
        self.task = None
        self.closed = False
        self.candidate = None
        self.signature = None
        self.retry_after = 0
        self.storage_lock = asyncio.Lock()
        self.state = {'schema':1, 'phase':'waiting', 'message':'等待版本与连接状态', 'ready':False,
                      'attention':False, 'acknowledged':False, 'last_success':None}
        try:
            p = self.root/'state.json'
            if p.stat().st_size > 65536:
                raise ValueError('oversized state')
            data = json.loads(p.read_text('utf-8'))
            if data.get('schema') != 1 or not REPORT.fullmatch(data.get('report_file', '')):
                raise ValueError('invalid state')
            report = self._load(data['report_file'])
            self.state = {k:copy.deepcopy(report[k]) for k in ('schema','phase','message','attention','last_success')}
            self.state.update(ready=True, report_file=data['report_file'], report_id=report['id'],
                              checked_at=report['checked_at'], versions=report['versions'], findings=report['findings'],
                              changed=report['changed'], acknowledged=data.get('acknowledged') is True)
            self.signature = data.get('signature') if isinstance(data.get('signature'), str) else None
        except FileNotFoundError:
            pass
        except (OSError, ValueError, KeyError, TypeError):
            self.state.update(message='上次自检记录不可用，等待重新检查')

    def snapshot(self):
        return copy.deepcopy({k:v for k,v in self.state.items() if k not in ('report_file',)})

    def _load(self, name):
        if not isinstance(name, str) or not REPORT.fullmatch(name):
            raise ValueError('invalid report identity')
        p = self.root/'reports'/name
        if p.is_symlink() or p.stat().st_size > 65536:
            raise ValueError('invalid report')
        value = json.loads(p.read_text('utf-8'))
        if value.get('schema') != 1 or value.get('source') != 'automatic-version-health' or value.get('read_only') is not True:
            raise ValueError('invalid report')
        return value

    def observe(self, value):
        try:
            self._observe(value)
        except Exception:
            # An unexpected future status format must never break the menu,
            # the regular status feed, or become permission to retry a write.
            self.state.update(phase='warning', attention=True, acknowledged=False,
                              message='自检遇到未知状态格式，请检查统一诊断')
            try:
                self._observe({'version':APP_VERSION, '_status_format_unknown':True})
            except Exception:
                pass

    def _observe(self, value):
        if self.closed:
            return
        versions, capability, findings, available = assessment(value, self.system)
        if not available:
            self.candidate = None
            return
        previous = self.state.get('versions', {})
        if capability is False and (self.state.get('last_success') or {}).get('redraw_document') is True:
            findings.append({'code':'redraw_capability_lost','severity':'warning'})
        latest = (value.get('tasks', {}).get('items') or [{}])[0]
        failure = latest.get('id') if latest.get('state') in ('failed', 'result-unknown') else None
        codes = error_codes(value)
        key = hashlib.sha256(json.dumps([versions, capability, findings, failure, codes], sort_keys=True).encode()).hexdigest()
        if key == self.signature:
            self.candidate = None
            return
        now = self.clock()
        if now < self.retry_after:
            return
        if not self.candidate or self.candidate[0] != key:
            self.candidate = (key, now)
            return
        if now-self.candidate[1] < self.settle or self.task and not self.task.done():
            return
        # A version check never competes with an interaction. Unknown-result
        # evidence is cached-only and can still be retained without clearing it.
        if not any(f['code']=='result_unconfirmed' for f in findings) and (
                value.get('photoshop', {}).get('busy') or value.get('menu', {}).get('visible') or
                value.get('photoshop_start', {}).get('active')):
            return
        report = {'schema':1, 'source':'automatic-version-health', 'read_only':True,
                  'id':uuid.uuid4().hex, 'checked_at':self.wall(), 'versions':versions,
                  'capabilities':{'redraw_document':capability}, 'findings':findings,
                  'changed':[k for k in versions if previous.get(k)!=versions[k]],
                  'attention':any(f['severity']=='warning' for f in findings),
                  'error_codes':codes,
                  'original_request':{k:v for k,v in (value.get('photoshop', {}).get('uxp_recovery') or {}).items()
                                      if k in ('request_id','task_id') and isinstance(v,str) and re.fullmatch(r'[a-f0-9]{32}',v)},
                  'scope':'cached-status-only; no Photoshop request, document edit, input or network',
                  'runtime':runtime_report({'application':{'version':versions['application']}, **value})}
        report['runtime']['tasks'] = report['runtime']['tasks'][:12]
        for item in report['runtime']['tasks']:
            item['timeline'] = item.get('timeline', [])[:8]
        report['phase'] = 'warning' if report['attention'] else 'completed'
        report['message'] = '版本自检发现异常，已保留报告' if report['attention'] else '版本与连接自检完成'
        report['last_success'] = self.state.get('last_success')
        if not report['attention']:
            report['last_success'] = {'checked_at':report['checked_at'], 'versions':versions,
                                      'redraw_document':capability}
        self.task = asyncio.create_task(self._record(report, key))

    async def _record(self, report, signature):
        try:
            async with self.storage_lock:
                await asyncio.to_thread(self._write, report, signature)
                self.signature = signature
                self.state = {k:copy.deepcopy(report[k]) for k in ('schema','phase','message','versions','changed',
                              'checked_at','attention','findings','last_success')}
                self.state.update(ready=True, report_id=report['id'], report_file=report['id']+'.json', acknowledged=False)
        except Exception:
            self.retry_after = self.clock()+60
            self.state.update(phase='warning', attention=True, acknowledged=False,
                              message='自检报告保存失败，请检查运行日志')
        finally:
            self.candidate = None

    def _write(self, report, signature):
        if len(json.dumps(report).encode()) > 65536:
            raise ValueError('report size limit')
        atomic_json(self.root/'reports'/(report['id']+'.json'), report)
        atomic_json(self.root/'state.json', {'schema':1, 'report_file':report['id']+'.json',
                                            'signature':signature, 'acknowledged':False})
        reports = sorted((self.root/'reports').glob('*.json'), key=lambda p:p.stat().st_mtime, reverse=True)
        for p in reports[20:]:
            if REPORT.fullmatch(p.name) and not p.is_symlink():
                try:
                    if self._load(p.name).get('source') == 'automatic-version-health':
                        p.unlink()
                except (OSError, ValueError):
                    pass

    async def acknowledge(self):
        if self.task and not self.task.done():
            await self.task
        if not self.state.get('ready'):
            return self.snapshot()
        async with self.storage_lock:
            await asyncio.to_thread(atomic_json, self.root/'state.json', {'schema':1,
                'report_file':self.state['report_file'], 'signature':self.signature, 'acknowledged':True})
            self.state['acknowledged'] = True
        return self.snapshot()

    async def export(self):
        if not self.state.get('ready'):
            raise RuntimeError('尚无自动自检报告')
        return await asyncio.to_thread(self._load, self.state['report_file'])

    async def close(self):
        self.closed = True
        if self.task:
            await asyncio.gather(self.task, return_exceptions=True)
