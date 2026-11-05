"""Install or remove the machine-wide TSF input service from the backend.

A per-user app cannot write HKLM, so the action launches a short elevated copy of
itself and waits for a receipt. Nothing is written without the elevation prompt,
and removal deletes exactly the keys and files installation created.
"""
import ctypes
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from .paths import resource_root

CLSID = '{A4D1C7F2-5E3B-4C8D-9F01-6B2E8D4A7C15}'
PROFILE = '{C7E2B9A4-3D51-4F86-8B20-9A4D6E1F3C58}'
DESCRIPTION = '151500px-menu 输入法服务'
LANGIDS = (0x0804, 0x0409)
TIP_KEY = rf'SOFTWARE\Microsoft\CTF\TIP\{CLSID}'
CLASS_KEY = rf'SOFTWARE\Classes\CLSID\{CLSID}'
FILES = ('InputService.dll', 'InputContext.dll')
PAYLOAD = 'service.json'
PROGRAM_DATA = Path(os.environ.get('ProgramData', r'C:\ProgramData')) / 'PhotoshopMenu' / 'InputService'
OWNER_KEY = r'Software\PhotoshopMenu\InputService'
_register_cache = {'at': 0.0, 'value': None}


_hash_cache = {}


def _sha256(path):
    stat = os.stat(path)
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    if key in _hash_cache:
        return _hash_cache[key]
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    _hash_cache[key] = result = digest.hexdigest()
    return result


def _source(name):
    return Path(resource_root()) / 'native' / name


def _read_hklm(path, name=''):
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            return winreg.QueryValueEx(key, name)[0]
    except (FileNotFoundError, OSError):
        return None


def registered(ttl=2.0):
    """True when the TIP and the in-process COM class exist and at least one profile is enabled."""
    now = time.monotonic()
    if _register_cache['value'] is not None and now - _register_cache['at'] < ttl:
        return _register_cache['value']
    server = _read_hklm(CLASS_KEY + r'\InprocServer32')
    enabled = any(_read_hklm(rf'{TIP_KEY}\LanguageProfile\0x00000000\0x{lang:04x}', 'Enable') == 1 for lang in LANGIDS)
    value = bool(server) and enabled
    _register_cache.update(at=now, value=value)
    return value


def status():
    """Read-only state for the admin page and the action result."""
    server = _read_hklm(CLASS_KEY + r'\InprocServer32')
    enabled = [lang for lang in LANGIDS
               if _read_hklm(rf'{TIP_KEY}\LanguageProfile\0x00000000\0x{lang:04x}', 'Enable') == 1]
    files = {}
    for name in FILES:
        installed, source = PROGRAM_DATA / name, _source(name)
        files[name] = {
            'installed': installed.exists(),
            'source': source.exists(),
            'match': installed.exists() and source.exists() and _sha256(installed) == _sha256(source),
        }
    return {'registered': registered(0), 'server': server or '', 'languages': enabled,
            'files': files, 'install_dir': str(PROGRAM_DATA), 'channel': 'tsf' if registered(0) else 'injection',
            'needs_admin': True}


def set_owner(pid):
    """Publish this service process as the attach owner for the TSF transport."""
    import winreg
    key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, OWNER_KEY, 0, winreg.KEY_WRITE)
    try:
        winreg.SetValueEx(key, 'OwnerPid', 0, winreg.REG_DWORD, int(pid))
    finally:
        key.Close()


def request(operation, receipt_dir, timeout=120):
    """Launch the elevated helper and return its receipt content."""
    if operation not in ('install', 'remove'):
        raise ValueError('未知的输入法服务操作')
    receipt = Path(receipt_dir) / f'input-service-{operation}.json'
    try:
        receipt.unlink()
    except FileNotFoundError:
        pass
    executable, arguments = _elevated_command(operation, receipt)
    result = ctypes.windll.shell32.ShellExecuteW(None, 'runas', str(executable), arguments,
                                                 str(Path(executable).parent), 1)
    if result <= 32:
        raise RuntimeError('已取消管理员授权，输入法服务未更改')
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if receipt.is_file():
            try:
                content = json.loads(receipt.read_text('utf-8'))
            except (OSError, ValueError):
                time.sleep(0.2)
                continue
            try:
                receipt.unlink()
            except OSError:
                pass
            if not content.get('ok'):
                raise RuntimeError(content.get('error') or '输入法服务操作失败')
            return content
        time.sleep(0.25)
    raise RuntimeError('等待管理员操作结果超时；请重新打开后台确认状态')


def _elevated_command(operation, receipt):
    if getattr(sys, 'frozen', False):
        return Path(sys.executable), f'--input-service {operation} --receipt "{receipt}"'
    return Path(sys.executable), f'"{Path(resource_root()) / "main.py"}" --input-service {operation} --receipt "{receipt}"'


def apply_privileged(operation, receipt):
    """Runs only inside the elevated helper; writes the receipt the backend waits for."""
    value = {'ok': False, 'operation': operation, 'at': round(time.time())}
    try:
        if operation == 'install':
            value.update(_install())
        elif operation == 'remove':
            value.update(_remove())
        else:
            raise ValueError('未知的输入法服务操作')
        value['ok'] = True
    except Exception as exc:
        value['error'] = str(exc) or type(exc).__name__
    Path(receipt).write_text(json.dumps(value, ensure_ascii=False), 'utf-8')
    return value


def _install():
    import winreg
    for name in FILES:
        if not _source(name).is_file():
            raise RuntimeError(f'缺少原生组件 {name}')
    PROGRAM_DATA.mkdir(parents=True, exist_ok=True)
    copied = {}
    for name in FILES:
        target = PROGRAM_DATA / name
        data = _source(name).read_bytes()
        target.write_bytes(data)
        if _sha256(target) != hashlib.sha256(data).hexdigest():
            raise RuntimeError(f'{name} 写入校验失败')
        copied[name] = _sha256(target)
    server = PROGRAM_DATA / 'InputService.dll'
    with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, TIP_KEY, 0, winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY) as key:
        winreg.SetValueEx(key, '', 0, winreg.REG_SZ, DESCRIPTION)
    for lang in LANGIDS:
        path = rf'{TIP_KEY}\LanguageProfile\0x00000000\0x{lang:04x}'
        with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, path, 0, winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY) as key:
            winreg.SetValueEx(key, 'Description', 0, winreg.REG_SZ, DESCRIPTION)
            winreg.SetValueEx(key, 'IconFile', 0, winreg.REG_SZ, str(server))
            winreg.SetValueEx(key, 'IconIndex', 0, winreg.REG_DWORD, 0)
            winreg.SetValueEx(key, 'Enable', 0, winreg.REG_DWORD, 1)
    with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, CLASS_KEY, 0, winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY) as key:
        winreg.SetValueEx(key, '', 0, winreg.REG_SZ, DESCRIPTION)
    with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, CLASS_KEY + r'\InprocServer32', 0,
                            winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY) as key:
        winreg.SetValueEx(key, '', 0, winreg.REG_SZ, str(server))
        winreg.SetValueEx(key, 'ThreadingModel', 0, winreg.REG_SZ, 'Apartment')
    (PROGRAM_DATA / PAYLOAD).write_text(json.dumps({'version': 1, 'clsid': CLSID, 'files': copied,
                                                    'installed_at': round(time.time())}, ensure_ascii=False), 'utf-8')
    _register_cache['value'] = None
    return {'message': '输入法服务已注册；请重启 Photoshop 后生效', 'requires_photoshop_restart': True,
            'files': sorted(copied)}


def _remove():
    import winreg
    for path in (TIP_KEY, CLASS_KEY):
        _delete_tree(winreg.HKEY_LOCAL_MACHINE, path)
    removed = []
    for name in FILES + (PAYLOAD,):
        target = PROGRAM_DATA / name
        if target.is_file():
            target.unlink()
            removed.append(name)
    try:
        PROGRAM_DATA.rmdir()
    except OSError:
        pass
    _register_cache['value'] = None
    return {'message': '输入法服务已卸载；重启 Photoshop 后恢复原输入法行为',
            'requires_photoshop_restart': True, 'files': removed}


def _delete_tree(root, path):
    import winreg
    try:
        key = winreg.OpenKey(root, path, 0, winreg.KEY_READ | winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY)
    except FileNotFoundError:
        return
    while True:
        try:
            child = winreg.EnumKey(key, 0)
        except OSError:
            break
        _delete_tree(root, path + '\\' + child)
    key.Close()
    try:
        winreg.DeleteKey(root, path)
    except FileNotFoundError:
        pass
