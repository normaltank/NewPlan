import unittest
import httpx
from bs4 import BeautifulSoup
from collection_guards import branch_scope,robots_response

class BranchTests(unittest.TestCase):
    def test_broad_navigation_selector_keeps_faculty_and_rejects_other_menus(self):
        soup=BeautifulSoup('''<ul><li><a>学院概况</a><ul class="sub-menu"><li><a href="/old">历任领导</a></li></ul></li>
        <li><a>师资队伍</a><ul class="sub-menu"><li><a href="/dept">基础教研室</a></li></ul></li>
        <li><a>人才培养</a><ul class="sub-menu"><li><a href="/mentor">导师简介</a></li><li><a href="/enroll">招生信息</a></li></ul></li></ul>''','html.parser')
        results={a['href']:branch_scope(a)[0] for a in soup.select('.sub-menu a')}
        self.assertEqual(results,{'/old':False,'/dept':True,'/mentor':True,'/enroll':False})
        self.assertIsNone(branch_scope(BeautifulSoup('<a>生态系</a>','html.parser').a)[0])

class RobotsTests(unittest.IsolatedAsyncioTestCase):
    async def test_same_host_https_redirect_reaches_real_robots_status(self):
        seen=[]
        def handler(req):
            seen.append(str(req.url))
            return httpx.Response(301,headers={'location':'https://test.edu.cn/robots.txt'}) if req.url.scheme=='http' else httpx.Response(404)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            r=await robots_response(client,'http://test.edu.cn/robots.txt','test.edu.cn')
        self.assertEqual(r.status_code,404);self.assertEqual(len(seen),2)
    async def test_cross_host_redirect_is_not_requested_and_loop_is_bounded(self):
        seen=[]
        def handler(req):
            seen.append(str(req.url));return httpx.Response(302,headers={'location':'https://other.edu.cn/robots.txt'})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaises(ValueError):await robots_response(client,'https://test.edu.cn/robots.txt','test.edu.cn')
        self.assertEqual(len(seen),1)
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req:httpx.Response(301,headers={'location':'/robots.txt'}))) as client:
            with self.assertRaises(ValueError):await robots_response(client,'https://test.edu.cn/robots.txt','test.edu.cn')

if __name__=='__main__':unittest.main()
