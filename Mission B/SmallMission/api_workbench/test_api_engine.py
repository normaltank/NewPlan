import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ai_regions import prepare
from bs4 import BeautifulSoup
from api_engine import ModelEngine, qualification, check_coverage
from app import Store
from runtime_paths import APP_ROOT

URL='https://example.edu.cn/staff.htm'
HTML='<title>教师名单</title><nav><a href="/news">新闻</a></nav><div class="roster"><a href="/index.htm">甲</a><a href="/a">John</a><a href="/a">John</a><a href="/b">甲</a><div class="pb_sys_common"><span>1/2</span><a href="/staff/1.htm">下一页</a></div></div>'


def plan(html=HTML):
    s,_,_,_=prepare(html,URL)
    return {'status':'ready','roster_regions':[int(s.select_one('.roster')['data-mb-id'])],
            'pagination_regions':[],'exclude_regions':[],'reason':'名单正文'}


class FakeClient:
    model='test-model'
    max_calls=20
    def __init__(self): self.calls=[]
    async def __aenter__(self): return self
    async def __aexit__(self,*args): pass
    async def ask(self,label,system,payload,**kwargs):
        self.calls.append({'label':label,'usage':{}})
        soup=BeautifulSoup(payload['html'],'lxml')
        return {'status':'ready','roster_regions':[int(soup.select_one('.roster')['data-mb-id'])],
                'pagination_regions':[],'exclude_regions':[],'reason':'名单正文'}


class RegionTests(unittest.TestCase):
    def evaluate(self, html=HTML, answers=None):
        s,n,a,_=prepare(html,URL)
        return qualification(s,n,a,answers or [plan(html),plan(html)],URL)[0]

    def test_pager_removed_without_deleting_legitimate_homepage_or_same_name_urls(self):
        r=self.evaluate()
        self.assertTrue(r['complete'])
        self.assertEqual(set(r['links']),{'https://example.edu.cn/index.htm','https://example.edu.cn/a','https://example.edu.cn/b'})
        self.assertEqual(r['links']['https://example.edu.cn/a']['occurrences'],2)
        self.assertEqual(r['pager_counters'],[(1,2)])

    def test_equal_model_counts_but_different_actual_anchors_are_not_accepted(self):
        html='<div class="roster"><a href="/a">甲</a><a href="/b">乙</a></div>'
        _,nodes,_,_=prepare(html,URL)
        ids=[i for i,n in nodes.items() if n.name=='a']
        plans=[{**plan(html),'roster_regions':[i]} for i in ids]
        self.assertFalse(self.evaluate(html,plans)['complete'])

    def test_agreed_zero_does_not_clear_original(self):
        html='<div class="roster">暂未找到</div>'
        p={**plan(html),'status':'no_links'}
        self.assertFalse(self.evaluate(html,[p,p])['complete'])

    def test_fake_ids_and_bad_exclusion_rejected(self):
        p={**plan(),'roster_regions':[999999]}
        with self.assertRaises(ValueError): self.evaluate(answers=[p,p])
        p={**plan(),'exclude_regions':[{'id':1,'kind':'not_a_person','reason':'不是姓名'}]}
        with self.assertRaises(ValueError): self.evaluate(answers=[p,p])

    def test_unrecognized_next_button_and_dynamic_targets_stay_pending(self):
        for html in ['<div class="roster"><a href="/a">甲</a></div><a href="/staff/1.htm">下一页</a>',
                     '<div class="roster"><a href="javascript:showPerson(1)">甲</a></div>']:
            self.assertFalse(self.evaluate(html)['complete'])

    def test_missing_middle_page_not_hidden_by_duplicate_first_page(self):
        sources=[{'roster_url':u,'parsed':{'complete':True,'issues':[],'pager_counters':[(page,3)]}}
                 for u,page in [(URL,1),('https://example.edu.cn/staff/3.htm',1),('https://example.edu.cn/staff/1.htm',3)]]
        check_coverage(sources)
        self.assertFalse(sources[0]['parsed']['complete'])
        self.assertIn('2',sources[0]['parsed']['issues'][0])

    def test_script_next_page_without_terminal_page_evidence_is_not_complete(self):
        html='<div class="roster"><a href="/a">甲</a></div><div class="pb_sys_common"><a href="javascript:void(0)">下一页</a></div>'
        self.assertFalse(self.evaluate(html)['complete'])
        terminal=html.replace('<a href="javascript:', '<span>2/2</span><a href="javascript:')
        self.assertTrue(self.evaluate(terminal)['complete'])


class CacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_document_cache_revalidated_and_changes_require_new_calls(self):
        with tempfile.TemporaryDirectory(dir=APP_ROOT) as tmp:
            root=Path(tmp);client=FakeClient()
            async with ModelEngine(root/'out',root/'cache',None,client=client) as engine:
                r=await engine.analyze(HTML,URL,root/'out'/'a')
                self.assertTrue(r['complete']);self.assertEqual(len(client.calls),2)
                r=await engine.analyze(HTML,URL,root/'out'/'b')
                self.assertTrue(r['analysis']['cache_hit']);self.assertEqual(len(client.calls),2)
                changed=HTML.replace('href="/b"','href="/c"')
                r=await engine.analyze(changed,URL,root/'out'/'c')
                self.assertFalse(r['analysis']['cache_hit']);self.assertEqual(len(client.calls),4)
                self.assertIn('https://example.edu.cn/c',r['links'])

    async def test_budget_does_not_accept_one_unchecked_answer(self):
        with tempfile.TemporaryDirectory(dir=APP_ROOT) as tmp:
            root=Path(tmp);client=FakeClient();client.max_calls=1
            async with ModelEngine(root/'out',root/'cache',None,client=client) as engine:
                r=await engine.analyze(HTML,URL,root/'out'/'a')
                self.assertFalse(r['complete']);self.assertFalse(client.calls)

    async def test_corrupt_cache_is_ignored_and_checked_again(self):
        with tempfile.TemporaryDirectory(dir=APP_ROOT) as tmp:
            root=Path(tmp);client=FakeClient()
            async with ModelEngine(root/'out',root/'cache',None,client=client) as engine:
                await engine.analyze(HTML,URL,root/'out'/'a')
                f=next((root/'cache').glob('*.json'));entry=json.loads(f.read_text('utf8'));entry['plans']=[];f.write_text(json.dumps(entry),'utf8')
                r=await engine.analyze(HTML,URL,root/'out'/'b')
                self.assertTrue(r['complete']);self.assertEqual(len(client.calls),4)


class SettingsTests(unittest.TestCase):
    def test_secret_is_not_saved_or_returned(self):
        with tempfile.TemporaryDirectory(dir=APP_ROOT) as tmp, patch.dict('os.environ',{'DEEPSEEK_API_KEY':''}):
            root=Path(tmp);store=Store(root/'data');secret='unit-test-private-secret'
            result=store.update_settings({'api_key':secret,'mode':'deepseek','max_calls':10})
            self.assertTrue(result['configured']);self.assertNotIn(secret,json.dumps(result))
            self.assertFalse(list(root.rglob('*.json')))
            self.assertFalse(Store(root/'data').settings()['configured'])
            store.update_settings({'clear_key':True});self.assertFalse(store.settings()['configured'])


if __name__=='__main__':unittest.main()
