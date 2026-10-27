import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,AsyncMock,patch
from backend.text_tools import TextTools,replace_parameters,split_parameters


class TextToolsTests(unittest.IsolatedAsyncioTestCase):
    async def test_preview_is_local_and_apply_consumes_exact_validated_plan_once(self):
        app=SimpleNamespace(operation_lock=asyncio.Lock(),desktop=SimpleNamespace(focus_search_result=Mock()),
            bridge=SimpleNamespace(execute_text=AsyncMock(return_value={'message':'done'}),busy=False,layer_context={}),broadcast=AsyncMock())
        tools=TextTools(app);tools.available=Mock();target={'session':'s','document_id':1,'layer_ids':[2],'active_layer_id':2}
        tools.snapshot={'revision':'r','text':'a','target':target}
        params={'revision':'r','draft':'猫','operation':'edit'}
        from backend.text_plan import compute
        with patch('backend.text_tools.evaluate',side_effect=compute):result=await tools.preview(params)
        app.bridge.execute_text.assert_not_called();self.assertEqual(result['preview'],'猫');self.assertEqual(result['matches'],[])
        with self.assertRaises(ValueError):await tools.apply({'revision':'r','plan_id':'old'})
        request={'revision':'r','plan_id':result['plan_id']}
        await tools.apply(request);app.bridge.execute_text.assert_awaited_once()
        self.assertEqual(app.bridge.execute_text.call_args.args[1]['value'],'猫')
        with self.assertRaises(ValueError):await tools.apply(request)

    async def test_failed_or_late_preview_cannot_leave_an_applicable_plan(self):
        tools=TextTools(SimpleNamespace());tools.available=Mock();saved={'revision':'r','text':'a'};tools.snapshot=saved
        tools.plan=('old',{},'text.replace')
        with patch('backend.text_tools.evaluate',side_effect=ValueError('bad regex')):
            with self.assertRaisesRegex(ValueError,'bad regex'):await tools.preview({'revision':'r','draft':'b','operation':'edit'})
        self.assertIsNone(tools.plan)
        def changed(*_):tools.snapshot=None;return {}
        with patch('backend.text_tools.evaluate',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'已改变'):await tools.preview({'revision':'r','draft':'b','operation':'edit'})
        self.assertIsNone(tools.plan)

    def test_validated_replacement_is_bounded(self):
        params={'revision':'s:1','find':'猫','replacement':''}
        self.assertEqual(replace_parameters(params),params)
        for value in ({},[],{**params,'find':''},{**params,'find':'x'*201},{**params,'replacement':'x'*501},{**params,'extra':True}):
            with self.assertRaises(ValueError):replace_parameters(value)

    async def test_read_clears_stale_preview_and_releases_after_failure(self):
        app=SimpleNamespace(bridge=SimpleNamespace(transport=SimpleNamespace(call=Mock(side_effect=RuntimeError('failed')))))
        tools=TextTools(app);tools.available=Mock();tools.snapshot={'revision':'old'}
        with self.assertRaisesRegex(RuntimeError,'failed'):await tools.read({})
        self.assertIsNone(tools.snapshot);self.assertFalse(tools.reading)

    async def test_replace_binds_original_read_target_and_rejects_repeat(self):
        app=SimpleNamespace(operation_lock=asyncio.Lock(),desktop=SimpleNamespace(focus_search_result=Mock()),
            bridge=SimpleNamespace(execute_text=AsyncMock(return_value={'message':'done'}),busy=False,layer_context={}),broadcast=AsyncMock())
        tools=TextTools(app);tools.available=Mock();target={'session':'s','document_id':1,'layer_ids':[2],'active_layer_id':2}
        tools.snapshot={'revision':'s:1','target':target}
        args={'revision':'s:1','find':'a','replacement':'b'}
        await tools.replace(args);app.bridge.execute_text.assert_awaited_once_with(target,args,'text.replace')
        with self.assertRaises(ValueError):await tools.replace(args)
        self.assertFalse(app.operation_lock.locked());self.assertIsNone(tools.snapshot)

    def test_split_offsets_are_bounded_and_ordered(self):
        self.assertEqual(split_parameters({'revision':'s:1','breaks':[3,8]})['breaks'],[3,8])
        for ends in ([1],[True,3],[3,3],[3,2],[0,3],[3,20001],list(range(1,66))):
            with self.assertRaises(ValueError):split_parameters({'revision':'s:1','breaks':ends})

    async def test_read_rejects_wrong_session_before_exposing_preview(self):
        value={'session':'new','text':{'text':'a','name':'source','revision':'x','target':{'session':'old','document_id':1,'active_layer_id':2,'layer_ids':[2]}}}
        tools=TextTools(SimpleNamespace(bridge=SimpleNamespace(transport=SimpleNamespace(call=Mock(return_value=value)))));tools.available=Mock()
        with self.assertRaisesRegex(RuntimeError,'会话不一致'):await tools.read({})
        self.assertIsNone(tools.snapshot)
