import tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from bs4 import BeautifulSoup
from api_pilot import Pilot
from quality_fields import profile_card,fields_from_text
from test_api_pilot import FakeAPI

class ProfileHeadingRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_rank_in_article_heading_survives_body_selector(self):
        for name,rank,body in [('张梦露','副教授','张梦露，博士。研究方向：环境科学。'),('吴春山','高级工程师','')]:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);(root/'page').mkdir()
                p=Pilot(SimpleNamespace(url='https://test.edu.cn/'),root,FakeAPI({}));p.profile_selector='.wp_articlecontent'
                p.observe(name,p.args.url+'person',p.args.url+'roster','师资','directory_link',name)
                item={'url':p.args.url+'person','loaded_url':p.args.url+'person','directory':'page'}
                soup=BeautifulSoup(f'<div class="article"><h1 class="arti_title">{name} {rank}</h1><span>浏览次数：1234</span><div class="wp_articlecontent">{body}</div></div><footer>公共邮箱 office@test.edu.cn</footer>','lxml')
                await p.profile(item,soup)
                saved=(root/'page/body-text.txt').read_text(encoding='utf8')
                self.assertEqual(fields_from_text(name,saved)['title']['value'],rank)
                self.assertIn(body,saved);self.assertNotIn('1234',saved);self.assertNotIn('office@',saved)
                if not body:self.assertEqual(item['body_status'],'card_only')

    def test_title_only_page_delivers_fields_without_claiming_a_biography(self):
        from test_material_delivery import DeliveryTests
        case=DeliveryTests();case.setUp()
        try:
            case.body('page','张三 教授',None);case.pages[0]['body_status']='card_only'
            person=case.assess()['people'][0]
            self.assertEqual(person['review']['status'],'auto_accepted')
            self.assertEqual(person['review']['fields']['title'],'教授')
            self.assertEqual(person['review']['fields']['biography'],'')
            self.assertEqual(person['review']['fields']['missing']['biography'],'not_read')
            self.assertEqual(person['review']['material_status'],'profile_card_only')
        finally:case.tearDown()

    def test_other_person_and_news_title_are_not_personal_rank(self):
        for heading in ['李四 教授','张三教授获奖','张三与李四教授的研究','学校教授名单']:
            soup=BeautifulSoup(f'<div class="article"><h1 class="arti_title">{heading}</h1><div class="wp_articlecontent"></div></div>','lxml')
            self.assertEqual(profile_card(soup,soup.select_one('.wp_articlecontent'),{'张三'}),'')

    def test_abbreviated_heading_does_not_override_existing_biography_rank(self):
        soup=BeautifulSoup('<div class="article"><h1 class="arti_title">张三 教授</h1><div class="wp_articlecontent">张三，特聘教授，研究环境科学。</div></div>','lxml')
        body=soup.select_one('.wp_articlecontent')
        self.assertEqual(profile_card(soup,body,{'张三'}),'')
        self.assertEqual(fields_from_text('张三',body.get_text())['title']['value'],'特聘教授')

if __name__=='__main__':unittest.main()
