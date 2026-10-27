import time
import unittest
from backend.text_plan import compute,evaluate,units
from backend.text_tools import mapped_parameters


class TextPlanTests(unittest.TestCase):
    def plan(self,source,operation='edit',draft=None,**extras):
        result=compute(source,{'revision':'r','draft':source if draft is None else draft,'operation':operation,**extras})
        params={key:value for key,value in result.items() if key in {'value','origins','count','breaks','layout'}}
        mapped_parameters({'revision':'r',**params},operation=='split')
        self.assertEqual(len(result['origins']),units(result['value'])+1)
        self.assertTrue(all(a<=b for a,b in zip(result['origins'],result['origins'][1:])))
        return result

    def test_edit_utf16_preserves_unchanged_character_styles(self):
        p=self.plan('A猫😀\rBC',draft='A猫😀\nBX!')
        self.assertEqual(p['value'],'A猫😀\rBX!');self.assertEqual(p['origins'][:6],[0,1,2,3,4,5])
        self.plan('😀',draft='😀尾')
        self.assertEqual(self.plan('x'*19999,draft='x'*19999+'尾')['value'],'x'*19999+'尾')

    def test_regex_groups_literal_backslashes_ignore_case_and_zero_width(self):
        p=self.plan('A12 a34','replace',find=r'(a)(\d+)',replacement=r'\2-\1',regex=True,ignore_case=True)
        self.assertEqual(p['value'],'12-A 34-a');self.assertEqual(p['count'],2)
        self.assertEqual(p['origins'],[0,0,0,0,3,4,4,4,4,4])
        p=self.plan('a','replace',find='a',replacement=r'\1',regex=False,ignore_case=False)
        self.assertEqual(p['value'],r'\1')
        self.assertEqual(self.plan('ab','replace',find='(?=b)',replacement='X',regex=True,ignore_case=False)['value'],'aXb')

    def test_match_ranges_are_utf8_bytes_in_normalized_draft_and_do_not_change_replacement(self):
        p=self.plan('猫😀A12\r尾 a34','replace',find=r'(a)(\d+)',replacement=r'\2-\1',regex=True,ignore_case=True)
        self.assertEqual(p['matches'],[[7,10],[15,18]])
        self.assertEqual(p['preview'],'猫😀12-A\n尾 34-a')
        self.assertEqual(self.plan('a\r\nb','replace',find=r'(?m)^b',replacement='B',regex=True,ignore_case=False)['matches'],[[2,3]])
        p=self.plan('猫😀尾','replace',find=r'(?=😀)',replacement='X',regex=True,ignore_case=False)
        self.assertEqual(p['matches'],[]);self.assertEqual(p['count'],1)
        self.assertEqual(self.plan('xx','replace',find='q',replacement='!',regex=False,ignore_case=False)['matches'],[])

    def test_python_named_groups_lookaround_inline_flags_and_conditionals(self):
        p=self.plan('ID12 id34','replace',find=r'(?i)(?P<key>id)(?P<n>\d+)',replacement=r'\g<n>-\g<key>',regex=True,ignore_case=False)
        self.assertEqual(p['value'],'12-ID 34-id')
        p=self.plan('x12 x34','replace',find=r'(?<=x)\d+(?!\d)',replacement='N',regex=True,ignore_case=False)
        self.assertEqual(p['value'],'xN xN')
        p=self.plan('a ab','replace',find=r'(a)?(?(1)b|c)',replacement='X',regex=True,ignore_case=False)
        self.assertEqual(p['value'],'a X')

    def test_cleanup_case_expansion_and_join_preserve_source_positions(self):
        self.assertEqual(self.plan('  A  \r\r B \r','trim')['value'],'A\r\rB\r')
        p=self.plan('\r A\r \rB\r','remove-empty');self.assertEqual(p['value'],' A\rB');self.assertEqual(p['origins'][:4],[1,2,3,6])
        self.assertEqual(self.plan('A\t  B','space')['value'],'A B')
        self.assertEqual(self.plan('ß a','upper')['origins'][:4],[0,0,1,2])
        self.assertEqual(self.plan('ΟΣ','lower')['value'],'ος')
        self.assertEqual(self.plan('A\rB','join',separator=' · ')['value'],'A · B')

    def test_split_without_newlines_keeps_delimiters_and_maps_styles(self):
        p=self.plan('猫,😀,尾','split',mode='literal',groups='',separator=',',layout='lines')
        self.assertEqual(p['value'],'猫,\r😀,\r尾');self.assertEqual(p['breaks'],[3,7,8]);self.assertEqual(p['count'],3)
        self.assertEqual(p['origins'],[0,1,2,2,3,4,5,5,5])
        p=self.plan('猫,狗;尾','split',mode='regex',groups='',separator='[,;]',layout='lines')
        self.assertEqual(p['value'],'猫,\r狗;\r尾')

    def test_original_line_layout_and_arbitrary_boundary_refusal(self):
        self.assertEqual(self.plan('A\rB\rC','split',mode='lines',groups='1-2,3',separator='',layout='original')['breaks'],[4,5])
        with self.assertRaisesRegex(ValueError,'逐行排列'):self.plan('A,B','split',mode='literal',groups='',separator=',',layout='original')

    def test_limits_empty_invalid_regex_and_invalid_mapping(self):
        for source in ('','x'*20001,'\ud800'):
            with self.assertRaises(ValueError):self.plan(source)
        with self.assertRaises(Exception):self.plan('a','replace',find='[',replacement='',regex=True,ignore_case=False)
        with self.assertRaises(ValueError):self.plan('a','replace',find='a',replacement='',regex=False,ignore_case=False)
        with self.assertRaises(ValueError):mapped_parameters({'revision':'r','value':'ab','origins':[1,0,1],'count':1})

    def test_real_owned_worker_finishes_and_regex_timeout_stops_only_worker(self):
        p={'revision':'r','draft':'猫1','operation':'replace','find':r'\d','replacement':'2','regex':True,'ignore_case':False}
        first=evaluate('猫1',p);self.assertEqual(first['value'],'猫2');self.assertEqual(first['matches'],[[3,4]])
        with self.assertRaisesRegex(ValueError,'unknown group'):evaluate('猫1',{**p,'replacement':r'\g<missing>'})
        p.update(draft='a'*10000+'!',find='(a+)+$',replacement='x')
        start=time.monotonic()
        with self.assertRaisesRegex(ValueError,'超时'):evaluate(p['draft'],p)
        self.assertLess(time.monotonic()-start,5)
        self.assertEqual(evaluate('x',{'revision':'r','draft':'y','operation':'edit'})['value'],'y')
