import tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from bs4 import BeautifulSoup
from api_pilot import Pilot,page_links
from test_api_pilot import FakeAPI

class RichRosterLinkRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def collect(self,html,people,qualified=True):
        soup=BeautifulSoup(html,'lxml');url='https://test.edu.cn/list.htm'
        with tempfile.TemporaryDirectory() as tmp:
            p=Pilot(SimpleNamespace(url='https://test.edu.cn/'),Path(tmp),FakeAPI({'people':people}))
            await p.extract_names('names',soup.get_text(' ',strip=True),page_links(soup,url),url,'师资','rich_roster',roster_qualified=qualified)
            return p

    async def test_all_observed_links_of_known_person_survive_model_dedup(self):
        p=await self.collect('<p><a href="/a">郭海健</a></p><p><a href="/b">郭海健</a></p><p><a href="/a">郭海健</a></p>',[{'name':'郭海健','link_id':0,'evidence':'郭海健'}])
        self.assertEqual({o['profile_url'] for o in p.observations},{'https://test.edu.cn/a','https://test.edu.cn/b'})
        self.assertEqual(len(p.observations),2)

    async def test_name_continues_outside_anchor_in_one_person_paragraph(self):
        p=await self.collect('<p><a href="/zheng">郑玉</a><span>芹</span></p>',[{'name':'郑玉芹','link_id':None,'evidence':'郑玉芹'}])
        self.assertEqual([(o['name'],o['profile_url']) for o in p.observations],[('郑玉芹','https://test.edu.cn/zheng')])

    async def test_full_row_name_prevents_a_second_truncated_person(self):
        p=await self.collect('<p><a href="/zheng">郑玉</a>芹</p>',[{'name':'郑玉','link_id':0,'evidence':'郑玉'},{'name':'郑玉芹','link_id':None,'evidence':'郑玉芹'}])
        self.assertEqual([(o['name'],o['profile_url']) for o in p.observations],[('郑玉芹','https://test.edu.cn/zheng')])

    async def test_no_link_is_invented_from_other_person_or_group(self):
        p=await self.collect('<p><a href="/other">张三</a>、李四</p><p>王五</p>',[{'name':'李四','link_id':0,'evidence':'李四'},{'name':'王五','link_id':None,'evidence':'王五'}])
        self.assertTrue(all(not o['profile_url'] for o in p.observations))
        self.assertNotIn('https://test.edu.cn/other',p.targets)

    async def test_model_link_with_existing_rank_suffix_is_preserved(self):
        p=await self.collect('<p><a href="/rank">张三教授</a></p><p><a href="/plain">张三</a></p>',[{'name':'张三','link_id':0,'evidence':'张三教授'}])
        self.assertEqual({o['profile_url'] for o in p.observations},{'https://test.edu.cn/rank','https://test.edu.cn/plain'})

if __name__=='__main__':unittest.main()
