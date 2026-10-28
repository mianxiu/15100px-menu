import json
import unittest
from xml.dom import minidom
from backend import text_list

OPTIONS={'kind':'numbered','marker':'auto','custom_marker':'','numbering':'hierarchical','start':3}
FOREIGN='<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="'+text_list.RDF+'"><rdf:Description rdf:about="" xmlns:f="urn:foreign" f:keep="yes"><f:data><![CDATA[<unrelated>]]></f:data><!--keep--></rdf:Description></rdf:RDF></x:xmpmeta>'


class TextListTests(unittest.TestCase):
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
