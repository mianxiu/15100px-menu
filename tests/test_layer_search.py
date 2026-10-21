import asyncio
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock,Mock,patch
from backend.layer_search import LayerSearch,query_parameters


class LayerSearchTests(unittest.IsolatedAsyncioTestCase):
    def test_query_validation(self):
        self.assertEqual(query_parameters({}),{'name':'','document':'','type':'all'})
        for value in ({'name':None},{'name':'x'*201},{'document':[]},{'type':'fake'}):
            with self.assertRaises(ValueError):query_parameters(value)

    async def test_failed_search_drops_prior_result_and_releases_slot(self):
        search=LayerSearch(None);search.available=Mock();search.result={'old':True}
        with patch.object(search,'_read',side_effect=RuntimeError('failed')):
            with self.assertRaisesRegex(RuntimeError,'failed'):await search.search({})
        self.assertIsNone(search.result);self.assertFalse(search.searching)

    async def test_repeated_search_rejected_without_queue(self):
        search=LayerSearch(None);search.available=Mock();search.searching=True
        with self.assertRaisesRegex(RuntimeError,'搜索进行中'):await search.search({})

    async def test_focus_uses_stored_result_and_busy_rejects_before_focus(self):
        app=SimpleNamespace(operation_lock=asyncio.Lock(),desktop=SimpleNamespace(focus_search_result=Mock()),
            bridge=SimpleNamespace(execute_focus=AsyncMock(return_value={'message':'done'}),busy=False,layer_context={}),broadcast=AsyncMock())
        search=LayerSearch(app);search.available=Mock();search.valid_until=time.monotonic()+60
        row={'document_id':1,'layer_id':2};search.result={'search_id':'id','session':'s','items':[row]}
        for args in ({'search_id':'bad','index':0},{'search_id':'id','index':True},{'search_id':'id','index':1}):
            with self.assertRaises(ValueError):await search.focus(args)
        app.desktop.focus_search_result.assert_not_called()
        await search.focus({'search_id':'id','index':0,'destination':{'layer_id':999}})
        app.bridge.execute_focus.assert_awaited_once_with('s',row)
        search.available.side_effect=RuntimeError('busy')
        with self.assertRaisesRegex(RuntimeError,'busy'):await search.focus({'search_id':'id','index':0})
        self.assertEqual(app.desktop.focus_search_result.call_count,1)
        self.assertFalse(app.operation_lock.locked())
