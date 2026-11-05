import copy,json,unittest
from pathlib import Path
from backend import text_object,text_list
from backend.text_object_render import page


def model():
    text='9.\tLong <script> & text\r10.\tOther\r    1.\t二级'
    size=len(text.encode('utf-16-le'))//2
    return {'schema':2,'renderer':'list-v1','canvas':{'width':600,'height':500,'resolution':72,'mode':'RGB','depth':8,'profile':'sRGB IEC61966-2.1'},
      'layer':{'name':'List','xmp':text_list.write('',{'kind':'numbered','numbering':'decimal','marker':'auto','custom_marker':'','start':9}),
      'text':{'_obj':'textLayer','textKey':text,'orientation':{'_value':'horizontal'},'warp':{'warpStyle':{'_value':'warpNone'}},
        'textClickPoint':{'horizontal':{'_unit':'percentUnit','_value':5},'vertical':{'_unit':'percentUnit','_value':5}},
        'textShape':[{'char':{'_value':'box'},'bounds':{'left':0,'right':500,'top':0,'bottom':400}}],
        'textStyleRange':[{'from':0,'to':size+1,'textStyle':{'fontPostScriptName':'MicrosoftYaHei','fontName':'Microsoft YaHei','size':{'_unit':'pointsUnit','_value':20}}}],
        'paragraphStyleRange':[{'from':0,'to':size+1,'paragraphStyle':{}}]}}}


class VectorListRenderTests(unittest.TestCase):
    def test_high_dpi_untagged_shape_bounds_are_document_pixels(self):
        source=model();source['canvas']['resolution']=300
        document,width,height=page(source)
        self.assertEqual((width,height),(192,160))
        self.assertIn('width:160.0px',document)

    def test_source_roundtrip_and_safe_local_page_preserve_source_text(self):
        value=model();saved=copy.deepcopy(value)
        self.assertEqual(text_object.read(text_object.write('',value)),value)
        document,width,height=page(value)
        self.assertEqual(value,saved);self.assertEqual((width,height),(800,500*96/72))
        self.assertIn('&lt;script&gt; &amp;',document);self.assertNotIn('Long <script>',document)
        self.assertIn('data-level="1"',document);self.assertIn('columns.get(row.dataset.level)',document)
        self.assertNotIn('https://',document);self.assertIn("default-src 'none'",document)

    def test_unsupported_layout_font_color_and_broken_list_are_rejected(self):
        for field,value in [('orientation',{'_value':'vertical'}),('transform',{'xx':2})]:
            source=model();source['layer']['text'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):page(source)
        for style in [{'fontAvailable':False},{'horizontalScale':80},{'color':{'_obj':'labColor'}},{'size':{'_unit':'invalid','_value':20}}]:
            source=model();source['layer']['text']['textStyleRange'][0]['textStyle'].update(style)
            with self.subTest(style=style),self.assertRaises(ValueError):page(source)
        source=model();source['layer']['text']['textKey']=source['layer']['text']['textKey'].replace('\t',' ')
        with self.assertRaisesRegex(ValueError,'分隔'):page(source)
        source=model();source['renderer']='future';
        with self.assertRaises(ValueError):text_object.source(source)
