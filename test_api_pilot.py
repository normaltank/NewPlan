"""Offline tests for false success and model-generated pagination failure cases."""
import tempfile
import unittest
import io
import httpx
from PIL import Image,ImageDraw,ImageFont
from pathlib import Path
from types import SimpleNamespace

from bs4 import BeautifulSoup
from api_pilot import Pilot, permission_denied, title_name
from unittest.mock import AsyncMock, patch


class FakeAPI:
    def __init__(self,answer):
        self.answer=answer
        self.requests=[]
    async def ask(self,*args,**kwargs):
        self.requests.append(args)
        return self.answer


class PilotTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_page_keeps_template_and_unchanged_browser_does_not_replan(self):
        with tempfile.TemporaryDirectory() as out:
            p=self.pilot(out,{'body_selector':''});p.args.browser=True
            p.profile_selector='.resume';p.profile_selectors=['.resume']
            (Path(out)/'empty').mkdir();(Path(out)/'real').mkdir()
            empty=BeautifulSoup('<h1>李四</h1><div class="shell"></div>','lxml')
            item={'url':p.args.url,'loaded_url':p.args.url,'directory':'empty'}
            rendered=BeautifulSoup('<h1>李四</h1><div class="shell"><span>»</span></div>','lxml')
            with patch('browser_capture.render_roster',new=AsyncMock(return_value=(rendered,{}))):
                await p.profile(item,empty)
            self.assertEqual(len(p.api.requests),1)
            self.assertEqual(item['body_status'],'not_extracted')
            real={'url':p.args.url+'real','loaded_url':p.args.url+'real','directory':'real'}
            await p.profile(real,BeautifulSoup('<div class="resume">张三，教授。完整正文与研究方向。</div>','lxml'))
            self.assertEqual(len(p.api.requests),1)
            self.assertEqual(real['body_status'],'text_saved')

    def test_role_and_email_suffixes_are_not_part_of_name(self):
        self.assertEqual(title_name('徐一鸣-学术学业导师'),'徐一鸣')
        self.assertEqual(title_name('褚敏捷 （邮箱：test@example.edu）'),'褚敏捷')
        self.assertIsNone(title_name('师资队伍'))
        self.assertEqual(title_name('陈佳佳简介'),'陈佳佳')
        self.assertEqual(title_name('张三个人简介'),'张三')
        self.assertIsNone(title_name('学院简介'))

    async def test_download_category_is_not_a_person_roster(self):
        with tempfile.TemporaryDirectory() as out:
            p=self.pilot(out,{'page_kind':'other','source_qualification':'not_faculty','reason':'下载表格'})
            item={'url':p.args.url,'loaded_url':p.args.url,'branch':'任课教师'}
            await p.roster(item,BeautifulSoup('<li>试卷分析</li>','lxml'))
            self.assertEqual(p.observations,[])
            self.assertEqual(p.issues[0]['kind'],'source_not_faculty_roster')

    async def test_embedded_pdf_full_text_is_preserved(self):
        with tempfile.TemporaryDirectory() as out:
            p=self.pilot(out,{});p.args.ocr=True;p.profile_selector='.resume'
            (Path(out)/'page').mkdir()
            item={'url':p.args.url,'loaded_url':p.args.url,'directory':'page'}
            record={'path':'documents/test','text':'[page 1]\n张宏，教授。完整履历。\n[page 2]\n论文与研究项目。'}
            p.read_profile_pdfs=AsyncMock(return_value=[record])
            await p.profile(item,BeautifulSoup('<div class="resume"><iframe src="viewer?file=x.pdf"></iframe></div>','lxml'))
            self.assertEqual(item['body_status'],'pdf_text_saved')
            self.assertIn('[page 2]',(Path(out)/'page'/'body-text.txt').read_text(encoding='utf8'))

    async def test_image_only_resume_download_ocr_and_evidence(self):
        image=Image.new('RGB',(900,280),'white');draw=ImageDraw.Draw(image)
        font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',32) if Path('C:/Windows/Fonts/msyh.ttc').exists() else ImageFont.truetype('DejaVuSans.ttf',32)
        draw.text((20,30),'Faculty Biography 2026',font=font,fill='black')
        draw.text((20,110),'Research: Chemistry and Materials',font=font,fill='black')
        buf=io.BytesIO();image.save(buf,format='PNG');data=buf.getvalue()
        def respond(request):
            if request.url.path=='/robots.txt':return httpx.Response(404)
            return httpx.Response(200,content=data,headers={'content-type':'image/png'})
        original=httpx.AsyncClient
        with tempfile.TemporaryDirectory() as out:
            p=self.pilot(out,{});p.args.ocr=True;p.profile_selector='.resume'
            (Path(out)/'page').mkdir()
            item={'url':p.args.url,'loaded_url':p.args.url,'directory':'page'}
            with patch('httpx.AsyncClient',side_effect=lambda **kw:original(transport=httpx.MockTransport(respond),**kw)):
                await p.profile(item,BeautifulSoup('<div class="resume"><img src="resume.png"></div>','lxml'))
            self.assertEqual(item['body_status'],'ocr_candidate')
            self.assertEqual(item['image_text_read'],'performed')
            self.assertIn('Chemistry',(Path(out)/'page'/'body-text.txt').read_text(encoding='utf8'))
            self.assertEqual(len(p.media),1)
            self.assertTrue((Path(out)/p.media[0]['directory']/p.media[0]['source_file']).is_file())
            self.assertTrue(any(i['kind']=='ocr_review_required' for i in p.issues))

    def test_same_host_http_and_https_share_target(self):
        with tempfile.TemporaryDirectory() as out:
            p=self.pilot(out,{})
            p.register('http://example.edu/person','profile','教师')
            p.register('https://example.edu/person','profile','教师')
            self.assertEqual(len(p.targets),2)
    def pilot(self,path,answer):
        args=SimpleNamespace(url='https://example.edu/college/',university='大学',college='学院',max_pages=20)
        return Pilot(args,Path(path),FakeAPI(answer))

    async def test_empty_discovery_is_unknown_not_no_faculty(self):
        with tempfile.TemporaryDirectory() as out:
            p=self.pilot(out,{'entry_link_ids':[],'status':'no_entry_found'})
            await p.discover({'url':p.args.url,'loaded_url':p.args.url,'title':'学院'},BeautifulSoup('<p>欢迎访问</p>','lxml'))
            self.assertEqual(p.observations,[])
            self.assertEqual(p.issues[0]['kind'],'faculty_entry_not_found')

    def test_permission_message_is_content_failure(self):
        soup=BeautifulSoup('<title>系统提示</title><p>您无权访问此页面</p>','lxml')
        self.assertTrue(permission_denied(soup,'https://example.edu/auth.htm'))

    async def test_image_only_profile_is_not_counted_as_text(self):
        with tempfile.TemporaryDirectory() as out:
            p=self.pilot(out,{})
            p.profile_selector='.resume'
            (Path(out)/'page').mkdir()
            item={'url':p.args.url,'loaded_url':p.args.url,'directory':'page'}
            await p.profile(item,BeautifulSoup('<div class="resume"><img src="resume.png"></div>','lxml'))
            self.assertEqual(item['body_status'],'no_text')
            self.assertEqual(item['image_text_read'],'not_performed')
            self.assertEqual(p.issues[0]['kind'],'profile_without_text')

    async def test_generated_non_source_name_is_rejected(self):
        with tempfile.TemporaryDirectory() as out:
            p=self.pilot(out,{'people':[{'name':'张宏','evidence':'张 宏','link_id':None},
                                       {'name':'虚构人','evidence':'虚构人','link_id':None}]})
            await p.extract_names('test','张 宏',[],p.args.url,'教师','text')
            self.assertEqual([o['name'] for o in p.observations],['张宏'])
            self.assertEqual(p.issues[0]['kind'],'name_evidence_rejected')

    async def test_relative_next_link_triggers_replan(self):
        with tempfile.TemporaryDirectory() as out:
            fixed={'page_kind':'directory','row_selector':'li','label_selector':'a',
                   'href_selector':'a','body_selector':'','next_selector':'a.Next','next_text':'下页','pager_selector':'#pager'}
            p=self.pilot(out,fixed)
            p.plans['教师']={**fixed,'next_selector':'a.Next[href*="list/"]'}
            item={'url':'https://example.edu/college/list/2.htm','loaded_url':'https://example.edu/college/list/2.htm','branch':'教师'}
            soup=BeautifulSoup('<ul><li><a href="../people/1.htm">张宏</a></li></ul><div id="pager">共3条 2/3</div><a class="Next" href="1.htm">下页</a>','lxml')
            await p.roster(item,soup)
            self.assertEqual(len(p.api.requests),1)
            self.assertIn('https://example.edu/college/list/1.htm',p.targets)
            self.assertEqual(len(p.observations),1)
            self.assertTrue(p.issues[0]['fixed'])


if __name__=='__main__':
    unittest.main()
