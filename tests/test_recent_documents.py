import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from unittest.mock import AsyncMock
from types import SimpleNamespace
import asyncio
from backend.main import Application
from backend.recent_documents import RecentDocuments
from backend.uxp_bridge import UxpBridge


class RecentTests(unittest.TestCase):
    def test_clipboard_and_eight_most_recent_are_visible_and_executable(self):
        with tempfile.TemporaryDirectory() as folder:
            reader=RecentDocuments(folder,clipboard_reader=lambda:None)
            parent=Path(folder)/'Adobe/Adobe Photoshop 2023/Adobe Photoshop 2023 Settings'
            parent.mkdir(parents=True)
            presets=[{'name':'Custom','width':64+i,'height':32,'units':'pixelsUnit','lastUsedTime':i} for i in range(15)]
            (parent/'MRU New Doc Sizes.json').write_text(json.dumps({'presets':presets}),'utf-8')
            result=reader.refresh('24.0.1')
            self.assertEqual([p['last_used'] for p in result['items'][1:]],list(range(14,6,-1)))
            self.assertEqual(len(reader.presets),8)
            from backend.recent_documents import preset_id
            with self.assertRaises(ValueError):reader.resolve(preset_id(presets[6]))
            self.assertEqual(reader.resolve(result['items'][-1]['id']),presets[7])

    def test_host_match_partial_write_and_detached_selection(self):
        with tempfile.TemporaryDirectory() as folder:
            reader=RecentDocuments(folder,clipboard_reader=lambda:None)
            parent=Path(folder)/'Adobe/Adobe Photoshop 2023/Adobe Photoshop 2023 Settings'
            parent.mkdir(parents=True);path=parent/'MRU New Doc Sizes.json'
            a={'name':'A4','width':210,'height':297,'units':'millimetersUnit','resolution':'print','lastUsedTime':100}
            b={**a,'name':'Custom','lastUsedTime':200,'width':50,'units':'pixelsUnit'}
            path.write_text(json.dumps({'presets':[a,b,{**a,'width':-1}]}),'utf-8')
            result=reader.refresh('24.0.1');self.assertEqual(len(result['items']),3)
            self.assertEqual(result['items'][1]['name'],'自定')
            identity=result['items'][2]['id'];raw=reader.resolve(identity)
            self.assertEqual(raw,a);raw['width']=1;self.assertEqual(reader.resolve(identity)['width'],210)
            before=path.read_bytes();reader.refresh('24.0.1');self.assertEqual(path.read_bytes(),before)
            path.write_text('{','utf-8');self.assertEqual(reader.refresh('24.0.1')['items'],result['items'])
            unavailable=reader.refresh('25.0.0')['items']
            self.assertEqual(len(unavailable),1)
            self.assertFalse(unavailable[0]['available'])
            with self.assertRaises(ValueError):reader.resolve(identity)

class RecentBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_dispatch_rejects_busy_stale_and_home_changed_before_make(self):
        bridge=UxpBridge(config=Path('unused'));bridge.execute_recent=AsyncMock(return_value={'message':'created'})
        desktop=SimpleNamespace(menu_epoch=3,require_home=Mock(),hide=Mock())
        reader=SimpleNamespace(resolve=Mock(return_value={'width':64,'height':32,'units':'pixelsUnit'}))
        app=SimpleNamespace(bridge=bridge,desktop=desktop,recent_documents=reader,
            operation_lock=asyncio.Lock(),panel_lock=asyncio.Lock(),photoshop_launcher=SimpleNamespace(active=False),broadcast=AsyncMock())
        args={'menu_epoch':3,'params':{'preset_id':'selected'}}
        try:
            bridge.busy=True
            with self.assertRaisesRegex(RuntimeError,'未接受'):await Application.dispatch(app,'document.recent',args)
            bridge.busy=False
            await Application.dispatch(app,'document.recent',{**args,'menu_epoch':2})
            desktop.require_home.assert_not_called();bridge.execute_recent.assert_not_awaited()
            desktop.require_home.side_effect=RuntimeError('Home changed')
            with self.assertRaisesRegex(RuntimeError,'Home changed'):await Application.dispatch(app,'document.recent',args)
            bridge.execute_recent.assert_not_awaited()
            desktop.require_home.side_effect=None
            await Application.dispatch(app,'document.recent',args)
            self.assertEqual(bridge.execute_recent.await_count,1)
            # Opening a different menu while a durable target read finishes
            # vetoes the old request before hiding or publishing it to PS.
            callback=bridge.execute_recent.call_args.args[1];desktop.menu_epoch=4
            with self.assertRaisesRegex(RuntimeError,'菜单已重新打开'):await callback({})
            desktop.hide.assert_not_called()
        finally:await bridge.close()
    async def test_capture_and_make_share_fenced_session_and_task_lifecycle(self):
        bridge=UxpBridge(config=Path('unused'));bridge.document_guard=Mock()
        target={'session':'fresh','document_ids':[],'active_document_id':None}
        bridge.transport=Mock()
        bridge.transport.call.side_effect=lambda op,**kw:{'target':target} if op=='inspect' else {'result':{'document_id':5}}
        preset={'width':64,'height':32,'units':'pixelsUnit'}
        try:
            result=await bridge.execute_recent(preset)
            self.assertEqual(bridge.tasks.get(result['task_id'])['state'],'succeeded')
            self.assertEqual(bridge.transport.call.call_args.kwargs,{'target':target,'preset':preset})
            self.assertEqual(bridge.transport.call.call_args.args,('new_document',))
            self.assertEqual(bridge.document_guard.call_count,2)
            bridge.busy=True
            with self.assertRaisesRegex(RuntimeError,'尚未完成'):await bridge.execute_recent(preset)
            self.assertEqual(bridge.transport.call.call_count,2)
        finally:bridge.busy=False;await bridge.close()

    async def test_old_plugin_or_changed_home_never_makes_document(self):
        bridge=UxpBridge(config=Path('unused'));bridge.document_guard=Mock()
        bridge.transport=Mock();bridge.transport.call.return_value={}
        try:
            with self.assertRaisesRegex(RuntimeError,'0.3.2'):await bridge.execute_recent({})
            self.assertEqual(bridge.transport.call.call_count,1)
            bridge.document_guard.side_effect=RuntimeError('Home changed')
            with self.assertRaisesRegex(RuntimeError,'Home changed'):await bridge.execute_recent({})
            self.assertEqual(bridge.transport.call.call_count,1)
        finally:await bridge.close()
