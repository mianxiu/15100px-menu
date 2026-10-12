import json
import struct
import tempfile
import unittest
from pathlib import Path
from backend.clipboard_preset import dib_size
from backend.recent_documents import RecentDocuments


class ClipboardPresetTests(unittest.TestCase):
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
