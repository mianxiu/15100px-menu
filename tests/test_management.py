import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import hashlib
from types import SimpleNamespace

from backend.settings import DEFAULTS, Settings
from backend.plugins import Plugins, FILES
from backend.desktop import Desktop, KeyState, panel_bounds, process_parent

ROOT = Path(__file__).resolve().parents[1]


def package(number='1.1.0', corrupt=False):
    data = json.loads((ROOT/'jsx/manifest.json').read_text(encoding='utf-8'))
    data['version'] = number
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        archive.writestr('manifest.json', json.dumps(data))
        for name in FILES:
            archive.writestr(name, b'bad checksum' if corrupt else (ROOT/'jsx'/name).read_bytes())
    return stream.getvalue()


class ManagementTests(unittest.TestCase):
    def test_old_right_click_setting_cannot_reenable_photoshop_interception(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'settings.json'
            data = copy.deepcopy(DEFAULTS)
            data['right_click_open'] = True
            path.write_text(json.dumps(data), encoding='utf-8')
            settings = Settings(path)
            self.assertFalse(settings.get()['right_click_open'])
            self.assertFalse(settings.save(data)['right_click_open'])

    def test_imgui_secondary_window_remains_in_menu_scope(self):
        desktop=Desktop('http://localhost',lambda action:None,copy.deepcopy(DEFAULTS))
        desktop.hwnd,desktop.target,desktop.visible=20,10,True
        desktop.gui=SimpleNamespace(GetForegroundWindow=lambda:21,IsWindow=lambda hwnd:True,
            IsIconic=lambda hwnd:False,GetAncestor=lambda hwnd,mode:hwnd,IsWindowVisible=lambda hwnd:True,IsWindowEnabled=lambda hwnd:True,GetClassName=lambda hwnd:'Photoshop' if hwnd==10 else 'ImGui')
        with patch('win32process.GetWindowThreadProcessId',side_effect=lambda hwnd:(0,300 if hwnd in (20,21) else 400)):
            self.assertTrue(desktop._scope())
            self.assertFalse(desktop._is_menu_window(22))
            desktop.visible=False
            self.assertFalse(desktop._scope())
    def test_default_capslock_toggle_and_combination(self):
        from backend.settings import chord
        self.assertEqual(chord(DEFAULTS['shortcuts']['toggle']), (20,))
        state = KeyState()
        self.assertEqual(state.event(20,True,True),(True,'hold_begin'))
        self.assertEqual(state.event(20,True,True),(True,None))
        self.assertEqual(state.event(20,False,True),(True,'hold_release'))
        state.event(20,True,True)
        self.assertEqual(state.event(65,True,True),(True,'select'))
        state.event(65,False,True)
        self.assertEqual(state.event(20,False,True),(True,'hold_cancel'))
        self.assertEqual(state.event(20,True,False),(False,None))
        self.assertEqual(state.event(20,False,False),(False,None))
        self.assertEqual(state.event(9,True,True),(False,None))
        self.assertEqual(state.event(9,False,True),(False,None))

    def test_legacy_stock_tab_prefix_migrates_without_overwriting_custom_bindings(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'settings.json'
            data=copy.deepcopy(DEFAULTS)
            data['shortcuts'].update(color='tab+a',moveToTop='tab+w',moveToBottom='tab+s')
            path.write_text(json.dumps(data),encoding='utf-8')
            self.assertEqual(Settings(path).get()['shortcuts']['color'],'')
            data['shortcuts']['moveToTop']='f8'
            path.write_text(json.dumps(data),encoding='utf-8')
            self.assertEqual(Settings(path).get()['shortcuts']['moveToTop'],'f8')

    @unittest.skipUnless(os.name=='nt','Windows process test')
    def test_windows_process_parent_matches_os(self):
        self.assertEqual(process_parent(os.getpid()),os.getppid())

    def test_overlay_accepts_owned_launcher_child_and_rejects_other_process(self):
        from unittest.mock import Mock
        desktop = Desktop('http://localhost',lambda action: None)
        desktop.process = SimpleNamespace(pid=500,poll=lambda: None)
        desktop.gui = SimpleNamespace(IsWindow=lambda hwnd:True,ShowWindow=Mock())
        desktop.icons = SimpleNamespace(apply=Mock())
        with patch('backend.desktop.process_parent',return_value=500), patch('win32process.GetWindowThreadProcessId',return_value=(0,501)):
            desktop.attach(100,501,desktop.token)
            self.assertEqual(desktop.hwnd,100)
            self.assertFalse(desktop.visible)
        with patch('backend.desktop.process_parent',return_value=999):
            with self.assertRaises(ValueError):
                desktop.attach(100,501,desktop.token)

    def test_settings_persist_and_invalid_save_keeps_previous(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'settings.json'
            settings = Settings(path)
            data = settings.get()
            data['menu_width'] = 800
            data['shortcuts']['toggle'] = 'f8'
            settings.save(data)
            self.assertEqual(Settings(path).get(), data)
            invalid = copy.deepcopy(data)
            invalid['shortcuts']['color'] = 'f8'
            with self.assertRaises(ValueError):
                settings.save(invalid)
            self.assertEqual(Settings(path).get(), data)

    def test_plugin_install_rollback_uninstall_and_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = Plugins(directory, ROOT/'jsx')
            with self.assertRaises(ValueError):
                manager.prepare(package(corrupt=True))
            preview = manager.prepare(package())
            manager.install(preview['token'])
            manager = Plugins(directory, ROOT/'jsx')
            self.assertEqual(manager.status()['active']['version'], '1.1.0')
            manager.restore()
            self.assertEqual(manager.status()['active']['version'], '1.0.0')
            manager.install(manager.prepare(package('1.2.0'))['token'])
            manager.restore(builtin=True)
            self.assertFalse(manager.status()['installed'])
            self.assertEqual(set(zipfile.ZipFile(io.BytesIO(manager.export())).namelist()), {'manifest.json',*FILES})

    def test_archive_paths_and_same_version_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = Plugins(directory, ROOT/'jsx')
            with self.assertRaises(ValueError):
                manager.prepare(package('1.0.0'))
            stream = io.BytesIO()
            with zipfile.ZipFile(stream,'w') as archive:
                archive.writestr('../outside.jsx','bad')
            with self.assertRaises(ValueError):
                manager.prepare(stream.getvalue())
            self.assertFalse((Path(directory).parent/'outside.jsx').exists())

    def test_custom_shortcuts_and_modifier_aliases(self):
        shortcuts = copy.deepcopy(DEFAULTS['shortcuts'])
        shortcuts['toggle'] = 'f8'
        shortcuts['color'] = 'ctrl+a'
        keys = KeyState(shortcuts)
        self.assertEqual(keys.event(119,True,True),(True,'hold_begin'))
        self.assertEqual(keys.event(119,False,True),(True,'hold_release'))
        keys.event(162,True,True)
        self.assertEqual(keys.event(65,True,True),(True,'color'))
        self.assertEqual(keys.event(65,False,True),(True,None))

    def test_escape_remains_available_to_ps_when_menu_hidden(self):
        shortcuts = copy.deepcopy(DEFAULTS['shortcuts'])
        shortcuts.pop('hide')
        keys = KeyState(shortcuts)
        self.assertEqual(keys.event(27,True,True),(False,None))
        self.assertEqual(keys.event(27,False,True),(False,None))

    def test_open_enforces_mouse_bounds_and_applies_clamped_position(self):
        from unittest.mock import Mock
        desktop = Desktop('http://localhost',lambda action:None,copy.deepcopy(DEFAULTS))
        desktop.hwnd = 2
        desktop.gui = SimpleNamespace(GetForegroundWindow=lambda:1, IsWindow=lambda hwnd:True,
            IsIconic=lambda hwnd:False, GetAncestor=lambda hwnd,mode:hwnd,IsWindowVisible=lambda hwnd:True,IsWindowEnabled=lambda hwnd:True,WindowFromPoint=lambda point:1, GetClassName=lambda hwnd:'Photoshop' if hwnd==1 else 'Other',
            GetWindowRect=lambda hwnd:(100,100,900,900),SetWindowLong=Mock(),SetWindowPos=Mock(),SetForegroundWindow=Mock(),SendMessage=Mock())
        with patch('win32api.GetCursorPos',return_value=(50,50)):
            with self.assertRaisesRegex(RuntimeError,'鼠标'):
                desktop._open()
        desktop.gui.SetWindowPos.assert_not_called()
        with patch('win32api.GetCursorPos',return_value=(850,850)),patch('win32api.GetMonitorInfo',return_value={'Work':(0,0,1920,1080)}),patch('win32api.MonitorFromPoint',return_value=1):
            desktop._open()
        self.assertTrue(desktop.visible)
        args = desktop.gui.SetWindowPos.call_args.args
        self.assertEqual(args[2:6],(540,600,360,300))

    def test_bounds_stay_inside_photoshop_and_work_area(self):
        self.assertEqual(panel_bounds((100,100,900,900),(0,0,1920,1080),(850,850),750,600),(150,300,750,600))
        self.assertEqual(panel_bounds((-400,0,500,400),(0,0,1920,1080),(400,300),750,600),(0,0,500,400))

    def test_scope_requires_valid_target_and_menu_visible(self):
        desktop = Desktop('http://localhost',lambda action: None,copy.deepcopy(DEFAULTS))
        class Gui:
            foreground = 1
            minimized = False
            def GetForegroundWindow(self): return self.foreground
            def IsWindow(self,hwnd): return hwnd in (1,2,3)
            def IsIconic(self,hwnd): return self.minimized and hwnd==1
            def GetAncestor(self,hwnd,mode): return hwnd
            def IsWindowVisible(self,hwnd): return True
            def IsWindowEnabled(self,hwnd): return True
            def GetClassName(self,hwnd): return 'Photoshop' if hwnd==1 else 'Other'
        desktop.gui = Gui()
        desktop.hwnd = 2
        self.assertTrue(desktop._scope())
        desktop.gui.foreground = 2
        self.assertFalse(desktop._scope())
        desktop.visible = True
        self.assertTrue(desktop._scope())
        desktop.gui.minimized = True
        self.assertFalse(desktop._scope())
        desktop.gui.foreground = 3
        with self.assertRaises(RuntimeError):
            desktop._open()  # Refuse before window creation or positioning.

    def test_outside_click_dismisses_without_leaking_to_photoshop(self):
        events = []
        desktop = Desktop('http://localhost', events.append, copy.deepcopy(DEFAULTS))
        desktop.hwnd, desktop.target, desktop.visible = 2, 1, True
        desktop._is_menu_window = lambda hwnd: hwnd == 2
        desktop.gui = SimpleNamespace(GetWindowRect=lambda hwnd:(100,100,500,500),
            GetForegroundWindow=lambda:2, IsWindow=lambda hwnd:True, IsIconic=lambda hwnd:False,
            GetAncestor=lambda hwnd,mode:hwnd,IsWindowVisible=lambda hwnd:True,IsWindowEnabled=lambda hwnd:True,
            GetClassName=lambda hwnd:'Photoshop' if hwnd==1 else 'Other')
        self.assertFalse(desktop.outside_click((200,200)))
        self.assertTrue(desktop.visible)
        self.assertTrue(desktop.outside_click((50,50)))
        self.assertFalse(desktop.visible)
        self.assertEqual(events,['dismiss'])
        desktop.visible = True
        desktop.gui.GetForegroundWindow = lambda:3
        self.assertFalse(desktop.outside_click((50,50)))
        self.assertFalse(desktop.visible)

    def test_dismiss_does_not_steal_focus_from_another_application(self):
        from unittest.mock import Mock
        desktop = Desktop('http://localhost',lambda action:None,copy.deepcopy(DEFAULTS))
        desktop.hwnd, desktop.target, desktop.visible = 2, 1, True
        desktop._is_menu_window = lambda hwnd: hwnd == 2
        desktop.gui = SimpleNamespace(GetForegroundWindow=lambda:3, IsWindow=lambda hwnd:True,
            IsIconic=lambda hwnd:False, GetAncestor=lambda hwnd,mode:hwnd,IsWindowVisible=lambda hwnd:True,IsWindowEnabled=lambda hwnd:True,WindowFromPoint=lambda point:1, GetClassName=lambda hwnd:'Photoshop',
            ShowWindow=Mock(),SetForegroundWindow=Mock())
        desktop.hide()
        desktop.gui.SetForegroundWindow.assert_not_called()
        desktop.gui.ShowWindow.assert_called_once_with(2,0)


class FeedTests(unittest.IsolatedAsyncioTestCase):
    async def test_feed_download_checks_checksum_and_prepares_only(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = Plugins(directory,ROOT/'jsx')
            payload = package()
            feed = {'id':'photoshop-menu-actions','version':'1.1.0','url':'https://example.test/actions.zip',
                    'sha256':hashlib.sha256(payload).hexdigest()}
            class Client:
                responses = [json.dumps(feed).encode(),payload]
                async def fetch(self,request): return SimpleNamespace(body=self.responses.pop(0))
                def close(self): pass
            with patch('backend.plugins.AsyncHTTPClient',return_value=Client()):
                self.assertTrue((await manager.check('https://example.test/update.json'))['available'])
                preview = await manager.download()
            self.assertEqual(preview['manifest']['version'],'1.1.0')
            self.assertEqual(manager.status()['active']['version'],'1.0.0')
            manager.update['sha256'] = '0'*64
            client = Client()
            client.responses = [payload]
            with patch('backend.plugins.AsyncHTTPClient',return_value=client):
                with self.assertRaisesRegex(ValueError,'SHA256'):
                    await manager.download()
