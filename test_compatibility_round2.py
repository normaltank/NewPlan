import unittest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock,patch
from bs4 import BeautifulSoup
from multi_profile_sections import split_biographies
from quality_fields import fields_from_text
from compatible_http import CompatibleHttpClient
from faculty_navigation import faculty_navigation
import test_api_pilot as pilot_fixture

class SectionTests(unittest.TestCase):
    def test_multiple_people_keep_full_sections_without_next_person(self):
        soup=BeautifulSoup('<div><p><b>张三</b></p><p>男，中共党员。博士研究生学历，教授。曾任学院副院长。</p><p>研究方向：材料。项目、论文完整原文。</p><p><strong>李四</strong></p><p>女，硕士研究生学历，副教授。研究领域为计算机。</p><p>邮箱 li@test.edu.cn</p></div>','html.parser')
        rows=split_biographies(soup.div)
        self.assertEqual([r['name'] for r in rows],['张三','李四'])
        self.assertNotIn('李四',rows[0]['text']);self.assertIn('项目、论文完整原文',rows[0]['text'])
        self.assertEqual(fields_from_text('张三',rows[0]['text'])['title']['value'],'教授')
        self.assertEqual(fields_from_text('李四',rows[1]['text'])['email']['value'],'li@test.edu.cn')

    def test_a_list_of_names_or_image_cv_is_not_a_complete_biography(self):
        for html in ('<p><b>张三</b></p><p><b>李四</b></p>','<p><b>张三</b></p><p>男，个人简历与论文项目详见下图。<img src="a.png"></p><p><b>李四</b></p>'):
            self.assertEqual(split_biographies(BeautifulSoup(html,'html.parser')),[])

    def test_professor_level_engineer_is_one_title(self):
        f=fields_from_text('张三','张三\n男，中共党员。硕士研究生学历，教授级高级工程师。曾任讲师。')
        self.assertEqual(f['title']['value'],'教授级高级工程师')

    def test_layout_fragments_and_equivalent_titles_do_not_create_conflicts(self):
        cases=[('一、个人简介\n张三\n，理学博士，副\n教授\n。','副教授'),
               ('张三 教授级高工\n一、个人简介\n张三，博士，教授级高级工程师。','教授级高级工程师'),
               ('张三 研究员\n一、个人简介\n张三，博士，研究员，特聘教授，博士生导师。','研究员、特聘教授')]
        for text,title in cases:
            f=fields_from_text('张三',text)
            self.assertEqual(f['title']['value'],title)
            self.assertNotIn('同等依据的职称不一致',f['anomalies'])
        f=fields_from_text('张三','张三 讲师\n张三，博士，副教授。')
        self.assertIn('同等依据的职称不一致',f['anomalies'])

    def test_superset_does_not_borrow_visiting_supervisors_rank(self):
        for text in ['张三，男，工学博士，副教授，硕士生导师，于南京航空航天\n大学获学位，2019年跟随李四教授进行访问研究。',
                     '张三，男，工学博士，副教授，2019年跟随李四教授进行访问研究。']:
            f=fields_from_text('张三',text)
            self.assertEqual(f['title']['value'],'副教授')
            self.assertEqual(f['anomalies'],[])

    def test_teacher_submenu_does_not_pick_students_or_ordinary_navigation(self):
        html='<ul><li><a>团队教师</a><ul><li><a href="/a">张三</a></li><li><a href="/b">李四</a></li><li><a href="/prof">教授</a></li></ul></li><li><a>学生成员</a><ul><li><a href="/c">王五</a></li></ul></li></ul>'
        found=faculty_navigation(BeautifulSoup(html,'html.parser'),'https://test.edu.cn/list')
        self.assertEqual([x['name'] for x in found],['张三','李四'])

class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_tls_fallback_is_host_scoped_and_not_a_status_bypass(self):
        c=CompatibleHttpClient();c.fallback.send_request=AsyncMock(return_value='verified-response')
        with patch('crawlee.http_clients.ImpitHttpClient.send_request',new_callable=AsyncMock) as primary:
            primary.side_effect=RuntimeError('SelectedUnusableCipherSuiteForVersion')
            self.assertEqual(await c.send_request('https://a.edu.cn/robots.txt'),'verified-response')
            self.assertEqual(await c.send_request('https://a.edu.cn/list'),'verified-response')
            self.assertEqual(primary.await_count,1)
            primary.side_effect=RuntimeError('403 forbidden')
            with self.assertRaises(RuntimeError):await c.send_request('https://b.edu.cn/list')
            self.assertEqual(c.fallback.send_request.await_count,2)
        await c.cleanup()

class CollectorTests(unittest.IsolatedAsyncioTestCase):
    async def test_teacher_submenu_promotes_profile_without_roster_model_call(self):
        with tempfile.TemporaryDirectory() as out:
            p=pilot_fixture.PilotTests.pilot(self,out,{})
            p.profile_selector='.resume';p.args.ocr=False;p.args.browser=False
            page=Path(out)/'page';page.mkdir()
            url='https://example.edu/zhang'
            p.register(url,'roster','团队教师')
            item={'url':url,'loaded_url':url,'title':'张三','branch':'团队教师','directory':'page'}
            soup=BeautifulSoup('<ul><li><a>团队教师</a><ul><li><a href="/zhang">张三</a></li><li><a href="/li">李四</a></li></ul></li></ul><div class="resume">张三，教授。研究方向与全部项目、论文原文完整保存。</div>','html.parser')
            await p.roster(item,soup)
            self.assertEqual(item['kind'],'profile')
            self.assertEqual(item['body_status'],'text_saved')
            self.assertIn('全部项目',(page/'body-text.txt').read_text(encoding='utf8'))
            self.assertEqual(p.targets[url]['kind'],'profile')
            self.assertEqual(p.targets['https://example.edu/li']['kind'],'profile')
            self.assertEqual(p.api.requests,[])

if __name__=='__main__':unittest.main()
