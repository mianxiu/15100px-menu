import unittest
from backend.input_language import LanguagePolicy,InputLanguage
from types import SimpleNamespace


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
