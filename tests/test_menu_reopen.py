import asyncio
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from backend.main import Application
from backend.desktop import Desktop, pie_bounds
from backend.photoshop_bridge import PhotoshopBridge


class MenuFocusTests(unittest.TestCase):
    def test_pie_is_centered_on_invocation_and_clamped_to_work_area(self):
        self.assertEqual(pie_bounds((0,0,1920,1080),(0,0,1920,1040),(960,520),1), (650,300,620,440))
        self.assertEqual(pie_bounds((0,0,1920,1080),(0,0,1920,1040),(1910,1030),1), (1300,600,620,440))
        self.assertEqual(pie_bounds((-1920,0,0,1080),(-1920,0,0,1040),(-960,520),1.5), (-1425,190,930,660))

    def test_hold_begin_requests_radial_layout_before_opening(self):
        desktop = Desktop('http://localhost', lambda action:None)
        desktop.visible = False
        desktop.open = Mock(return_value={'message':'opened'})
        desktop.hold_begin()
        desktop.open.assert_called_once_with(hold=True)
        self.assertTrue(desktop.hold_active)

    def test_hold_release_is_once_and_hidden_menu_does_not_execute(self):
        desktop = Desktop('http://localhost', lambda action:None)
        desktop.hwnd, desktop.visible, desktop.hold_active = 2, True, True
        desktop._scope = lambda:True
        desktop.gui = SimpleNamespace(SendMessage=Mock())
        desktop.hold_release()
        desktop.hold_release()
        desktop.gui.SendMessage.assert_called_once_with(2, 0x800e, 0, 0)
        desktop.gui.SendMessage.reset_mock()
        desktop.hold_active, desktop.visible = True, False
        desktop.hold_release()
        desktop.gui.SendMessage.assert_not_called()

    def test_short_tap_pins_in_place_and_ignores_later_release(self):
        desktop = Desktop('http://localhost', lambda action:None)
        desktop.hwnd, desktop.visible, desktop.hold_active = 2, True, True
        desktop._scope = lambda:True
        def opened(**kwargs):
            desktop.visible = True
            return {'message':'opened'}
        desktop.open = Mock(side_effect=opened)
        desktop.gui = SimpleNamespace(SendMessage=Mock())
        desktop.hold_pin()
        desktop.open.assert_not_called()
        self.assertFalse(desktop.hold_active)
        desktop.gui.SendMessage.assert_called_once_with(2, 0x8010, 1, 0)
        desktop.hold_release()
        self.assertEqual(desktop.gui.SendMessage.call_count, 1)

    def test_hold_release_after_focus_change_cancels_without_execution(self):
        desktop = Desktop('http://localhost', lambda action:None)
        desktop.hwnd, desktop.visible, desktop.hold_active = 2, True, True
        desktop._scope = lambda:False
        desktop.hide = Mock(return_value={'message':'closed'})
        desktop.gui = SimpleNamespace(SendMessage=Mock())
        desktop.hold_release()
        desktop.hide.assert_called_once_with(restore=False)
        desktop.gui.SendMessage.assert_not_called()

    def test_capslock_closes_input_paused_menu(self):
        desktop = Desktop('http://localhost', lambda action:None)
        desktop.visible = True
        desktop._scope = lambda:True
        desktop.require_action_focus = Mock(side_effect=RuntimeError('input paused'))
        desktop.hide = Mock(return_value={'message':'closed'})
        self.assertEqual(desktop.toggle()['message'], 'closed')
        desktop.require_action_focus.assert_not_called()

    def test_hide_restores_ps_even_if_showwindow_changes_foreground(self):
        for initial in (2, 4):  # Main menu and floating ImGui submenu.
            desktop = Desktop('http://localhost', lambda action:None)
            desktop.hwnd, desktop.target, desktop.visible = 2, 1, True
            foreground = [initial]
            desktop._is_menu_window = lambda hwnd: hwnd in (2, 4)
            desktop._is_photoshop = lambda hwnd: hwnd == 1
            desktop.gui = SimpleNamespace(
                GetForegroundWindow=lambda:foreground[0], IsWindow=lambda hwnd:True,
                ShowWindow=lambda *args:foreground.__setitem__(0, 3),
                SetForegroundWindow=lambda hwnd:foreground.__setitem__(0, hwnd))
            desktop.hide()
            self.assertEqual(foreground[0], 1)
            self.assertFalse(desktop.visible)


class MenuReopenTests(unittest.IsolatedAsyncioTestCase):
    async def test_old_hide_waiting_on_panel_lock_does_not_close_new_pin(self):
        with tempfile.TemporaryDirectory() as folder:
            app = Application(15190, bridge=SimpleNamespace(busy=False), runtime=folder)
            app.desktop = SimpleNamespace(menu_epoch=1, hide=Mock())
            await app.panel_lock.acquire()
            stale = asyncio.create_task(app.dispatch('panel.hide', {'menu_epoch':1}))
            await asyncio.sleep(0)
            app.desktop.menu_epoch = 2
            app.panel_lock.release()
            await stale
            app.desktop.hide.assert_not_called()

    async def test_fast_reopen_survives_previous_operation_completion(self):
        with tempfile.TemporaryDirectory() as folder:
            started, release = asyncio.Event(), asyncio.Event()
            class Bridge:
                busy = False
                async def execute(self, name):
                    self.busy = True
                    started.set()
                    await release.wait()
                    self.busy = False
                    return {'message':'done'}
            desktop = SimpleNamespace(visible=True, require_action_focus=lambda:None)
            def hide():
                desktop.visible = False
            desktop.hide = Mock(side_effect=hide)
            app = Application(15190, bridge=Bridge(), runtime=folder)
            app.desktop = desktop
            async def broadcast(event):
                pass
            app.broadcast = broadcast
            for _ in range(100):
                desktop.visible = True
                started.clear(); release.clear()
                operation = asyncio.create_task(app.dispatch('action.execute', {'name':'color'}))
                await asyncio.wait_for(started.wait(), 2)
                self.assertFalse(desktop.visible, 'Old menu must close before COM starts')
                desktop.visible = True  # A fresh CapsLock menu during COM.
                release.set()
                await operation
                self.assertTrue(desktop.visible, 'Completion must not close the newly opened menu')
            self.assertEqual(desktop.hide.call_count, 100)
            app.control.close()

    async def test_busy_status_preserves_connection_without_waiting_for_com(self):
        bridge = PhotoshopBridge()
        try:
            bridge._status = lambda:{'connected':True, 'document':'test.psd', 'message':'connected'}
            await bridge.status()
            bridge.busy = True
            bridge._status = Mock(side_effect=AssertionError('Busy status must not query COM'))
            status = await bridge.status()
            self.assertTrue(status['connected'])
            self.assertEqual(status['document'], 'test.psd')
            self.assertTrue(status['busy'])
            bridge._status.assert_not_called()
        finally:
            bridge.busy = False
            await bridge.close()
