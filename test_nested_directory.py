import asyncio,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from bs4 import BeautifulSoup
from api_pilot import Pilot,title_name
from directory_rows import directory_rows
from quality_fields import profile_label_name

PLAN={'page_kind':'directory','row_selector':'ul.contentbox > li.con','label_selector':'div.txt > h3','href_selector':'a','source_qualification':'faculty_roster','body_selector':'','next_selector':'','next_text':'','pager_selector':'','branch_selector':''}
SOURCE=(Path(__file__).parent/'fixtures/nested_rank_cards.html').read_bytes()
NAMES=['李雪铭','张华','张威','郑德凤','王耕','单良','刘亮','高源','贾飞飞']

class NoModel:
    async def ask(self,*args,**kwargs):raise AssertionError('No model needed for the verified structure')

class NestedDirectoryTests(unittest.TestCase):
    def test_real_source_recovers_all_card_name_link_pairs(self):
        soup=BeautifulSoup(SOURCE,'lxml')
        self.assertEqual(len(soup.select(PLAN['row_selector'])),3)
        rows,audit=directory_rows(soup,PLAN,title_name)
        self.assertEqual([title_name(r.select_one('h3').get_text(' ',strip=True)) for r in rows],NAMES)
        self.assertEqual(audit['recovered_rows'],9)
        with tempfile.TemporaryDirectory() as tmp:
            pilot=Pilot(SimpleNamespace(url='https://example.edu.cn/',ocr=False,browser=False),Path(tmp),NoModel())
            pilot.plans['师资']=PLAN.copy()
            item={'url':'https://example.edu.cn/list','loaded_url':'https://example.edu.cn/list','title':'师资队伍','directory':'page','branch':'师资'}
            asyncio.run(pilot.roster(item,soup))
            self.assertEqual([o['name'] for o in pilot.observations],NAMES)
            self.assertEqual(len({o['profile_url'] for o in pilot.observations}),9)
            self.assertEqual(pilot.rosters[-1]['row_recovery']['before_rows'],3)

    def test_valid_list_and_unqualified_page_are_not_expanded(self):
        rows,audit=directory_rows(BeautifulSoup(SOURCE,'html.parser'),PLAN,title_name)
        self.assertEqual(len(rows),9);self.assertIsNone(audit)
        rows,audit=directory_rows(BeautifulSoup(SOURCE,'lxml'),{**PLAN,'source_qualification':'uncertain'},title_name)
        self.assertEqual(len(rows),3);self.assertIsNone(audit)

    def test_nested_subgroup_or_multiple_profile_links_blocks_recovery(self):
        for snippet in ('<ul><li class="con"><a href="other"><div class="txt"><h3>李四 教授</h3></div></a></li></ul>',
                        '<a href="different-person">另一个人</a>'):
            soup=BeautifulSoup(SOURCE,'lxml');soup.select_one('li.con').append(BeautifulSoup(snippet,'lxml'))
            rows,audit=directory_rows(soup,PLAN,title_name)
            self.assertEqual(len(rows),3);self.assertIsNone(audit)

    def test_name_rank_office_label_is_exact_and_keeps_news_out(self):
        self.assertEqual(profile_label_name('王辉 教授/院长'),'王辉')
        self.assertEqual(title_name('张三 副教授／副院长'),'张三')
        for text in ('王辉 教授/院长来校报告','欢迎王辉 教授/院长','王辉/张三 教授/院长','王辉 教授/研究方向'):
            self.assertIsNone(title_name(text),text)

if __name__=='__main__':unittest.main()
