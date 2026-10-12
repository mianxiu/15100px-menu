"""Open the original Photoshop shortcut through the existing Explorer desktop.

Does not close Photoshop, retry a failed launch, or change Adobe settings.
"""
import argparse
import json
from pathlib import Path
import sys
import time
from urllib.request import urlopen

import win32api
import win32com.client
import win32process

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.uxp_management import photoshop_running


def status():
    return json.load(urlopen('http://127.0.0.1:15151/api/status', timeout=5))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shortcut', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=45, choices=range(1, 121))
    parser.add_argument('--report', type=Path, default=ROOT/'.runtime/photoshop-desktop-launch-verification.json')
    args = parser.parse_args()
    if photoshop_running():
        print('Photoshop is already running; no launch or restart attempted')
        return 0
    if status()['photoshop'].get('busy'):
        raise RuntimeError('Backend is busy; no launch attempted')
    shortcut = args.shortcut.resolve(strict=True)
    if shortcut.suffix.lower() != '.lnk':
        raise ValueError('An existing Photoshop .lnk shortcut is required')
    details = win32com.client.Dispatch('WScript.Shell').CreateShortcut(str(shortcut))
    if Path(details.TargetPath).name.lower() != 'photoshop.exe':
        raise ValueError('The shortcut does not target Photoshop.exe')
    Path(details.TargetPath).resolve(strict=True)

    # Shell.Application alone does not identify the process executing a launch.
    # Bind to the existing desktop and ask its hosted Application instead.
    shell = win32com.client.Dispatch('Shell.Application')
    desktop = shell.Windows().FindWindowSW(0, 0, 8, 0, 1)
    desktop_pid = win32process.GetWindowThreadProcessId(desktop.HWND)[1]
    handle = win32api.OpenProcess(0x410, False, desktop_pid)
    try:
        if Path(win32process.GetModuleFileNameEx(handle, 0)).name.lower() != 'explorer.exe':
            raise RuntimeError('Desktop is not hosted by Explorer; launch refused')
    finally:
        handle.Close()
    if photoshop_running():
        print('Photoshop became active; no duplicate launch attempted')
        return 0
    report = {'method': 'existing Explorer desktop Document.Application.ShellExecute(original shortcut)',
              'shortcut': str(shortcut), 'desktop_pid': desktop_pid,
              'started_at_ms': int(time.time()*1000), 'observations': [],
              'scope': 'One launch, backend connection and UXP readiness; not repeated restart stability.'}
    desktop.Document.Application.ShellExecute(str(shortcut), '', '', 'open', 1)
    deadline = time.monotonic()+args.timeout
    report['ready'] = False
    while time.monotonic() < deadline:
        ps = status()['photoshop']
        report['observations'].append({'elapsed_ms': int(time.time()*1000)-report['started_at_ms'],
                                       'process_running': photoshop_running(),
                                       'connected': ps.get('connected'), 'uxp_ready': ps.get('uxp_ready'),
                                       'message': ps.get('message')})
        if ps.get('connected') and ps.get('uxp_ready'):
            report['ready'] = True
            break
        time.sleep(1)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), 'utf-8')
    print(json.dumps({'ready': report['ready'], 'last': report['observations'][-1]}))
    return 0 if report['ready'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
