"""Bounded native message/first-frame benchmark; no hotkeys or PS actions.

Shows an isolated, non-activating menu. Numbers measure message handling and
CPU render progress, NOT physical key-to-photon latency.
"""
import argparse
import json
from pathlib import Path
import queue
import statistics
import subprocess
import threading
import time
import win32con
import win32gui


def run(executable, cycles=30):
    with subprocess.Popen([str(Path(executable).resolve())], stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                          text=True, encoding='utf-8', creationflags=0x08000000) as process:
        ready = queue.Queue()
        threading.Thread(target=lambda: ready.put(process.stdout.readline()), daemon=True).start()
        try:
            hwnd = json.loads(ready.get(timeout=10))['hwnd']
            def frames():
                return win32gui.SendMessageTimeout(hwnd, 0x800b, 0, 0,
                    win32con.SMTO_ABORTIFHUNG, 1000)[1]
            response, first_frame = [], []
            for cycle in range(cycles):
                before = frames()
                start = time.perf_counter()
                win32gui.ShowWindow(hwnd, win32con.SW_SHOWNOACTIVATE)
                deadline = start+2
                while frames() <= before:
                    if time.perf_counter() >= deadline:
                        raise RuntimeError('Reopened menu stopped rendering')
                    time.sleep(.001)
                first_frame.append((time.perf_counter()-start)*1000)
                for _ in range(6):
                    time.sleep(.003)
                    start = time.perf_counter()
                    frames()
                    response.append((time.perf_counter()-start)*1000)
                win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
                time.sleep(.005)
            def summarize(values):
                return {'samples':len(values),'median_ms':round(statistics.median(values),3),
                        'p95_ms':round(sorted(values)[int(.95*(len(values)-1))],3),
                        'max_ms':round(max(values),3)}
            return {'executable':str(executable),'message_response':summarize(response),
                    'show_to_render_observed':summarize(first_frame)}
        finally:
            process.stdin.close()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = run(args.executable)
    text = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(text, encoding='utf-8')
    print(text)
