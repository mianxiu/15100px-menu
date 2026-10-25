import ast
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from backend.input_method import ImePolicy,ImeContext,InputMethod
from tests import test_input_language as legacy_tests


def sample(state='non-input',opened=1):
    return {'root':1,'identity':[1,2,'created',3],'focus':10,'layout':0x8040804,
            'ime':20,'ime_open':opened,'state':state}


class ImePolicyTests(unittest.TestCase):
    def test_disable_readback_then_input_restore_without_layout_change(self):
        p=ImePolicy();request=p.step(sample(),7,0)
        self.assertEqual(request['wanted'],0);self.assertIsNone(p.owned)
        self.assertIsNone(p.step(sample(opened=0),7,.1));self.assertIsNotNone(p.owned)
        request=p.step(sample('input',0),None,.2);self.assertEqual(request['wanted'],1)
        p.step(sample('input'),None,.3);self.assertIsNone(p.owned)
        self.assertEqual((p.confirmed_disables,p.confirmed_restores),(1,1))
        self.assertIsNotNone(p.step(sample(),7,.4))

    def test_unknown_input_outside_and_already_closed_do_not_disable(self):
        for s in (sample('unknown'),sample('input'),sample('outside'),sample(opened=0),{**sample(),'ime_open':None}):
            self.assertIsNone(ImePolicy().step(s,7,0))

    def test_unconfirmed_request_is_retained_without_reissue(self):
        p=ImePolicy();request=p.step(sample(),7,0)
        for tick in (1,2,100):self.assertIsNone(p.step(sample(),8,tick))
        self.assertEqual(p.pending,request);self.assertEqual(p.state,'request-not-confirmed')

    def test_unknown_restores_once_and_does_not_autonomously_toggle(self):
        p=ImePolicy();p.step(sample(),7,0);p.step(sample(opened=0),7,.1)
        self.assertEqual(p.step(sample('unknown',0),None,.2)['wanted'],1)
        p.step(sample(),7,.3)
        self.assertIsNone(p.step(sample(),7,2));self.assertIsNotNone(p.step(sample(),8,3))

    def test_background_restore_targets_the_owned_ps_context_only(self):
        p=ImePolicy();p.step(sample(),7,0);p.step(sample(opened=0),7,.1)
        for field,value in (('identity',[4,5,'other',6]),('ime',99),('layout',0x4090409)):
            self.assertIsNone(p.step({**sample('outside',0),field:value},None,.2))
        self.assertEqual(p.step(sample('outside',0),None,.3)['ime'],20)

    def test_manual_open_is_respected_until_a_real_input_cycle(self):
        p=ImePolicy();p.step(sample(),7,0);p.step(sample(opened=0),7,.1)
        p.step(sample(),8,.2);self.assertIsNone(p.owned)
        self.assertIsNone(p.step(sample(),9,.3))
        p.step(sample('input'),None,.4)
        self.assertIsNotNone(p.step(sample(),10,.5))

    def test_ps_reopening_ime_for_input_is_not_a_manual_override(self):
        p=ImePolicy();p.step(sample(),7,0);p.step(sample(opened=0),7,.1)
        self.assertIsNone(p.step(sample('input'),None,.2));self.assertIsNone(p.owned)
        self.assertIsNotNone(p.step(sample(),7,.3))

    def test_native_input_restore_does_not_permanently_disable_eng_as_manual_change(self):
        p=ImePolicy();p.step(sample(),7,0);p.step(sample(opened=0),7,.1)
        request=p.step({**sample(),'native_restored':True},8,.2)
        self.assertEqual(request['wanted'],0);self.assertIsNone(p.manual)
        self.assertEqual(p.confirmed_restores,1)


class ImeJournalTests(unittest.TestCase):
    def test_native_journal_binds_the_control_nonce_and_preserves_unknown(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'input-method-owned.json';c=InputMethod(SimpleNamespace());c.context_schema=2
            c.policy.step({**sample(),'context_nonce':123},7,0);path.write_text(json.dumps(c.saved()),'utf-8')
            other=InputMethod(SimpleNamespace());other.load(path)
            self.assertEqual(other.context_schema,2);self.assertIsNotNone(other.policy.pending)
            self.assertIsNone(other.policy.step({**sample(opened=0),'context_nonce':456},8,3))
            self.assertIsNotNone(other.policy.pending)

    def test_unknown_journal_roundtrip_and_wrong_namespace_rejection(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'input-method-owned.json';c=InputMethod(SimpleNamespace(runtime=Path(folder)))
            c.policy.step(sample(),7,0);p.write_text(json.dumps(c.saved()),'utf-8')
            restored=InputMethod(c.desktop);restored.load(p)
            self.assertEqual(restored.policy.pending['identity'],sample()['identity'])
            self.assertIsNotNone(restored.policy.pending);self.assertIsNone(restored.policy.owned)
            p.write_text(json.dumps({'owned':None,'pending':None}),'utf-8')
            with self.assertRaises(ValueError):InputMethod(c.desktop).load(p)

    def test_untrusted_fields_never_enter_the_restore_path(self):
        c=InputMethod(SimpleNamespace());c.policy.step(sample(),7,0);valid=c.saved()
        for key,value in (('wanted',2),('wanted',False),('original',0),('disable',False),('time',float('nan')),('ime',0),('identity',[1,0,'',3])):
            with tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'input-method-owned.json';bad=json.loads(json.dumps(valid));bad['pending'][key]=value;path.write_text(json.dumps(bad),'utf-8')
                target=InputMethod(SimpleNamespace())
                with self.assertRaises(ValueError):target.load(path)
                self.assertIsNone(target.policy.owned);self.assertIsNone(target.policy.pending)

    def test_confirmed_exit_archives_but_unknown_pending_is_never_retired(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'input-method-owned.json';c=InputMethod(SimpleNamespace());c.policy.step(sample(),7,0)
            c.retire(path,'original-process-exited');self.assertIsNotNone(c.policy.pending);self.assertFalse(path.exists())
            c.policy.step(sample(opened=0),7,.1);owned=dict(c.policy.owned);c.retire(path,'original-process-exited')
            self.assertEqual(json.loads(path.read_text()),{'schema':1,'owned':None,'pending':None})
            archive=list(Path(folder).glob('input-method-retired-*.json'))
            self.assertEqual(json.loads(archive[0].read_text())['owned'],owned)
            self.assertFalse(json.loads(archive[0].read_text())['restore_sent'])


class ImeTransportTests(unittest.TestCase):
    def test_attached_menu_focus_reads_only_original_ps_ime_context(self):
        context=ImeContext.__new__(ImeContext)
        def gui_info(thread,pointer):pointer._obj.focus=99;return 1
        context.user=SimpleNamespace(GetGUIThreadInfo=gui_info,GetKeyboardLayout=lambda _:0x8040804)
        context.read=Mock(side_effect=lambda value:value)
        handle=Mock()
        with patch('win32gui.IsWindow',return_value=True),patch('win32api.OpenProcess',return_value=handle),patch('win32process.GetProcessTimes',return_value={'CreationTime':'created'}),patch('win32process.GetWindowThreadProcessId',side_effect=lambda hwnd:[8,9] if hwnd==99 else [3,2]):
            value=context.observe_owned(sample())
            self.assertEqual(value['focus'],10);self.assertEqual(value['identity'],sample()['identity'])
            self.assertEqual(value['state'],'outside');handle.Close.assert_called_once()

    def test_only_ime_control_messages_are_used(self):
        context=ImeContext.__new__(ImeContext);context.imm=SimpleNamespace(ImmGetDefaultIMEWnd=Mock(return_value=20))
        with patch('win32gui.IsWindow',return_value=True),patch('win32gui.GetClassName',return_value='IME'),patch('win32process.GetWindowThreadProcessId',return_value=[3,2]),patch('win32gui.SendMessageTimeout',return_value=(1,1)) as message:
            self.assertEqual(context.read(sample())['ime_open'],1)
            context.send({'ime':20,'wanted':0});context.send({'ime':20,'wanted':1})
            self.assertEqual([c.args[1:4] for c in message.call_args_list],[(0x283,5,0),(0x283,6,0),(0x283,6,1)])
        with patch('win32gui.IsWindow',return_value=True),patch('win32gui.GetClassName',return_value='IME'),patch('win32process.GetWindowThreadProcessId',return_value=[3,99]),patch('win32gui.SendMessageTimeout') as message:
            self.assertIsNone(context.read(sample())['ime']);message.assert_not_called()

    def test_production_controller_cannot_send_a_new_keyboard_layout_switch(self):
        from backend.desktop import Desktop
        import inspect
        self.assertIn('InputMethod(self)',inspect.getsource(Desktop.start))
        tree=ast.parse(inspect.getsource(__import__('backend.input_method',fromlist=['x'])))
        calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='PostMessageW']
        self.assertEqual(len(calls),1)
        self.assertIn("if request['switch']:raise",inspect.getsource(InputMethod.legacy_step))


class ImeWorkerTests(unittest.TestCase):
    def start(self,acknowledge=True,legacy=None,tool=None,reconcile=None):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.desktop=SimpleNamespace(runtime=Path(temp.name),visible=False,settings={'enabled':True},stop=threading.Event(),input_language_busy=lambda:False,input_language_tool=lambda:{'classID':'moveTool','isModal':False})
        if tool is not None:self.desktop.input_language_tool=tool
        if reconcile is not None:self.desktop.input_language_reconcile=reconcile
        self.c=InputMethod(self.desktop);self.opened=1;self.kind=50033;self.outside=False;self.posts=[]
        if legacy is not None:(self.desktop.runtime/'input-language-owned.json').write_text(json.dumps(legacy),'utf-8')
        def observe():
            if self.outside:return {'state':'outside'}
            return {**sample(), 'state':'unknown','workspace':True,'pid':2,'class':'PSViewC','accessibility':legacy_tests.FocusAccessibilityTests().row(self.kind)}
        self.c.sample=observe
        def read(value):return {**value,'ime':20,'ime_open':self.opened}
        def send(value):
            self.posts.append(value['wanted'])
            if acknowledge:self.opened=value['wanted']
        def layouts(count,values):values[0]=0x8040804;values[1]=0x4090409;return 2
        self.user=SimpleNamespace(GetKeyboardLayout=Mock(return_value=0x8040804),GetKeyboardLayoutList=Mock(side_effect=layouts),PostMessageW=Mock(),GetAsyncKeyState=Mock(return_value=0))
        for p in (patch('backend.input_method.ctypes.WinDLL',return_value=self.user),patch('backend.input_method.ImeContext',return_value=SimpleNamespace(read=read,send=send,observe_owned=lambda _:read({**sample('outside'),'ime_open':self.opened}))),patch('backend.input_method.NativeImeContext',return_value=SimpleNamespace(read=lambda value:{**read(value),'context_nonce':123},send=send,observe_owned=lambda _:{**read({**sample('outside'),'ime_open':self.opened}),'context_nonce':123})),patch('backend.input_method.FocusAccessibility',return_value=object()),patch('backend.input_method.process_exited',return_value=False)):
            p.start();self.addCleanup(p.stop)
        self.c.thread.start()
        def stop():self.desktop.stop.set();self.c.wake.set();self.c.thread.join(2);self.assertFalse(self.c.thread.is_alive())
        self.addCleanup(stop)

    def wait(self,predicate):
        end=time.monotonic()+3
        while not predicate():self.assertLess(time.monotonic(),end,self.c.report);time.sleep(.005)

    def test_non_input_input_outside_and_shutdown_restore_without_changing_hkl(self):
        self.start();self.wait(lambda:self.c.policy.confirmed_disables==1)
        self.kind=50004;self.c.activity();self.wait(lambda:self.c.policy.confirmed_restores==1)
        self.kind=50033;self.c.activity();self.wait(lambda:self.c.policy.confirmed_disables==2)
        self.outside=True;self.c.activity();self.wait(lambda:self.c.policy.confirmed_restores==2)
        self.assertEqual(self.posts,[0,1,0,1]);self.assertEqual(self.c.report['layout_requests'],0);self.user.PostMessageW.assert_not_called()
        self.outside=False;self.c.activity();self.wait(lambda:self.c.policy.confirmed_disables==3)
        self.desktop.stop.set();self.c.wake.set();self.c.thread.join(2)
        self.assertEqual(self.posts[-2:],[0,1]);self.assertIsNone(self.c.policy.pending)

    def test_unknown_close_is_not_retried_even_during_shutdown(self):
        self.start(acknowledge=False);self.wait(lambda:len(self.posts)==1)
        self.c.policy.pending['time']=time.monotonic()-2;self.c.activity()
        self.wait(lambda:self.c.policy.state=='request-not-confirmed')
        self.desktop.stop.set();self.c.wake.set();self.c.thread.join(2)
        self.assertEqual(self.posts,[0]);self.assertIsNotNone(self.c.policy.pending)

    def test_paused_or_disabled_product_restores_its_ime_ownership(self):
        self.start();self.wait(lambda:self.c.policy.confirmed_disables==1)
        self.desktop.settings['enabled']=False;self.c.activity();self.wait(lambda:self.c.policy.confirmed_restores==1)
        self.assertEqual(self.posts,[0,1])

    def test_legacy_unknown_layout_request_blocks_new_ime_changes_without_reissue(self):
        owner=legacy_tests.ExitedLanguageOwnerTests().owner();owner['identity'][2]='old-process'
        self.start(legacy={'owned':owner,'pending':{**owner,'switch':False}})
        self.wait(lambda:self.c.report.get('legacy_pending'))
        self.assertEqual(self.posts,[]);self.user.PostMessageW.assert_not_called()
        self.desktop.stop.set();self.c.wake.set();self.c.thread.join(2)
        saved=json.loads((self.desktop.runtime/'input-language-owned.json').read_text())
        self.assertEqual(saved['pending']['identity'],owner['identity']);self.assertEqual(self.posts,[])

    def test_known_read_settlement_can_reobserve_without_a_first_keystroke(self):
        value={'classID':'moveTool','isModal':False};provider=Mock(side_effect=[None,value,value])
        self.start(tool=provider,reconcile=lambda:True)
        self.wait(lambda:self.c.policy.confirmed_disables==1)
        self.assertEqual(provider.call_count,3);self.assertEqual(self.c.snapshot()[0],0);self.assertEqual(self.posts,[0])

    def test_unknown_read_never_starts_another_host_observation(self):
        provider=Mock(side_effect=RuntimeError('original unknown'))
        self.start(tool=provider,reconcile=lambda:False)
        self.wait(lambda:provider.call_count==1);time.sleep(.12)
        self.assertEqual(provider.call_count,1);self.assertEqual(self.posts,[])

    def test_nonactivating_caps_close_and_known_busy_end_rearm_without_a_keystroke(self):
        self.start();self.wait(lambda:self.c.policy.confirmed_disables==1)
        self.desktop.visible=True;self.wait(lambda:self.c.policy.confirmed_restores==1)
        self.desktop.visible=False;self.wait(lambda:self.c.policy.confirmed_disables==2)
        self.desktop.input_language_busy=lambda:True;self.wait(lambda:self.c.policy.confirmed_restores==2)
        self.desktop.input_language_busy=lambda:False;self.wait(lambda:self.c.policy.confirmed_disables==3)
        self.assertEqual(self.c.snapshot()[0],0);self.assertEqual(self.posts,[0,1,0,1,0])
