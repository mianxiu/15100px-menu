import asyncio
import json
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock,Mock,patch
from pathlib import Path
from backend.layer_search import LayerSearch,query_parameters


class LayerSearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_preview_uses_stored_destination_and_rejects_stale_results(self):
        search=LayerSearch(SimpleNamespace(bridge=SimpleNamespace(status=AsyncMock(return_value={'layer_preview_available':True}))));search.available=Mock();search.valid_until=time.monotonic()+60
        row={'document_id':1,'layer_id':2};search.result={'search_id':'q','session':'s','items':[row]}
        with patch.object(search,'_read',return_value={'available':False,'reason':'empty'}) as read:
            await search.preview({'search_id':'q','index':0,'destination':{'layer_id':999}})
            read.assert_called_once_with({},row)
            with self.assertRaises(ValueError):await search.preview({'search_id':'old','index':0})


    async def test_preview_read_failure_never_dispatches_or_caches_a_fallback(self):
        app=SimpleNamespace(bridge=SimpleNamespace(status=AsyncMock(return_value={'layer_preview_available':True}),execute_thumbnail=AsyncMock()),broadcast=AsyncMock())
        search=LayerSearch(app);search.available=Mock();search.valid_until=time.monotonic()+60
        search.result={'search_id':'q','session':'s','items':[{'layer_id':2,'type':'pixel'}]}
        for error in ('timeout','stale target','priority interrupted'):
            with patch.object(search,'_read',side_effect=RuntimeError(error)):
                with self.assertRaisesRegex(RuntimeError,error):await search.preview({'search_id':'q','index':0})
            self.assertFalse(search.previews);app.bridge.execute_thumbnail.assert_not_awaited();app.broadcast.assert_not_awaited()

    async def test_legacy_capability_flag_and_unsupported_layer_never_trigger_export(self):
        bridge=SimpleNamespace(status=AsyncMock(return_value={'layer_thumbnail_available':True}),execute_thumbnail=AsyncMock())
        search=LayerSearch(SimpleNamespace(bridge=bridge));search.available=Mock();search.valid_until=time.monotonic()+60
        row={'layer_id':2,'type':'pixel'};search.result={'search_id':'q','session':'s','items':[row]}
        with patch.object(search,'_read') as read:
            with self.assertRaisesRegex(RuntimeError,'不支持静默'):await search.preview({'search_id':'q','index':0})
            bridge.status.return_value={'layer_preview_available':True}
            for kind in ('group','adjustment'):
                row['type']=kind;self.assertFalse((await search.preview({'search_id':'q','index':0}))['available'])
            read.assert_not_called();bridge.execute_thumbnail.assert_not_awaited()

    async def test_no_silent_capability_refuses_before_any_host_preview(self):
        app=SimpleNamespace(bridge=SimpleNamespace(status=AsyncMock(return_value={}),execute_thumbnail=AsyncMock()))
        search=LayerSearch(app);search.available=Mock();search.valid_until=time.monotonic()+60
        search.result={'search_id':'q','session':'s','items':[{'layer_id':2}]}
        with patch.object(search,'_read') as read:
            with self.assertRaisesRegex(RuntimeError,'不支持静默'):await search.preview({'search_id':'q','index':0})
            read.assert_not_called();app.bridge.execute_thumbnail.assert_not_awaited()

    async def test_direct_read_unsupported_never_uses_legacy_document_copy(self):
        app=SimpleNamespace(bridge=SimpleNamespace(status=AsyncMock(return_value={'layer_preview_available':True}),execute_thumbnail=AsyncMock()))
        search=LayerSearch(app);search.available=Mock();search.valid_until=time.monotonic()+60
        search.result={'search_id':'q','session':'s','items':[{'layer_id':2,'type':'pixel'}]}
        with patch.object(search,'_read',return_value={'available':False,'fallback':True,'reason':'unsupported'}):
            value=await search.preview({'search_id':'q','index':0})
        self.assertFalse(value['available']);app.bridge.execute_thumbnail.assert_not_awaited()

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


class LayerPreviewReadTests(unittest.TestCase):
    def read(self,value,supersede=False):
        with tempfile.TemporaryDirectory() as name:
            folder=Path(name);config=folder/'config.json';config.write_text(json.dumps({'token':'test'}),'utf-8')
            transport=SimpleNamespace(_discover=lambda:(folder,{'session':'s','probe_version':'0.3.70'}),config=config)
            search=LayerSearch(SimpleNamespace(bridge=SimpleNamespace(transport=transport,busy=False),operation_lock=SimpleNamespace(locked=lambda:False)))
            def publish(temp,destination):
                temp.replace(destination);request=json.loads(destination.read_text('utf-8'))
                (folder/'layer-search-result.json').write_text(json.dumps({'schema':1,'id':request['id'],'session':'s','result':value}),'utf-8')
                if supersede:destination.write_text(json.dumps({'id':'new'}),'utf-8')
            with patch('backend.layer_search.publish_request',side_effect=publish):return search._read({}, {'layer_id':2})

    def test_pixel_shape_and_component_validation(self):
        tile={'available':True,'width':1,'height':1,'pixels':[255,0,0,128]}
        self.assertEqual(self.read(tile),tile)
        for bad in ({**tile,'width':129},{**tile,'pixels':[True,0,0,255]},{**tile,'pixels':[256,0,0,255]},{'available':False,'reason':[]},{'available':False,'reason':'x','fallback':'yes'},{**tile,'fallback':True}):
            with self.assertRaises(ValueError):self.read(bad)

    def test_superseding_search_cancels_old_preview_without_wait(self):
        with self.assertRaisesRegex(RuntimeError,'取代'):self.read({'available':False,'reason':'empty'},supersede=True)
