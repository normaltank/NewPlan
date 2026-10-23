import asyncio,json,hashlib,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from bs4 import BeautifulSoup
from roster_tables import faculty_body,html_rows,image_rows,apply_table_rows
from faculty_navigation import faculty_navigation
from api_pilot import Pilot
from test_api_pilot import FakeAPI
from quality_fields import profile_label_name,fields_from_text

def line(text,x,y,score=1):return {'text':text,'confidence':score,'box':[[x,y],[x+25,y],[x+25,y+15],[x,y+15]]}
def media():
    return {'sha256':hashlib.sha256(b'original').hexdigest(),'directory':'media/table','source_file':'source.png','source_url':'https://x.edu.cn/table.png','height':150,
            'lines':[line('姓名',10,10),line('性别',100,10),line('职称',200,10),line('张三',10,50),line('男',100,50),line('教授',200,50),line('李四',10,100,.7),line('女',100,100),line('讲师',200,100)]}
TABLE='<table><tr><th>姓名</th><th>性别</th><th>职称</th></tr><tr><td>张三</td><td>男</td><td>教授</td></tr></table>'
def html(content):return '<title>师资队伍_学院</title><div id="fontzoom">'+content+'</div>'

class ArtStructures(unittest.IsolatedAsyncioTestCase):
    def test_title_role_label_and_past_appointment(self):
        for text in ['姓名：张三\n职称/职务：某大学教授，博士生导师。','职务/职称：某大学副教授。']:
            self.assertTrue(fields_from_text('张三',text)['title']['value'])
        f=fields_from_text('史正浩','史正浩，博士，副教授。曾任河南大学校聘副教授。现为郑州大学书法学院副教授。')
        self.assertEqual(f['title']['value'],'副教授');self.assertFalse(f['anomalies'])
        self.assertEqual(fields_from_text('张三','曾任某大学校聘副教授。')['title']['value'],'')
    def test_unnamed_opening_requires_matching_person_heading(self):
        text='江苏淮安人，讲师，艺术学博士，师从某教授。'
        self.assertEqual(fields_from_text('魏力',text,identity_bound=True)['title']['value'],'讲师')
        self.assertEqual(fields_from_text('魏力',text)['title']['value'],'')
        self.assertEqual(fields_from_text('魏力','师从某大学教授。',identity_bound=True)['title']['value'],'')
    def test_role_prefix_is_name_but_news_is_not(self):
        self.assertEqual(profile_label_name('美术学院研究生导师——张炯炯'),'张炯炯')
        self.assertEqual(profile_label_name('行业导师-宋华平'),'宋华平')
        self.assertEqual(profile_label_name('行业导师-宋华平来校讲座'),'行业导师-宋华平来校讲座')
    def test_image_rows_bind_columns_and_low_confidence(self):
        rows,issues=image_rows(media());self.assertFalse(issues)
        self.assertEqual([(r['name'],r['fields']['职称']) for r in rows],[('张三','教授'),('李四','讲师')])
        self.assertEqual(rows[1]['confidence'],.7)
    def test_portrait_and_misaligned_headers_not_table(self):
        m=media();m['lines']=m['lines'][3:];self.assertFalse(image_rows(m)[0])
        m=media();m['lines'][0]=line('姓名',10,100);self.assertFalse(image_rows(m)[0])
    def test_missing_name_exposes_unmatched_cells(self):
        m=media();m['lines'].pop(6);rows,issues=image_rows(m)
        self.assertTrue(issues);self.assertLess(len(rows),2)
    def test_news_and_menu_context_not_faculty_body(self):
        for source in ['<title>新闻：师资队伍建设活动</title><div id="fontzoom"><img src="a.png"></div>',
                       '<title>学院新闻</title><nav>师资队伍</nav><div id="fontzoom">'+TABLE+'</div>']:
            self.assertIsNone(faculty_body(BeautifulSoup(source,'lxml')))
    def test_native_table_keeps_rank_but_skips_linked_or_merged_rows(self):
        rows,issues=html_rows(BeautifulSoup('<div>'+TABLE+'</div>','lxml'))
        self.assertEqual(rows[0]['fields']['职称'],'教授');self.assertFalse(issues)
        self.assertFalse(html_rows(BeautifulSoup(TABLE.replace('张三','<a href="p.htm">张三</a>'),'lxml'))[0])
        self.assertTrue(html_rows(BeautifulSoup(TABLE.replace('<td>男','<td rowspan="2">男'),'lxml'))[1])
    async def test_real_pilot_does_ocr_before_text_plan_and_does_not_invent_cv(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'page').mkdir();args=SimpleNamespace(url='https://x.edu.cn/',ocr=True)
            p=Pilot(args,root,FakeAPI({'page_kind':'other','source_qualification':'not_faculty'}));p.read_body_images=AsyncMock(return_value=[media()])
            item={'url':args.url,'loaded_url':args.url,'directory':'page','branch':'师资'}
            await p.roster(item,BeautifulSoup(html('<img src="table.png">'),'lxml'))
            self.assertEqual(p.api.requests,[]);self.assertEqual([o['name'] for o in p.observations],['张三','李四'])
            self.assertTrue(all(not o.get('person_body_path') for o in p.observations))
            self.assertTrue(all(o['table_media']==['media/table'] for o in p.observations))
    async def test_unread_image_retains_issue_not_non_faculty(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'page').mkdir();p=Pilot(SimpleNamespace(url='https://x.edu.cn/',ocr=True),root,FakeAPI({}))
            p.read_body_images=AsyncMock(return_value=[])
            await p.roster({'url':p.args.url,'loaded_url':p.args.url,'directory':'page','branch':'师资'},BeautifulSoup(html('<img src="a.png">'),'lxml'))
            self.assertEqual([i['kind'] for i in p.issues],['faculty_table_unresolved'])
    def test_definition_list_faculty_menu_but_not_people_in_news(self):
        source='<dl><a><dt>师资队伍</dt></a><a href="p.htm"><dd>行业导师-宋华平</dd></a><a href="x.htm"><dd>历史系</dd></a></dl>'
        self.assertEqual([x['name'] for x in faculty_navigation(BeautifulSoup(source,'lxml'),'https://x.edu.cn/')],['宋华平'])
        self.assertEqual(faculty_navigation(BeautifulSoup(source.replace('师资队伍','校友风采'),'lxml'),'https://x.edu.cn/'),[])
    def test_derived_row_tampering_does_not_auto_accept(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'p').mkdir();(root/'p/source.html').write_text(html(TABLE),encoding='utf8')
            row=html_rows(BeautifulSoup('<div>'+TABLE+'</div>','lxml'))[0][0];row['fields']['职称']='讲师';(root/'p/row.json').write_text(json.dumps(row,ensure_ascii=False),encoding='utf8')
            person={'id':'1','name':'张三','profile_url':'','review':{},'observations':[{'source_kind':'html_faculty_table','source_url':'https://x.edu.cn/','table_row_path':'p/row.json'}]}
            items={'1':{'status':'pending'}}
            apply_table_rows({'people':[person],'pages':[{'url':'https://x.edu.cn/','directory':'p'}]},root,items)
            self.assertEqual(items['1']['status'],'pending')

if __name__=='__main__':unittest.main()
