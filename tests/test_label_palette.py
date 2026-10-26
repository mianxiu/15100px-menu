import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

from backend.layer_labels import LABEL_COLORS, SLOT_NAMES, THEME_NAMES, LabelPalette, read_label_palette


FALLBACK=[{**v,'source':'fallback'} for v in LABEL_COLORS]


def fixture(modern=False):
    entries=[]
    for i,name in enumerate(SLOT_NAMES[:12 if modern else 8]):
        for suffix in ('','Disabled'):
            values=[[10+i+theme,30+theme,50,1.0] for theme in range(4)]
            if suffix:values=[[v[0]+20,*v[1:]] for v in values]
            entries.append('SlotColor'+name+suffix+': '+json.dumps(values))
    return '\n'.join(entries)


class LabelPaletteTests(unittest.TestCase):
    def test_four_host_themes_and_disabled_colors_keep_enum_identity(self):
        data=read_label_palette(fixture(True))
        self.assertEqual(set(data),{v['id'] for v in LABEL_COLORS})
        self.assertEqual(data['grain']['rgb'][1],[15,31,50])
        self.assertEqual(data['fuchsia']['disabled_rgb'][3],[44,33,50])
        self.assertEqual(read_label_palette(fixture().replace('SlotColorRed:','slotcolorred:'))['red']['rgb'][0],[11,30,50])

    def test_palette_cached_per_session_theme_switch_does_not_read_again(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'UIColors.txt';path.write_text(fixture(True),encoding='utf-8')
            original=path.read_bytes();locate=Mock(return_value=path);reader=LabelPalette(locate)
            state={'connected':True,'photoshop_version':'24.0.1','layer_context':{'session':'one'}}
            for i,theme in enumerate(THEME_NAMES):
                result=reader.refresh({**state,'ui_theme':theme})
                self.assertEqual(result[1]['rgb'],[11+i,30+i,50])
                self.assertEqual(result[1]['disabled_rgb'],[31+i,30+i,50])
            locate.assert_called_once_with('24.0.1');self.assertEqual(reader.source,'host-ui-colors')
            self.assertEqual(reader.refresh({**state,'ui_theme':'unknown'})[1]['rgb'],[14,33,50])
            result[1]['rgb'][0]=0
            self.assertEqual(reader.refresh({**state,'ui_theme':'light'})[1]['rgb'][0],11)
            reader.refresh({**state,'layer_context':{'session':'two'}})
            self.assertEqual(locate.call_count,2);self.assertEqual(path.read_bytes(),original)

    def test_missing_modern_entries_retain_known_fallback_not_invented_colors(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'UIColors.txt';path.write_text(fixture(),encoding='utf-8')
            colors=LabelPalette(lambda _:path).refresh({'connected':True,'photoshop_version':'24.0.1','layer_context':{'session':'a'},'ui_theme':'dark'})
            self.assertEqual(colors[8]['rgb'],LABEL_COLORS[8]['rgb'])
            self.assertEqual(colors[0]['rgb'],[13,33,50])

    def test_float_channels_and_partial_modern_palette_are_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'UIColors.txt'
            path.write_text(fixture().replace('[10, 30, 50, 1.0]','[10.5, 30.0, 50, 1.0]'),encoding='utf-8')
            reader=LabelPalette(lambda _:path)
            values=reader.refresh({'connected':True,'photoshop_version':'25.2','layer_context':{'session':'a'},'ui_theme':'light'})
            self.assertEqual(values[0]['rgb'],[11,30,50])
            self.assertEqual(reader.source,'host-ui-colors-partial')
            self.assertEqual(values[8]['source'],'fallback')
            self.assertEqual(values[0]['source'],'host-ui-colors')

    def test_transient_startup_lookup_retries_bounded_without_queries_after_success(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'UIColors.txt';path.write_text(fixture(),encoding='utf-8')
            locate=Mock(side_effect=[OSError('workspace not ready'),path])
            reader=LabelPalette(locate);state={'connected':True,'photoshop_version':'24.0.1','layer_context':{'session':'a'}}
            with patch('backend.layer_labels.time.monotonic',return_value=10):
                self.assertEqual(reader.refresh(state),FALLBACK)
                reader.refresh(state);locate.assert_called_once()
            with patch('backend.layer_labels.time.monotonic',return_value=13):
                reader.refresh(state);reader.refresh(state)
            self.assertEqual(locate.call_count,2);self.assertEqual(reader.source,'host-ui-colors')
            reader=LabelPalette(Mock(side_effect=OSError('unavailable')))
            for tick in (1,2,3,5,10,100):
                with patch('backend.layer_labels.time.monotonic',return_value=tick):reader.refresh(state)
            self.assertEqual(reader.locate.call_count,3)

    def test_invalid_resource_data_rejected(self):
        for bad in ('[256,30,50,1.0]','[-1,30,50,1.0]','[true,30,50,1.0]','[10,30,50,0.5]'):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                read_label_palette(fixture().replace('[10, 30, 50, 1.0]',bad,1))
        with self.assertRaises(ValueError):read_label_palette('SlotColorRed: [[1,2,3,1],[1,2,3,1],[1,2,3,1],[1,2,3,1]]')

    def test_missing_oversized_or_partial_file_uses_bounded_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'UIColors.txt';state={'connected':True,'photoshop_version':'24.0.1','layer_context':{'session':'a'}}
            for content in (None,'x'*(1024*1024+1),'SlotColorRed: ['):
                if content is not None:path.write_text(content,encoding='utf-8')
                reader=LabelPalette(lambda _:path)
                self.assertEqual(reader.refresh(state),FALLBACK);self.assertEqual(reader.source,'fallback')

    def test_no_unverified_host_lookup_and_unknown_theme_uses_dark(self):
        locate=Mock(side_effect=AssertionError('No host lookup expected'))
        self.assertEqual(LabelPalette(locate).refresh({'connected':False}),FALLBACK)
        self.assertEqual(LabelPalette(locate).refresh({'connected':True,'photoshop_version':'24.0.1'}),FALLBACK)
        locate.assert_not_called()

    def test_concurrent_status_reads_share_one_completed_resource_snapshot(self):
        from concurrent.futures import ThreadPoolExecutor
        import threading
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'UIColors.txt';path.write_text(fixture(),encoding='utf-8')
            entered=threading.Event();release=threading.Event()
            def locate(_):
                entered.set();self.assertTrue(release.wait(2));return path
            reader=LabelPalette(Mock(side_effect=locate))
            state={'connected':True,'photoshop_version':'24.0.1','layer_context':{'session':'a'},'ui_theme':'light-gray'}
            with ThreadPoolExecutor(max_workers=2) as pool:
                first=pool.submit(reader.refresh,state);self.assertTrue(entered.wait(2))
                second=pool.submit(reader.refresh,state);release.set()
                self.assertEqual(first.result(2),second.result(2))
            reader.locate.assert_called_once_with('24.0.1')
