import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from backend.menu_model import MenuSelection, display_shortcut
from backend.settings import DEFAULTS, Settings, chord
from backend.paths import ROOT


class MenuTests(unittest.TestCase):
    @unittest.skipUnless(os.name=='nt' and (ROOT/'native/HotkeyHost.exe').is_file(),'Windows native hook')
    def test_hook_renewal_recovers_removal_and_preserves_held_press(self):
        result=subprocess.run([str(ROOT/'native/HotkeyHost.exe'),'--self-test-hooks'],
            capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('30 silent-removal cycles',result.stdout)

    @unittest.skipUnless(os.name=='nt' and (ROOT/'native/MenuHost.exe').is_file(),'Windows native menu')
    def test_real_setwindowpos_pie_becomes_opaque_and_closes(self):
        import queue
        import threading
        import win32con as c
        import win32gui
        ready = queue.Queue()
        process = subprocess.Popen([str(ROOT/'native/MenuHost.exe')], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding='utf-8',
            creationflags=0x08000000)
        threading.Thread(target=lambda:ready.put(process.stdout.readline()), daemon=True).start()
        try:
            hwnd = json.loads(ready.get(timeout=10))['hwnd']
            def message(code, wp=0, lp=0):
                return win32gui.SendMessageTimeout(hwnd, code, wp, lp, c.SMTO_ABORTIFHUNG, 1000)[1]
            for cycle in range(10):
                # Production prepare flags include type eligibility; all slots
                # must stay visible even for Background/unknown selection.
                mask,kind=((1,1),(15,4),(0,0),(2,8),(3,3))[cycle%5]
                message(0x8011,16|1|64|(mask<<8)|(kind<<12),cycle+1)
                self.assertEqual(message(0x8012), 0, 'Preparing must not expose the stale surface')
                # Same display API as desktop.show_popup; avoid taking user focus.
                win32gui.SetWindowPos(hwnd, c.HWND_TOP, 100,100,620,440, c.SWP_SHOWWINDOW|c.SWP_NOACTIVATE)
                self.assertTrue(win32gui.IsWindowVisible(hwnd))
                deadline=time.monotonic()+2
                while message(0x8012)<1000 and time.monotonic()<deadline:
                    time.sleep(.01)
                self.assertEqual(message(0x8012),1000,'Visible HWND must not remain transparent')
                # Pin survives release; ordinary release suppresses the surface
                # before the backend receives its asynchronous hide action.
                if cycle%2:
                    message(0x8010,1)
                    message(0x800e)
                    self.assertEqual(message(0x8012),1000)
                    message(0x8010,0)
                message(0x800e)
                self.assertEqual(message(0x8012),0)
                time.sleep(.025)
                self.assertEqual(message(0x8012),0,'Late frames must not reveal a released pie')
                win32gui.ShowWindow(hwnd,c.SW_HIDE)
                self.assertFalse(win32gui.IsWindowVisible(hwnd))
        finally:
            process.stdin.close()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
            process.stdout.close()

    @unittest.skipUnless(os.name=='nt' and (ROOT/'native/MenuHost.exe').is_file(),'Windows native menu')
    def test_frame_wait_keeps_messages_and_reopen_responsive(self):
        import runpy
        benchmark = runpy.run_path(str(ROOT/'tools/benchmark-menu-response.py'))['run']
        result = benchmark(ROOT/'native/MenuHost.exe', cycles=8)
        self.assertEqual(result['show_to_render_observed']['samples'], 8)
        self.assertEqual(result['message_response']['samples'], 48)

    @unittest.skipUnless(os.name=='nt' and (ROOT/'native/MenuHost.exe').is_file(),'Windows native menu')
    def test_font_update_prepares_while_menu_stays_hidden(self):
        import win32gui
        with tempfile.TemporaryFile(mode='w+b') as log:
            process = subprocess.Popen([str(ROOT/'native/MenuHost.exe')], stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=log, text=True, encoding='utf-8')
            try:
                ready = json.loads(process.stdout.readline())
                hwnd = ready['hwnd']
                self.assertFalse(win32gui.IsWindowVisible(hwnd))
                event = {'type':'status','data':{'photoshop':{'connected':False,'ui_font_size':'large'},
                                               'settings':{'enabled':True,'shortcuts':{}}}}
                process.stdin.write(json.dumps(event)+'\n');process.stdin.flush()
                deadline = time.monotonic()+8
                contents = ''
                while time.monotonic()<deadline:
                    log.seek(0);contents=log.read().decode('utf-8',errors='replace')
                    if 'Font selection ready: large, cached' in contents:break
                    if process.poll() is not None:break
                    time.sleep(.05)
                self.assertIn('Font selection ready: large, cached',contents)
                self.assertEqual(contents.count('Font atlas prepared:'),1,contents)
                self.assertFalse(win32gui.IsWindowVisible(hwnd))
                self.assertIsNone(process.poll())
            finally:
                process.stdin.close()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
                process.stdout.close()
    @unittest.skipUnless(os.name=='nt' and (ROOT/'native/HotkeyHost.exe').is_file(),'Windows native hook')
    def test_hook_process_uses_same_physical_dpi_coordinates_as_menu(self):
        import ctypes,win32gui,win32con
        user=ctypes.WinDLL('user32')
        user.SetThreadDpiAwarenessContext.argtypes=[ctypes.c_void_p]
        user.SetThreadDpiAwarenessContext.restype=ctypes.c_void_p
        previous=user.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
        hwnd=None
        try:
            hwnd=win32gui.CreateWindow('STATIC','Private DPI coordinate test',win32con.WS_POPUP,200,200,600,300,0,0,0,None)
            expected=list(win32gui.GetWindowRect(hwnd))
            result=subprocess.run([str(ROOT/'native/HotkeyHost.exe'),'--inspect-window',str(hwnd)],capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout),expected)
        finally:
            if hwnd: win32gui.DestroyWindow(hwnd)
            user.SetThreadDpiAwarenessContext(previous)
    @unittest.skipUnless(os.name=='nt' and (ROOT/'native/MenuHost.exe').is_file(),'Build Dear ImGui menu first')
    def test_cpp_imgui_search_keyboard_and_mouse_dispatch(self):
        result=subprocess.run([str(ROOT/'native/MenuHost.exe'),'--self-test'],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('original radial/focus/input/cancel matrix',result.stdout)
        self.assertIn('shape local draft',result.stdout)

    def test_iconified_popup_is_restored_before_showing(self):
        from backend.desktop import show_popup
        from unittest.mock import Mock
        from types import SimpleNamespace
        import win32con as c
        order=[]
        gui=SimpleNamespace(SetWindowLong=lambda *args:order.append('owner'),
            IsIconic=lambda hwnd:True,ShowWindow=lambda hwnd,mode:order.append(('restore',mode)),
            SetWindowPos=lambda *args:order.append('position'))
        show_popup(gui,2,1,(100,100,360,300))
        self.assertEqual(order,['owner',('restore',c.SW_RESTORE),'position'])
        gui.IsIconic=lambda hwnd:False
        gui.ShowWindow=Mock()
        show_popup(gui,2,1,(100,100,360,300))
        gui.ShowWindow.assert_not_called()
    def test_search_keyboard_navigation_and_empty_result(self):
        menu=MenuSelection()
        menu.filter('排序')
        self.assertEqual(menu.names,['moveToTop','moveToBottom'])
        menu.move(-1); self.assertEqual(menu.current,'moveToBottom')
        menu.move(1); self.assertEqual(menu.current,'moveToTop')
        menu.filter('CapsLock+w',DEFAULTS['shortcuts'])
        self.assertIsNone(menu.current)
        menu.filter('CapsLock+w',{**DEFAULTS['shortcuts'],'moveToTop':'capslock+w'})
        self.assertEqual(menu.current,'moveToTop')
        menu.filter('missing action'); menu.move(1)
        self.assertIsNone(menu.current)
        menu.filter('orange'); self.assertEqual(menu.current,'color')
        self.assertEqual(display_shortcut('capslock+a'),'CapsLock + A')

    def test_previous_settings_migrate_and_custom_dimensions_are_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'settings.json'
            old=copy.deepcopy(DEFAULTS); old.pop('right_click_open')
            old['menu_width'],old['menu_height']=420,360
            path.write_text(json.dumps(old))
            new=Settings(path).get()
            self.assertEqual((new['menu_width'],new['menu_height']),(360,300))
            self.assertFalse(new['right_click_open'])
            old['menu_width']=500
            path.write_text(json.dumps(old))
            self.assertEqual(Settings(path).get()['menu_width'],500)

    @unittest.skipUnless(os.name=='nt' and (ROOT/'native/HotkeyHost.exe').is_file(),'Build Windows hotkey host first')
    def test_independent_native_hotkey_state_machine(self):
        result=subprocess.run([str(ROOT/'native/HotkeyHost.exe'),'--self-test'],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('10000 CapsLock and Tab pairs',result.stdout)

    @unittest.skipUnless(os.name=='nt' and (ROOT/'native/HotkeyHost.exe').is_file(),'Build Windows hotkey host first')
    def test_native_hook_registration_configuration_and_clean_exit(self):
        from concurrent.futures import ThreadPoolExecutor
        process=subprocess.Popen([str(ROOT/'native/HotkeyHost.exe'),'--parent',str(os.getpid())],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,encoding='utf-8')
        try:
            process.stdin.write(json.dumps({'enabled':False,'right_click_open':False,'hwnd':0,
                'bindings':{name:list(chord(value)) for name,value in DEFAULTS['shortcuts'].items()}})+'\n')
            process.stdin.flush()
            with ThreadPoolExecutor(max_workers=1) as worker:
                message=json.loads(worker.submit(process.stdout.readline).result(timeout=5))
            self.assertEqual(message['type'],'ready')
            with ThreadPoolExecutor(max_workers=1) as worker:
                for _ in range(5):
                    event=json.loads(worker.submit(process.stdout.readline).result(timeout=5))
                    if event['type']=='configured':break
                    self.assertIn(event['type'],('caps.state','hook.health','activation.foreground'))
                else:self.fail('Native host did not acknowledge configuration')
            process.stdin.close()
            self.assertEqual(process.wait(5),0)
        finally:
            if process.poll() is None:process.terminate();process.wait(5)
            process.stdout.close()

    @unittest.skipUnless(os.name=='nt' and (ROOT/'native/HotkeyHost.exe').is_file(),'Build Windows hotkey host first')
    def test_native_host_crash_recovers_without_overlay_or_script_execution(self):
        import threading,time
        from backend.desktop import Desktop
        settings=copy.deepcopy(DEFAULTS); settings['enabled']=False
        desktop=Desktop('http://localhost',lambda action:self.fail('Disabled host dispatched an action'),settings)
        desktop.ready=threading.Event()
        desktop._spawn_native()
        desktop.thread=threading.Thread(target=desktop._native_events,daemon=True)
        desktop.thread.start()
        try:
            self.assertTrue(desktop.ready.wait(5))
            old=desktop.native
            old.terminate(); old.wait(5)
            deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                if desktop.native is not old and desktop.ready.is_set(): break
                time.sleep(.05)
            self.assertIsNot(desktop.native,old)
            self.assertIsNone(desktop.native.poll())
            self.assertTrue(desktop.ready.is_set())
            self.assertIn('"enabled": false',desktop.native_payload)
        finally:
            desktop.close()
        self.assertFalse(desktop.thread.is_alive())
