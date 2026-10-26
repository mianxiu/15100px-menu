import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from backend.input_context import NativeImeContext


class NativeContextTransportTests(unittest.TestCase):
    def test_native_profile_command_has_bounded_cold_start_budget(self):
        value=NativeImeContext.__new__(NativeImeContext)
        value.user=SimpleNamespace(GetPropW=Mock(return_value=123));value.message=99
        send=Mock(return_value=(1,35))
        with patch.dict(sys.modules,{'win32gui':SimpleNamespace(SendMessageTimeout=send)}):
            self.assertEqual(value.command(7,2,8),35)
        send.assert_called_once_with(7,99,(123<<8)|2,8,2,1000)

    def context(self):
        value=NativeImeContext.__new__(NativeImeContext)
        value.user=SimpleNamespace(GetPropW=Mock(return_value=123));value.command=Mock(return_value=3)
        return value

    def test_nonce_mismatch_cannot_change_another_native_lease(self):
        value=self.context()
        with self.assertRaisesRegex(RuntimeError,'会话已变化'):value.send({'ime':1,'context_nonce':456,'wanted':0,'focus':2})
        value.command.assert_not_called()

    def test_synchronous_native_readback_confirms_only_matching_result(self):
        value=self.context();request={'ime':1,'context_nonce':123,'wanted':0,'focus':2,'input_restore':False}
        self.assertEqual(value.send(request)['ime_open'],0)
        value.command.return_value=9;self.assertEqual(value.send(request),{'rejected':True})
        value.command.return_value=0;self.assertIsNone(value.send(request))
        value.command.return_value=21;request.update(wanted=1,input_restore=True)
        self.assertEqual(value.send(request)['state'],'input')

    def test_reading_or_changed_layout_cannot_renew_unowned_context(self):
        value=self.context();owned={'identity':[1,2,'time',3],'layout':4,'ime':5,'focus':6,'context_nonce':7}
        for sample in ({**owned,'state':'outside'},{**owned,'state':'unknown'},{**owned,'state':'non-input','layout':8},{**owned,'state':'non-input','context_nonce':8}):value.renew(owned,sample)
        value.command.assert_not_called();value.renew(owned,{**owned,'state':'non-input'})
        value.command.assert_called_once_with(5,4,6)
