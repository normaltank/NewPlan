import asyncio,hashlib,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from bs4 import BeautifulSoup
from api_pilot import Pilot,title_name
from faculty_navigation import faculty_navigation,explicit_roster_entries
from grouped_roster import grouped_members
from image_profiles import image_biography,verify_observation
from profile_layouts import structured_profile,opening_alias_card
from test_workbench import fixture
from quality_pipeline import build

class NoModel:
    async def ask(self,*a,**k):raise AssertionError('unexpected model call')

class LanguageLayouts(unittest.TestCase):
    def test_opening_bilingual_alias_requires_exact_full_name(self):
        text='丽嘉·米科拉谢韦察（\nLĪGA MIKLAŠEVIČA\n），拉脱维亚籍，外籍专家。'
        self.assertEqual(opening_alias_card(text,{'LĪGA MIKLAŠEVIČA'},'Liga'),'LĪGA MIKLAŠEVIČA')
        self.assertFalse(opening_alias_card('合作者：'+text,{'LĪGA MIKLAŠEVIČA'},'Liga'))
        self.assertFalse(opening_alias_card(text,{'Other Person'},'Liga'))
        self.assertFalse(opening_alias_card(text,{'LĪGA MIKLAŠEVIČA'},'LĪGA MIKLAŠEVIČA'))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'page').mkdir()
            pilot=Pilot(SimpleNamespace(url='https://test.edu.cn/',ocr=False,browser=False),root,NoModel())
            pilot.observe('LĪGA MIKLAŠEVIČA','https://test.edu.cn/liga','https://test.edu.cn/list','外籍教师','directory_link')
            pilot.profile_selector='.body';pilot.profile_selectors=['.body']
            asyncio.run(pilot.profile({'url':'https://test.edu.cn/liga','loaded_url':'https://test.edu.cn/liga','directory':'page','title':'Liga','branch':'外籍教师'},BeautifulSoup('<div class="body">'+text+'</div>','lxml')))
            self.assertTrue((root/'page/body-text.txt').read_text(encoding='utf8').startswith('LĪGA MIKLAŠEVIČA'))
    def test_empty_formatting_anchor_does_not_hide_accented_full_name(self):
        html='<title>外籍教师</title><table><tr><td>拉脱维亚语</td><td><a href="/liga"><span></span></a><a href="/liga"><span>LĪGA MIKLAŠEVIČA</span></a></td></tr></table>'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);pilot=Pilot(SimpleNamespace(url='https://test.edu.cn/',ocr=False,browser=False),root,NoModel())
            pilot.plans['外籍教师']={'page_kind':'directory','source_qualification':'faculty_roster','row_selector':'tr','label_selector':'td:nth-child(2) a span,td:nth-child(2) span','href_selector':'td:nth-child(2) a','branch_selector':'','next_selector':'','next_text':'','pager_selector':''}
            asyncio.run(pilot.roster({'url':'https://test.edu.cn/list','loaded_url':'https://test.edu.cn/list','branch':'外籍教师'},BeautifulSoup(html,'lxml')))
            self.assertEqual([(o['name'],o['profile_url']) for o in pilot.observations],[('LĪGA MIKLAŠEVIČA','https://test.edu.cn/liga')])
    def test_exact_heading_binds_sibling_cv_not_footer(self):
        html='<title>学院</title><div class="in-det"><div class="in-det-bt"><span class="s1">陈可冉</span><p>发布时间：2022-09-26</p></div><div class="in-det-det"><div class="v_news_content">职称：教授。研究方向：文学。论文及完整项目清单</div></div><div class="in-det-lian">下一篇 李四</div></div><footer>public@x.cn</footer>'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'page').mkdir()
            p=Pilot(SimpleNamespace(url='https://test.edu.cn/',ocr=False,browser=False),root,NoModel())
            p.observe('陈可冉','https://test.edu.cn/a','https://test.edu.cn/list','师资','directory_link')
            item={'url':'https://test.edu.cn/a','loaded_url':'https://test.edu.cn/a','directory':'page','title':'学院','branch':'师资'}
            asyncio.run(p.profile(item,BeautifulSoup(html,'lxml')))
            text=(root/'page/body-text.txt').read_text(encoding='utf8')
            self.assertTrue(text.startswith('陈可冉'));self.assertIn('完整项目',text)
            self.assertNotIn('public@',text);self.assertNotIn('下一篇',text)
        self.assertIsNone(structured_profile(BeautifulSoup(html,'lxml'),{'李四'}))
        self.assertIsNone(structured_profile(BeautifulSoup(html.replace('陈可冉','陈可冉参加会议'),'lxml'),{'陈可冉'}))
        alternate=html.replace('陈可冉','陈可冉（CHEN KERAN）').replace('class="v_news_content"','id="vsb_content"')
        self.assertIsNotNone(structured_profile(BeautifulSoup(alternate,'lxml'),{'陈可冉'}))

    def test_mixed_table_keeps_unlinked_names_and_excludes_admin_rows(self):
        html='<title>教职员工-学院</title><div class="v_news_content"><table><tr><th>专业</th><th>教职员工</th></tr><tr><td>阿尔巴尼亚语</td><td><a href="/a">陈逢华</a>&nbsp; &nbsp;靳乔&nbsp; &nbsp;<a href="/b">柯静</a>&nbsp;马赛</td></tr><tr><td>办公室</td><td>王五</td></tr></table></div>'
        rows,excluded,errors=grouped_members(BeautifulSoup(html,'lxml'),'https://test.edu.cn/list')
        self.assertEqual([r['name'] for r in rows],['陈逢华','柯静','靳乔','马赛'])
        self.assertEqual(len(excluded),1);self.assertFalse(errors)
        self.assertFalse(grouped_members(BeautifulSoup(html.replace('教职员工-学院','学生名单'),'lxml'),'https://test.edu.cn/list')[0])
        html=html.replace('class="v_news_content"','id="vsb_content"')
        with tempfile.TemporaryDirectory() as tmp:
            store,key=fixture(Path(tmp));root=Path(store.job(key)['run_dir']);(root/'list').mkdir()
            (root/'list/source.html').write_text(html,encoding='utf8')
            pilot=Pilot(SimpleNamespace(url='https://test.edu.cn/',ocr=False,browser=False),root,NoModel())
            pilot.plans['教职员工']={'page_kind':'name_text','source_qualification':'faculty_roster','body_selector':'#vsb_content table','row_selector':'','label_selector':'','href_selector':'','branch_selector':'','next_selector':'','next_text':'','pager_selector':''}
            item={'url':'https://test.edu.cn/list','loaded_url':'https://test.edu.cn/list','directory':'list','branch':'教职员工','title':'教职员工-学院'}
            asyncio.run(pilot.roster(item,BeautifulSoup(html,'lxml')))
            # Preserve a bad model observation from an earlier run as an
            # automatically excluded record, with its saved office-row proof.
            pilot.observe('王五','',item['url'],'教职员工','rich_roster','王五')
            for fn,value in [('pages',[item]),('observations',pilot.observations),('roster-pages',pilot.rosters),('issues',pilot.issues)]:
                (root/(fn+'.json')).write_text(json.dumps(value,ensure_ascii=False),encoding='utf8')
            build(store,key,force=True);people=store.catalog(key)['people']
            self.assertEqual({p['name'] for p in people},{'陈逢华','柯静','靳乔','马赛','王五'})
            for p in people:
                if p['name']=='王五':
                    self.assertEqual(p['review']['status'],'excluded');self.assertTrue(p['review']['source_exclusions']);continue
                if not p['profile_url']:
                    self.assertEqual(p['review']['status'],'auto_accepted');self.assertEqual(p['review']['material_status'],'roster_only')

    def test_category_labels_are_entries_not_people(self):
        for value in ('教职员工','客座教授','外籍教师','名师风采'):self.assertIsNone(title_name(value))
        soup=BeautifulSoup('<dl><dt>师资队伍</dt><dd><a href="/list">教职员工</a></dd><dd><a href="/feature">名师风采</a></dd><dd><a href="/a">张三</a></dd></dl>','lxml')
        self.assertEqual([x['name'] for x in faculty_navigation(soup,'https://test.edu.cn/')],['张三'])
        self.assertEqual(explicit_roster_entries(soup,'https://test.edu.cn/')[0]['url'],'https://test.edu.cn/list')
        self.assertEqual(len(explicit_roster_entries(soup,'https://test.edu.cn/')),1)

    def test_image_preview_cannot_truncate_delivered_email(self):
        with tempfile.TemporaryDirectory() as tmp:
            store,key=fixture(Path(tmp));root=Path(store.job(key)['run_dir'])
            text='张三，教授。研究领域：文学翻译与英语教学。邮箱：person@example.com'
            (root/'page/body-text.txt').write_text(text,encoding='utf8')
            obs=json.loads((root/'observations.json').read_text())
            obs[0].update(source_kind='image_person_card',evidence=text[:-1])
            (root/'observations.json').write_text(json.dumps(obs),encoding='utf8')
            build(store,key,force=True)
            self.assertEqual(store.catalog(key)['people'][0]['review']['fields']['email'],'person@example.com')

    def test_image_identity_source_hash_and_uncertain_email(self):
        text='张三，教授，英语教育专业。\n开设课程：英语阅读。\n研究领域：文学翻译及语法教学。\n联系方式：broken163.com'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'media').mkdir();(root/'page').mkdir()
            (root/'media/source.png').write_bytes(b'original-image')
            (root/'media/person.txt').write_text(text,encoding='utf8')
            (root/'page/source.html').write_text('<div class="body"><img src="/photo.png"></div>',encoding='utf8')
            media={'directory':'media','source_file':'source.png','sha256':hashlib.sha256(b'original-image').hexdigest(),'source_url':'https://test.edu.cn/photo.png','text':text,'lines':[{'text':x,'confidence':.99} for x in text.splitlines()]}
            cat={'media':[media],'pages':[{'url':'https://test.edu.cn/list','directory':'page'}],'rosters':[{'url':'https://test.edu.cn/list','source_qualification':'faculty_roster'}]}
            o={'name':'张三','person_image':'media','person_body_path':'media/person.txt','source_url':'https://test.edu.cn/list','image_body_selector':'.body'}
            self.assertEqual(image_biography(media)['name'],'张三')
            self.assertIn('格式不完整',verify_observation(cat,root,o)[0])
            ambiguous=text.replace('broken163.com','1eejian@163.com')
            media.update(text=ambiguous,lines=[{'text':x,'confidence':.99} for x in ambiguous.splitlines()])
            (root/'media/person.txt').write_text(ambiguous,encoding='utf8')
            self.assertIn('易混淆',verify_observation(cat,root,o)[0])
            media.update(text=text,lines=[{'text':x,'confidence':.99} for x in text.splitlines()])
            (root/'media/person.txt').write_text(text.replace('张三','李四'),encoding='utf8')
            self.assertIn('校验失败',verify_observation(cat,root,o)[0])
            self.assertIn('姓名',verify_observation(cat,root,{**o,'name':'李四'})[0])
            self.assertIsNone(image_biography({**media,'lines':[{'text':'教师合影','confidence':.99}]}))

if __name__=='__main__':unittest.main()
