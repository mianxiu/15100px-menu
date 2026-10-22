import ctypes
import json
import os
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import time
import unittest
from backend.paths import ROOT


@unittest.skipUnless(os.name=='nt' and (ROOT/'native/MenuHost.exe').is_file(),'Windows native menu')
class BenchmarkResponsivenessTests(unittest.TestCase):
    def test_warp_benchmark_pumps_messages_and_closes_without_kill(self):
        import win32api,win32gui,win32process
        u=ctypes.WinDLL('user32');u.IsHungAppWindow.argtypes=[ctypes.c_void_p];u.IsHungAppWindow.restype=ctypes.c_int
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'result.json';events=queue.Queue()
            with (Path(folder)/'error.log').open('w+',encoding='utf-8') as error:
                p=subprocess.Popen([str(ROOT/'native/MenuHost.exe'),'--render-mode','cpu','--benchmark-shape-output',str(output),'--benchmark-render-completion'],stdout=subprocess.PIPE,stderr=error,text=True,encoding='utf-8',creationflags=0x08000000)
                def read():
                    for line in p.stdout:
                        try:value=json.loads(line)
                        except ValueError:continue
                        if value.get('type')=='benchmark.started':events.put(value)
                    events.put(None)
                threading.Thread(target=read,daemon=True).start()
                try:
                    h=win32api.OpenProcess(0x200|0x400,False,p.pid)
                    try:
                        allowed=win32process.GetProcessAffinityMask(h)[0];bits=[1<<i for i in range(64) if allowed&(1<<i)]
                        win32process.SetProcessAffinityMask(h,sum(bits[:2]));win32process.SetPriorityClass(h,win32process.BELOW_NORMAL_PRIORITY_CLASS)
                    finally:h.Close()
                    event=events.get(timeout=30)
                    if event is None:
                        error.flush();error.seek(0);self.fail(error.read())
                    hwnd=event['hwnd'];self.assertEqual(win32process.GetWindowThreadProcessId(hwnd)[1],p.pid)
                    deadline=time.monotonic()+6.5;samples=0
                    while time.monotonic()<deadline:
                        self.assertIsNone(p.poll(),'Full WARP benchmark ended before responsiveness observation')
                        win32gui.SendMessageTimeout(hwnd,0,0,0,2,300)
                        self.assertFalse(u.IsHungAppWindow(hwnd));samples+=1;time.sleep(.05)
                    self.assertGreater(samples,20)
                    win32gui.PostMessage(hwnd,0x10,0,0)
                    self.assertEqual(p.wait(timeout=2),0)
                    self.assertFalse(output.exists(),'A cancelled benchmark must not publish complete timings')
                finally:
                    if p.poll() is None:p.kill();p.wait(timeout=5) # Only this owned test, never PS or the service.
                    p.stdout.close()
