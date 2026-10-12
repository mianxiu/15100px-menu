import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from backend.desktop import Desktop
from backend.native_commands import Input, open_new_dialog
from backend.main import Application


class HomeMenuTests(unittest.TestCase):
    def user(self, accepted=4):
        return SimpleNamespace(GetAsyncKeyState=Mock(return_value=0),SendInput=Mock(return_value=accepted))

    def test_atomic_native_shortcut_and_key_up_pairs(self):
        user=self.user()
        result=open_new_dialog(SimpleNamespace(GetForegroundWindow=lambda:10),10,user)
        count,sequence,size=user.SendInput.call_args.args
        self.assertEqual(count,4)
        self.assertEqual([(x.payload.keyboard.vk,x.payload.keyboard.flags) for x in sequence],[(17,0),(78,0),(78,2),(17,2)])
        self.assertEqual(result['channel'],'photoshop-native-shortcut')
        import ctypes
        self.assertEqual(size,ctypes.sizeof(Input))
        self.assertEqual(size,40 if ctypes.sizeof(ctypes.c_void_p)==8 else 28)

    def test_foreign_focus_and_held_modifiers_never_inject(self):
        user=self.user()
        with self.assertRaisesRegex(RuntimeError,'焦点'):
            open_new_dialog(SimpleNamespace(GetForegroundWindow=lambda:20),10,user)
        user.SendInput.assert_not_called()
        user.GetAsyncKeyState.return_value=0x8000
        with self.assertRaisesRegex(RuntimeError,'松开'):
            open_new_dialog(SimpleNamespace(GetForegroundWindow=lambda:10),10,user)
        user.SendInput.assert_not_called()

    def test_partial_injection_releases_keys_without_repeating_new(self):
        user=self.user(2)
        with self.assertRaisesRegex(RuntimeError,'未完整'):
            open_new_dialog(SimpleNamespace(GetForegroundWindow=lambda:10),10,user)
        self.assertEqual(user.SendInput.call_count,2)
        self.assertEqual([(x.payload.keyboard.vk,x.payload.keyboard.flags) for x in user.SendInput.call_args.args[1]],[(78,2),(17,2)])

    def test_home_is_rechecked_before_hiding_or_injecting(self):
        desktop=Desktop('http://localhost',Mock())
        desktop.target=10;desktop.gui=Mock();desktop.require_action_focus=Mock()
        desktop.panel_context=SimpleNamespace(home_visible=Mock(return_value=False));desktop.hide=Mock()
        with patch('backend.photoshop_windows.workspace_root',return_value=10),patch('backend.native_commands.open_new_dialog') as inject:
            with self.assertRaisesRegex(RuntimeError,'离开首页'):desktop.new_document()
            desktop.hide.assert_not_called();inject.assert_not_called()
            desktop.panel_context.home_visible.return_value=True
            desktop.new_document()
            desktop.hide.assert_called_once();inject.assert_called_once_with(desktop.gui,10)


class HomeDispatchTests(unittest.IsolatedAsyncioTestCase):
    def application(self):
        return SimpleNamespace(desktop=SimpleNamespace(menu_epoch=3,new_document=Mock(return_value={'message':'requested'})),
             bridge=SimpleNamespace(busy=False),photoshop_launcher=SimpleNamespace(active=False),
             operation_lock=asyncio.Lock(),panel_lock=asyncio.Lock())

    async def test_busy_and_stale_requests_do_not_open_dialog_or_queue(self):
        app=self.application();app.bridge.busy=True
        with self.assertRaisesRegex(RuntimeError,'未接受'):await Application.dispatch(app,'document.new',{})
        app.desktop.new_document.assert_not_called()
        app.bridge.busy=False
        result=await Application.dispatch(app,'document.new',{'menu_epoch':2})
        self.assertIn('旧菜单',result['message']);app.desktop.new_document.assert_not_called()
        result=await Application.dispatch(app,'document.new',{'menu_epoch':3})
        self.assertEqual(result['message'],'requested');app.desktop.new_document.assert_called_once()
