import tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from bs4 import BeautifulSoup
from api_pilot import Pilot
from faculty_navigation import faculty_navigation
from test_api_pilot import FakeAPI

HTML='''<ul><li><a href="/all/list.htm">师资队伍</a><ul>
<li><a href="/lsx/list.htm">历史系</a></li>
<li><a href="/fxx/list.htm">法律系</a></li>
<li><a href="/institute/list.htm">张謇研究院</a></li>
<li><a href="/center/list.htm">文化中心</a></li>
<li><a href="/11366/list.htm">教职工名录</a></li>
<li><a href="/hiring/list.htm">人才引进</a></li>
<li><a href="/famous/list.htm">名师风采</a></li>
<li><a href="/groups/list.htm">教研室设置</a></li>
<li><a href="/admin/list.htm">行政</a></li>
<li><a href="/postdoc/list.htm">博士后</a></li>
</ul></li></ul><ul class="people"><li><a href="/zhang/page.htm">张三</a></li></ul>'''

class FacultyNavigationRegressionTests(unittest.IsolatedAsyncioTestCase):
    def test_mixed_hierarchical_specialties_are_not_teacher_names(self):
        source='<li><a>师资队伍</a><ul><li><a href="/art">美术学</a><ul><li><a href="/paint">油画</a></li></ul></li><li><a href="/calligraphy">书法学</a></li><li><a href="/design">视觉传达设计</a></li></ul></li>'
        self.assertEqual(faculty_navigation(BeautifulSoup(source,'lxml'),'https://test.edu.cn/'),[])
    def test_organizational_faculty_menu_is_not_people(self):
        self.assertEqual(faculty_navigation(BeautifulSoup(HTML,'lxml'),'https://test.edu.cn/all/list.htm'),[])

    def test_person_menu_preserves_extended_names_and_latin(self):
        names=['沙菁㛃','𠮷田太郎','Simone Baldi','José García','王院','张学']
        html='<li><a>团队教师</a><ul>'+''.join(f'<li><a href="/{i}/list.htm">{n}</a></li>' for i,n in enumerate(names))+'</ul></li>'
        self.assertEqual([p['name'] for p in faculty_navigation(BeautifulSoup(html,'lxml'),'https://test.edu.cn/')],names)

    async def test_roster_discovered_branches_are_not_overwritten_as_profiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Pilot(SimpleNamespace(url='https://test.edu.cn/',max_pages=100),Path(tmp),FakeAPI({}))
            for branch in ('lsx','fxx'):p.register(f'https://test.edu.cn/{branch}/list.htm','roster',branch)
            p.plans['all']={'page_kind':'directory','source_qualification':'faculty_roster','row_selector':'.people li','label_selector':'a','href_selector':'a','body_selector':'','next_selector':'','next_text':'','pager_selector':'','branch_selector':''}
            await p.roster({'url':'https://test.edu.cn/all/list.htm','loaded_url':'https://test.edu.cn/all/list.htm','branch':'all'},BeautifulSoup(HTML,'lxml'))
            self.assertEqual([o['name'] for o in p.observations],['张三'])
            for branch in ('lsx','fxx'):self.assertEqual(p.targets[f'https://test.edu.cn/{branch}/list.htm']['kind'],'roster')

if __name__=='__main__':unittest.main()
