import unittest
from backend.input_language import LanguagePolicy,InputLanguage
from types import SimpleNamespace
from backend.input_accessibility import control_state
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import Mock,patch


class LanguagePolicyTests(unittest.TestCase):
    def sample(self,state='non-input',layout=0x8040804,focus=10):
        return {'root':1,'identity':[1,2,'created',3],'focus':focus,'layout':layout,'state':state}

    def test_unknown_input_outside_and_no_english_never_switch(self):
        for sample in [self.sample('unknown'),self.sample('input'),{'state':'outside'}]:
            self.assertIsNone(LanguagePolicy().step(sample,7,0x4090409,0))
        self.assertIsNone(LanguagePolicy().step(self.sample(),7,None,0))

    def test_one_request_then_readback_before_ownership_and_restore(self):
        p=LanguagePolicy();request=p.step(self.sample(),7,0x4090409,0)
        self.assertEqual(request['wanted'],0x4090409);self.assertIsNone(p.owned)
        self.assertIsNone(p.step(self.sample(),7,0x4090409,.1))
        self.assertIsNone(p.step(self.sample(layout=0x4090409),7,0x4090409,.2))
        self.assertEqual(p.confirmed_switches,1)
        request=p.step(self.sample('input',0x4090409,11),7,0x4090409,.3)
        self.assertEqual(request['wanted'],0x8040804);self.assertFalse(request['switch'])
        self.assertIsNotNone(p.owned)
        p.step(self.sample('input',focus=11),7,0x4090409,.4)
        self.assertIsNone(p.owned);self.assertEqual(p.confirmed_restores,1)

    def test_unknown_result_is_retained_and_not_reposted(self):
        p=LanguagePolicy();request=p.step(self.sample(),7,0x4090409,0)
        for tick in [2,3,100]:self.assertIsNone(p.step(self.sample(),8,0x4090409,tick))
        self.assertEqual(p.pending,request);self.assertEqual(p.state,'request-not-confirmed')

    def test_manual_change_releases_ownership_without_overwrite(self):
        p=LanguagePolicy();p.step(self.sample(),7,0x4090409,0)
        p.step(self.sample(layout=0x4090409),7,0x4090409,.1)
        self.assertIsNone(p.step(self.sample('input',layout=0x4110411),7,0x4090409,.2))
        self.assertIsNone(p.owned);self.assertEqual(p.state,'manual-change')

    def test_other_process_or_reused_window_never_receives_restore(self):
        p=LanguagePolicy();p.step(self.sample(),7,0x4090409,0)
        p.step(self.sample(layout=0x4090409),7,0x4090409,.1)
        changed=self.sample('input',layout=0x4090409);changed['identity'][2]='new process'
        self.assertIsNone(p.step(changed,7,0x4090409,.2))
        self.assertIsNone(p.step({'state':'outside'},7,0x4090409,.3))
        self.assertIsNotNone(p.owned)

    def test_failed_restore_is_not_queued_every_poll(self):
        p=LanguagePolicy();p.step(self.sample(),7,0x4090409,0)
        p.step(self.sample(layout=0x4090409),7,0x4090409,.1)
        self.assertIsNotNone(p.step(self.sample('input',0x4090409),7,0x4090409,.2))
        p.pending=None
        self.assertIsNone(p.step(self.sample('input',0x4090409),7,0x4090409,.3))

    def test_repeated_independent_intents_each_restore_once(self):
        p=LanguagePolicy()
        for intent in range(1,4):
            self.assertIsNotNone(p.step(self.sample(),intent,0x4090409,intent))
            p.step(self.sample(layout=0x4090409),intent,0x4090409,intent+.1)
            self.assertIsNotNone(p.step(self.sample('input',0x4090409),intent,0x4090409,intent+.2))
            p.step(self.sample('input'),intent,0x4090409,intent+.3)
        self.assertEqual(p.confirmed_switches,3);self.assertEqual(p.confirmed_restores,3)

    def test_input_intent_invalidates_old_click_without_clearing_ownership(self):
        controller=InputLanguage(SimpleNamespace());controller.policy.owned={'preserved':True}
        controller.click(1,2);self.assertIsNotNone(controller.intent)
        controller.protect();self.assertIsNone(controller.intent)
        self.assertEqual(controller.policy.owned,{'preserved':True});self.assertTrue(controller.wake.is_set())

    def test_confirmed_restore_allows_same_ps_focus_to_return_to_eng(self):
        p=LanguagePolicy()
        for tick in (0,1):
            self.assertIsNotNone(p.step(self.sample(),7,0x4090409,tick))
            p.step(self.sample(layout=0x4090409),7,0x4090409,tick+.1)
            p.step(self.sample('input',0x4090409),7,0x4090409,tick+.2)
            p.step(self.sample('input'),7,0x4090409,tick+.3)
        self.assertEqual(p.confirmed_switches,2);self.assertEqual(p.confirmed_restores,2)

    def test_activity_invalidates_tool_evidence_without_becoming_a_click(self):
        controller=InputLanguage(SimpleNamespace())
        controller.protect();epoch=controller.epoch;serial=controller.serial
        controller.activity()
        self.assertFalse(controller.protected);self.assertIsNone(controller.intent)
        self.assertEqual(controller.epoch,epoch);self.assertGreater(controller.serial,serial)


class FocusAccessibilityTests(unittest.TestCase):
    def row(self,kind=50000,**changes):
        row={30002:2,30003:kind,30008:True,30010:True,30020:10,30022:False,
             30033:False,30040:False,30043:False}
        row.update({int(k):v for k,v in changes.items()});return row

    def test_toolbars_layers_tabs_menus_and_dialog_buttons_need_no_canvas_click(self):
        for kind in (50021,50008,50007,50024,50000,50018,50019,50011,50017):
            self.assertEqual(control_state(self.row(kind),2),'non-input',kind)

    def test_canvas_generic_panels_and_home_require_positive_tool_evidence(self):
        for kind in (50025,50030,50032,50033):
            row=self.row(kind)
            self.assertEqual(control_state(row,2,True),'unknown')
            self.assertEqual(control_state(row,2,False,'moveTool'),'unknown')
            for tool in ('moveTool','pathComponentSelectTool','directSelectTool','blurTool','frameTool'):
                self.assertEqual(control_state(row,2,True,tool),'non-input',tool)
            for tool in ('typeCreateOrEditTool','typeVerticalCreateOrEditTool','typeMaskTool'):
                self.assertEqual(control_state(row,2,True,tool),'input',tool)

    def test_native_and_custom_edit_rename_search_numeric_and_text_pattern_are_protected(self):
        for kind in (50003,50004,50016):self.assertEqual(control_state(self.row(kind),2),'input')
        for props in ({'30040':True},{'30043':True,'30046':False},{'30033':True,'30048':False}):
            self.assertEqual(control_state(self.row(50025,**props),2,True,'moveTool'),'input')

    def test_idle_type_tool_allows_shortcuts_but_actual_editing_never_does(self):
        for tool in ('typeCreateOrEditTool','typeVerticalCreateOrEditTool','typeMaskTool','pathComponentSelectTool'):
            for kind in (50025,50030,50032,50033):
                self.assertEqual(control_state(self.row(kind),2,True,{'classID':tool,'isModal':False}),'non-input')
                self.assertEqual(control_state(self.row(kind),2,True,{'classID':tool,'isModal':True}),'input')
            self.assertEqual(control_state(self.row(50004),2,True,{'classID':tool,'isModal':False}),'input')
        for tool in ({'classID':'moveTool'},{'classID':'moveTool','isModal':0},{'classID':'','isModal':False}):
            self.assertEqual(control_state(self.row(50033),2,True,tool),'unknown')

    def test_missing_stale_foreign_offscreen_and_unsupported_properties_never_grant_eng(self):
        for props in ({'30002':3},{'30003':object()},{'30008':False},{'30010':False},{'30022':True},{'30043':None},{'30040':None}):
            self.assertEqual(control_state(self.row(**props),2),'unknown')
        self.assertEqual(control_state({},2,True,'moveTool'),'unknown')


class LanguageWorkerTests(unittest.TestCase):
    def start_worker(self,*,acknowledge=True,kind=50000):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.desktop=SimpleNamespace(runtime=Path(temp.name),settings={'enabled':True},visible=False,
                                     stop=threading.Event(),input_language_busy=lambda:False)
        self.controller=InputLanguage(self.desktop);self.layout=0x8040804;self.kind=kind;self.modal=False;self.posts=[]
        def sample():
            return {'root':1,'identity':[1,2,'test-process',3],'focus':10,'layout':self.layout,'pid':2,
                    'state':'unknown','workspace':True,'class':'test',
                    'accessibility':FocusAccessibilityTests().row(self.kind)}
        self.controller.sample=sample
        self.desktop.input_language_tool=lambda:{'classID':'typeCreateOrEditTool','isModal':self.modal}
        def installed(count,array):array[0]=0x8040804;array[1]=0x4090409;return 2
        def post(hwnd,message,unused,layout):
            self.posts.append(layout)
            if acknowledge:self.layout=layout
            return True
        self.user=SimpleNamespace(GetKeyboardLayout=Mock(),GetKeyboardLayoutList=Mock(side_effect=installed),
                                  PostMessageW=Mock(side_effect=post),GetAsyncKeyState=Mock(return_value=0))
        api=patch('backend.input_language.ctypes.WinDLL',return_value=self.user);api.start();self.addCleanup(api.stop)
        uia=patch('backend.input_accessibility.FocusAccessibility',return_value=object());uia.start();self.addCleanup(uia.stop)
        self.controller.thread.start()
        def stop():
            self.desktop.stop.set();self.controller.wake.set();self.controller.thread.join(2)
            self.assertFalse(self.controller.thread.is_alive())
        self.addCleanup(stop)

    def wait(self,predicate):
        until=time.monotonic()+2
        while not predicate():
            self.assertLess(time.monotonic(),until,self.controller.report)
            time.sleep(.005)

    def test_without_click_all_ps_non_input_focus_switches_restores_and_returns_to_eng(self):
        self.start_worker()
        self.wait(lambda:self.controller.policy.confirmed_switches==1)
        self.assertIsNone(self.controller.intent)
        self.kind=50004;self.controller.activity()
        self.wait(lambda:self.controller.policy.confirmed_restores==1)
        self.kind=50021;self.controller.activity()
        self.wait(lambda:self.controller.policy.confirmed_switches==2)
        self.desktop.stop.set();self.controller.wake.set();self.controller.thread.join(2)
        self.assertEqual(self.posts,[0x4090409,0x8040804,0x4090409,0x8040804])
        self.assertEqual(self.controller.policy.confirmed_restores,2)

    def test_idle_type_tool_allowed_then_modal_editing_restores_without_sending_keys(self):
        self.start_worker(kind=50033);self.wait(lambda:self.controller.policy.confirmed_switches==1)
        self.kind=50033;self.modal=True;self.controller.protect()
        self.wait(lambda:self.controller.policy.confirmed_restores==1)
        self.modal=False;self.controller.activity()
        self.wait(lambda:self.controller.policy.confirmed_switches==2)
        self.assertTrue(all(call.args[1]==0x50 for call in self.user.PostMessageW.call_args_list))

    def test_unconfirmed_switch_is_never_repeated_or_assumed_owned(self):
        self.start_worker(acknowledge=False);self.wait(lambda:len(self.posts)==1)
        self.controller.policy.pending['time']=time.monotonic()-2
        self.controller.activity();self.wait(lambda:self.controller.policy.state=='request-not-confirmed')
        self.assertIsNone(self.controller.policy.owned)
        self.kind=50004;self.controller.activity()
        self.desktop.stop.set();self.controller.wake.set();self.controller.thread.join(2)
        self.assertEqual(self.posts,[0x4090409]);self.assertIsNotNone(self.controller.policy.pending)

    def test_tool_observation_failure_restores_owned_layout_and_never_grants_eng(self):
        self.start_worker();self.wait(lambda:self.controller.policy.confirmed_switches==1)
        self.kind=50033
        self.desktop.input_language_tool=Mock(side_effect=RuntimeError('unknown original observation'))
        self.controller.activity();self.wait(lambda:self.controller.policy.confirmed_restores==1)
        self.assertEqual(self.posts,[0x4090409,0x8040804])

    def test_return_from_busy_rechecks_tool_without_another_click_or_key(self):
        self.start_worker(kind=50033);self.wait(lambda:self.controller.policy.confirmed_switches==1)
        busy=[True];self.desktop.input_language_busy=lambda:busy[0]
        self.controller.activity();self.wait(lambda:self.controller.policy.confirmed_restores==1)
        before=self.controller.report['tool_reads'];busy[0]=False
        self.wait(lambda:self.controller.policy.confirmed_switches==2)
        self.assertGreater(self.controller.report['tool_reads'],before)
