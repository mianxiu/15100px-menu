import json
import struct
import tempfile
import unittest
import ctypes
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from types import SimpleNamespace
from pathlib import Path
from backend.clipboard_preset import dib_size
from backend.recent_documents import RecentDocuments


class ClipboardPresetTests(unittest.TestCase):
    def test_concurrent_status_reads_share_one_live_clipboard_handle(self):
        from backend import clipboard_preset as module
        class Function:
            def __init__(self,call):self.call=call
            def __call__(self,*args):return self.call(*args)
        state={'open':0,'peak':0,'reads':0,'seq':1234,'available':True}
        def open_clipboard(_):
            state['open']+=1;state['peak']=max(state['peak'],state['open']);return True
        def close_clipboard():state['open']-=1
        def get_data(_):state['reads']+=1;time.sleep(.01);return 1
        header=ctypes.create_string_buffer(struct.pack('<Iii',40,249,101)+bytes(28))
        user=SimpleNamespace(**{k:Function(v) for k,v in {
            'OpenClipboard':open_clipboard,'CloseClipboard':close_clipboard,'GetClipboardData':get_data,
            'GetClipboardSequenceNumber':lambda:state['seq'],'IsClipboardFormatAvailable':lambda _:state['available']}.items()})
        kernel=SimpleNamespace(**{k:Function(v) for k,v in {'GlobalSize':lambda _:40,
            'GlobalLock':lambda _:ctypes.addressof(header),'GlobalUnlock':lambda _:None}.items()})
        with patch.object(module,'_cached_sequence',None),patch.object(module,'_cached_metadata',None),patch.object(module.ctypes,'WinDLL',side_effect=lambda name,**kw:user if name=='user32' else kernel):
            with ThreadPoolExecutor(max_workers=12) as pool:values=list(pool.map(lambda _:module.image_metadata(),range(48)))
            self.assertEqual(state['peak'],1);self.assertEqual(state['reads'],1);self.assertEqual(state['open'],0)
            values[0]['width']=999;self.assertEqual(module.image_metadata()['width'],249)
            state['seq']+=1;self.assertEqual(module.image_metadata()['sequence'],1235);self.assertEqual(state['reads'],2)
            state['seq']+=1;state['available']=False;self.assertIsNone(module.image_metadata())
    def test_dib_header_top_down_and_bad_dimensions(self):
        def header(w,h,length=40):return struct.pack('<Iii',length,w,h)+bytes(28)
        self.assertEqual(dib_size(header(249,101)),(249,101))
        self.assertEqual(dib_size(header(249,-101,124)),(249,101))
        for h in (b'',header(0,100),header(100,0),header(-10,100),header(300001,100),header(100,100,12)):
            self.assertIsNone(dib_size(h))

    def test_clipboard_first_updates_despite_unchanged_mru_and_rejects_stale(self):
        current={'sequence':1,'width':249,'height':101}
        with tempfile.TemporaryDirectory() as folder:
            parent=Path(folder)/'Adobe/Adobe Photoshop 2023/Adobe Photoshop 2023 Settings'
            parent.mkdir(parents=True)
            path=parent/'MRU New Doc Sizes.json'
            raw=[{'name':'Custom','width':64+i,'height':32,'units':'pixelsUnit','lastUsedTime':i} for i in range(12)]
            path.write_text(json.dumps({'presets':raw}),'utf-8')
            original=path.read_bytes()
            reader=RecentDocuments(folder,clipboard_reader=lambda:current)
            first=reader.refresh('24.0.1')['items']
            self.assertEqual(len(first),9)
            self.assertEqual(first[0]['name'],'剪贴板')
            self.assertTrue(first[0]['available'])
            self.assertEqual(first[0]['size'],'249 × 101 px')
            preset=reader.resolve(first[0]['id'])
            self.assertEqual((preset['width'],preset['height'],preset['resolution']),(249,101,72))
            current={'sequence':2,'width':300,'height':200}
            with self.assertRaisesRegex(ValueError,'剪贴板图像已改变'):reader.resolve(first[0]['id'])
            newer=reader.refresh('24.0.1')['items']
            self.assertEqual(newer[0]['size'],'300 × 200 px')
            self.assertNotEqual(first[0]['id'],newer[0]['id'])
            current=None
            empty=reader.refresh('24.0.1')['items']
            self.assertFalse(empty[0]['available'])
            self.assertEqual(empty[1:],newer[1:])
            self.assertEqual(path.read_bytes(),original)
