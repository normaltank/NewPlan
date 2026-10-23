import unittest
import asyncio,json,tempfile
from pathlib import Path
from types import SimpleNamespace
from bs4 import BeautifulSoup
from profile_layouts import structured_profile
from quality_fields import fields_from_text
from api_pilot import Pilot
from test_workbench import fixture
from quality_pipeline import build

class NoModel:
    async def ask(self,*args,**kwargs):raise AssertionError('recognized layout should not call model')

class CardTitleTests(unittest.TestCase):
    def run_profile(self,card_title,biography):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        store,key=fixture(Path(temp.name));root=Path(store.job(key)['run_dir'])
        page=json.loads((root/'pages.json').read_text())[0];page['loaded_url']=page['url']
        html='<div class="article"><div class="arti_top"><div class="news_wz"><h1 class="news_title">张三</h1><div class="news_info"><div class="news_field">'+card_title+'</div><div class="news_field">通讯方式：z@edu.cn</div></div></div></div><div class="arti_bottom"><div class="entry">'+biography+'</div></div></div>'
        (root/'page/source.html').write_text(html,encoding='utf8')
        pilot=Pilot(SimpleNamespace(url='https://test.edu.cn/',ocr=False,browser=False),root,NoModel())
        pilot.observe('张三',page['url'],'https://test.edu.cn/list','师资','directory_link','张三')
        asyncio.run(pilot.profile(page,BeautifulSoup(html,'lxml')))
        (root/'pages.json').write_text(json.dumps([page]),encoding='utf8')
        (root/'issues.json').write_text(json.dumps(pilot.issues),encoding='utf8')
        build(store,key);cat=store.catalog(key)
        return cat['people'][0]['review'],cat['issues'],page
    def test_conflicting_current_titles_keep_other_fields_deliverable(self):
        r,issues,page=self.run_profile('研究员','张三，教授。研究方向：能源材料。')
        self.assertIn('personal_title_conflict',page)
        self.assertEqual(r['status'],'auto_accepted')
        self.assertEqual(r['fields']['title'],'')
        self.assertEqual(r['fields']['missing']['title'],'conflict')
        self.assertEqual(r['fields']['email'],'z@edu.cn')
        self.assertTrue(any(i['issue_kind']=='profile_title_conflict' and i['review']['status']=='pending' for i in issues))
        self.assertTrue(any(n['code']=='title_conflict' for n in r['delivery_notes']))
    def test_abbreviated_card_preserves_detailed_current_appointment(self):
        r,issues,page=self.run_profile('教授','张三，特聘教授。研究方向：能源材料。')
        self.assertEqual(r['fields']['title'],'特聘教授')
        self.assertNotIn('personal_title_conflict',page)
    def test_advisers_title_does_not_override_named_personal_card(self):
        r,issues,page=self.run_profile('副教授','个人简介\n在李四教授课题组开展材料研究。')
        self.assertEqual(r['fields']['title'],'副教授')
        self.assertNotIn('personal_title_conflict',page)

class BoundLayouts(unittest.TestCase):
    def test_article_card_only_binds_exact_person_and_its_sibling_cv(self):
        soup=BeautifulSoup('<div class="article"><div class="arti_top"><div class="news_wz"><h1 class="news_title">张三</h1><div class="news_info"><div class="news_field">工程系副教授，硕士生导师</div><div class="news_field">通讯方式：z@edu.cn</div></div></div></div><div class="arti_bottom"><div class="entry">个人简介：张三研究工程</div><div class="entry">论文及项目全文</div></div></div><footer>admin@edu.cn</footer>','lxml')
        layout=structured_profile(soup,{'张三'});text=layout['card']+'\n'+layout['body'].get_text('\n',strip=True)
        self.assertIn('论文及项目全文',text);self.assertNotIn('admin@',text)
        self.assertEqual(fields_from_text('张三',text)['title']['value'],'副教授')
        self.assertIsNone(structured_profile(soup,{'李四'}))
        self.assertIsNone(structured_profile(soup,{'张三','李四'}))
        soup.select_one('h1').string='张三教授的研究团队获奖'
        self.assertIsNone(structured_profile(soup,{'张三'}))
    def test_empty_section_titles_are_not_a_biography(self):
        soup=BeautifulSoup('<div><div class="top"><div class="carrer"><div class="title"><span class="jsbt">张三</span></div></div></div><div class="tearchContainer"><div class="news_box"><h2>个人简介</h2><div class="con"></div></div></div></div>','lxml')
        self.assertTrue(structured_profile(soup,{'张三'})['empty_cv'])
    def test_wrapped_duplicate_email_requires_an_exact_complete_copy(self):
        text='张三，教授。邮箱：test@seu.edu.cn\n联系：test@seu.edu. cn'
        self.assertEqual(fields_from_text('张三',text)['email']['value'],'test@seu.edu.cn')
        text='张三，教授。邮箱：test@seu.edu.cn\n另一个邮箱：test@seu.edu'
        self.assertEqual(set(fields_from_text('张三',text)['email']['value'].split('; ')),{'test@seu.edu.cn','test@seu.edu'})
    def test_card_and_cv_same_widget_exclude_footer_and_second_person(self):
        soup=BeautifulSoup('''<div><div class="top"><div class="carrer"><div class="title"><span class="jsbt">张三</span><span>教授</span></div><div>邮箱:z@edu.cn</div></div></div><div class="tearchContainer">个人简介：张三研究材料</div></div><footer>邮箱:public@edu.cn</footer><div><div class="top"><div class="carrer"><div class="title"><span class="jsbt">李四</span></div>wrong@edu.cn</div></div><div class="tearchContainer">李四的简介</div></div>''','lxml')
        result=structured_profile(soup,{'张三'});text=result['card']+'\n'+result['body'].get_text()
        self.assertIn('z@edu.cn',text);self.assertNotIn('public@',text);self.assertNotIn('wrong@',text)
        self.assertIsNone(structured_profile(soup,{'王五'}))
    def test_repeated_sections_kept_and_card_binds_identity(self):
        soup=BeautifulSoup('''<table><tr><td><table class="wp_article_list_table"><tr><td class="huizi">张三</td></tr></table><table class="wp_article_list_table"><tr><td>通讯方式：z@edu.cn</td></tr></table><table class="wp_article_list_table"><tr><td><div class="szpost-21"><span class="biaoti1">个人简介</span><p>某大学土木学院，教授/博士研究生导师。</p></div><div class="szpost-21"><span class="biaoti1">论文和专著</span><p>最后一篇论文</p></div></td></tr></table></td></tr></table><footer>admin@edu.cn</footer>''','lxml')
        r=structured_profile(soup,{'张三'});text=r['card']+'\n'+r['body'].get_text('\n',strip=True)
        self.assertIn('最后一篇论文',text);self.assertNotIn('admin@',text)
        self.assertEqual(fields_from_text('张三',text)['title']['value'],'教授')
        self.assertIsNone(structured_profile(soup,{'李四'}))
        soup.select_one('.biaoti1').string='学院新闻'
        self.assertIsNone(structured_profile(soup,{'张三'}))

if __name__=='__main__':unittest.main()
