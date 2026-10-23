import tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from bs4 import BeautifulSoup
from api_pilot import Pilot
from faculty_navigation import explicit_roster_entries
from test_api_pilot import FakeAPI

class HtmlRosterRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_roster_survives_model_omission(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Pilot(SimpleNamespace(url='https://test.edu.cn/',university='大学',college='体育学院'),Path(tmp),FakeAPI({'entry_link_ids':[],'status':'no_entry_found'}))
            html='<li><a>高水平运动队</a><ul><li><a href="/coaches/list.htm">教练员情况</a></li><li><a href="/athletes/list.htm">运动员情况</a></li></ul></li>'
            await p.discover({'url':p.args.url,'loaded_url':p.args.url,'title':'学院'},BeautifulSoup(html,'lxml'))
            self.assertEqual(p.targets[p.args.url+'coaches/list.htm']['kind'],'roster')
            self.assertNotIn(p.args.url+'athletes/list.htm',p.targets)
            self.assertFalse(any(i['kind']=='faculty_entry_not_found' for i in p.issues))

    def test_download_and_foreign_links_are_not_added(self):
        html='<li><a>下载中心</a><ul><li><a href="/forms">教师名录</a></li></ul></li><a href="https://other.edu.cn/list">教练员名单</a><a href="/news">教师队伍建设新闻</a>'
        self.assertEqual(explicit_roster_entries(BeautifulSoup(html,'lxml'),'https://test.edu.cn/'),[])

    async def test_qualified_group_article_reads_rows_and_keeps_old_roster_warning(self):
        for qualified in [True,False]:
            with self.subTest(qualified=qualified),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);(root/'page').mkdir()
                p=Pilot(SimpleNamespace(url='https://test.edu.cn/'),root,FakeAPI({}));url=p.args.url+'article';source=p.args.url+'list'
                p.issues=[{'kind':'non_person_directory_entry','url':source,'document_url':url}]
                p.rosters=[{'url':source,'source_qualification':'faculty_roster' if qualified else 'uncertain'}]
                html='<div class="wp_articlecontent"><p>2014 年教练员情况</p><table><tr><th>姓名</th><th>职称</th><th>性别</th></tr><tr><td>常 生</td><td>教授</td><td>男</td></tr><tr><td>刘 琪</td><td>中级教练</td><td>男</td></tr></table></div>'
                (root/'page/source.html').write_text(html,encoding='utf8')
                await p.document({'url':url,'directory':'page','title':'高水平运动队教练员情况','branch':'教练员情况'},BeautifulSoup(html,'lxml'))
                self.assertEqual([o['name'] for o in p.observations],['常生','刘琪'] if qualified else [])
                if qualified:
                    self.assertTrue(all(o['historical_roster'] for o in p.observations))
                    for o in p.observations:self.assertIn('姓名：', (root/o['person_body_path']).read_text(encoding='utf8'))
                    self.assertFalse(any(i['kind']=='document_without_supported_attachment' for i in p.issues))

if __name__=='__main__':unittest.main()
