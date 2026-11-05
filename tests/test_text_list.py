import json
import unittest
import os
from unittest.mock import patch
from xml.dom import minidom
from backend import text_list

OPTIONS={'kind':'numbered','marker':'auto','custom_marker':'','numbering':'hierarchical','start':3}
FOREIGN='<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="'+text_list.RDF+'"><rdf:Description rdf:about="" xmlns:f="urn:foreign" f:keep="yes"><f:data><![CDATA[<unrelated>]]></f:data><!--keep--></rdf:Description></rdf:RDF></x:xmpmeta>'


class TextListTests(unittest.TestCase):
    @unittest.skipUnless(os.name=='nt','Windows glyph coverage')
    def test_symbol_font_checks_glyphs_instead_of_font_availability(self):
        self.assertTrue(text_list.symbol_glyphs('•◦▪–✓'))
        self.assertFalse(text_list.symbol_glyphs('\u0378'))

    def test_marker_font_is_bounded_and_missing_glyph_rejected_before_write(self):
        base=[{'from':0,'to':2,'start':0,'first':0}]
        with patch('backend.text_list.symbol_glyphs',return_value=True):
            params,_=text_list.formatting('◦\tX',[0,0,0,1],base,'',True)
        self.assertEqual(params['marker_font'],'SegoeUISymbol');self.assertEqual(text_list.format_parameters(params),params)
        with patch('backend.text_list.symbol_glyphs',return_value=False):
            with self.assertRaisesRegex(ValueError,'不支持'):text_list.formatting('◦\tX',[0,0,0,1],base,'',True)
        with self.assertRaises(ValueError):text_list.format_parameters({**params,'marker_font':'other font'})

    def test_layout_tracks_utf16_paragraphs_and_restores_original_indents(self):
        from backend.text_plan import compute
        source='First😀\rSecond';base=[{'from':0,'to':8,'start':12,'first':3},{'from':8,'to':15,'start':24,'first':-2}]
        params={'revision':'r','draft':source,'operation':'list',**OPTIONS}
        plan=compute(source,params)
        formatting,xml=text_list.formatting(plan['value'],plan['origins'],base,text_list.write(FOREIGN,OPTIONS),True)
        self.assertEqual([row['start'] for row in formatting['paragraphs']],[12,24])
        self.assertTrue(all(row['prefix']>row['from'] for row in formatting['paragraphs']))
        again=compute(plan['value'],{**params,'draft':plan['value']})
        _,xml2=text_list.formatting(again['value'],again['origins'],base,xml,True)
        self.assertEqual(text_list.layout(xml2),text_list.layout(xml))
        removed=compute(plan['value'],{**params,'draft':plan['value'],'kind':'remove'})
        restore,cleared=text_list.formatting(removed['value'],removed['origins'],base,text_list.write(xml,None),False)
        self.assertEqual(removed['value'],source);self.assertIsNone(text_list.layout(cleared))
        self.assertEqual([row['first'] for row in restore['paragraphs']],[3,-2])
        with self.assertRaises(ValueError):text_list.format_parameters({'enabled':True,'paragraphs':[{'from':0,'to':3,'start':float('nan'),'first':0,'prefix':1}]})

    def test_roundtrip_change_remove_preserve_foreign_and_no_stale_text(self):
        first=text_list.write(FOREIGN,OPTIONS)
        self.assertEqual(text_list.read(first),OPTIONS)
        self.assertEqual(text_list.write(first,OPTIONS),first)
        second=text_list.write(first,{**OPTIONS,'start':8})
        self.assertEqual(text_list.read(second)['start'],8)
        removed=text_list.write(second,None)
        self.assertIsNone(text_list.read(removed))
        def foreign(raw):return minidom.parseString(raw).getElementsByTagNameNS(text_list.RDF,'Description')[0].toxml()
        self.assertEqual(foreign(FOREIGN),foreign(first));self.assertEqual(foreign(FOREIGN),foreign(removed))
        self.assertNotIn('draft',first);self.assertEqual(text_list.write('',None),'')

    def test_bounded_xml_and_unknown_schema_rejected_without_overwrite(self):
        good=text_list.write('',OPTIONS)
        bad=[None,'x','x'*131073,'<!DOCTYPE x [<!ENTITY e "bad">]><x/>',good.replace('&quot;schema&quot;:1','&quot;schema&quot;:2'),good.replace('&quot;start&quot;:3','&quot;start&quot;:0')]
        for raw in bad:
            with self.subTest(raw=str(raw)[:60]):
                with self.assertRaises(ValueError):text_list.write(raw,OPTIONS)
        for value in ({**OPTIONS,'extra':1},{**OPTIONS,'kind':'remove'},{**OPTIONS,'start':True}):
            with self.assertRaises(ValueError):text_list.options(value)
        deep='<a>'*70+'b'+'</a>'*70
        with self.assertRaises(ValueError):text_list.read(deep)

    def test_xmp_attribute_form_duplicate_and_custom_unicode(self):
        value={**OPTIONS,'kind':'bullet','marker':'custom','custom_marker':'😀'}
        raw=text_list.write('',value);self.assertEqual(text_list.read(raw),value)
        doc=minidom.parseString(raw);node=doc.getElementsByTagNameNS(text_list.NAMESPACE,'options')[0];desc=node.parentNode
        desc.setAttribute('xmlns:pxmenu',text_list.NAMESPACE);desc.setAttributeNS(text_list.NAMESPACE,'pxmenu:options',node.firstChild.data);desc.removeChild(node)
        self.assertEqual(text_list.read(doc.toxml()),value)
        desc.appendChild(node)
        with self.assertRaises(ValueError):text_list.read(doc.toxml())
