import unittest
import tempfile
import json
import io
from pathlib import Path
from bs4 import BeautifulSoup
from quality_fields import fields_from_text, pdf_table_rows, profile_card, administrative_only
from quality_pipeline import build
from workbench_store import Store
from fastapi.testclient import TestClient
from workbench import make_app


class QualityTests(unittest.TestCase):
    def test_labelled_wrapped_email_and_conference_marker(self):
        self.assertEqual(fields_from_text('张三', '联系邮箱：\nlldh987\n@\nshnu.\nedu.cn')['email']['value'], 'lldh987@shnu.edu.cn')
        self.assertEqual(fields_from_text('张三', '邮箱：\nxuejingya\n3679@163.\ncom\n◆主要学习工作经历')['email']['value'], 'xuejingya3679@163.com')
        f = fields_from_text('张三', 'Email: zhang@test.edu.cn\n论文 Workshop (SRW@ACL2023). （EI会议）')
        self.assertEqual(f['anomalies'], [])
        self.assertIn('邮箱格式不完整', fields_from_text('张三', '邮箱 yho0704@163.')['anomalies'])
        self.assertEqual(fields_from_text('张三', '作者 xue\n3679@163.\ncom')['email']['value'], '')

    def test_current_title_after_degree_and_split_named_title(self):
        self.assertEqual(fields_from_text('张志丹', '张志丹，哲学博士，法学博士后。上海师范大学马克思主义学院教授，博士生导师。')['title']['value'], '教授')
        f = fields_from_text('武亚运', '【简 介】\n武亚运\n，\n讲师\n，\n复旦大学法学博士，美国某大学访问学者，\n某研究中心\n研究员。')
        self.assertEqual(f['title']['value'], '讲师')
        self.assertEqual(f['anomalies'], [])
        self.assertEqual(fields_from_text('张三', '张三，博士。曾任某大学教授。导师为某大学教授。')['title']['value'], '')
        self.assertEqual(fields_from_text('高某', '高某，博士，教授，副院长。工作经历2021.07--某大学学院教授；2016.09--2021.06某大学学院副教授。')['title']['value'], '教授')
        self.assertEqual(fields_from_text('邵某', '邵某，讲师，研究道路安全。现任校聘副教授。')['title']['value'], '校聘副教授')
        f = fields_from_text('邵雍', '邵雍，某大学特聘教授、博士生导师；某学院兼职教授。')
        self.assertEqual(f['title']['value'], '特聘教授')
        self.assertEqual(f['anomalies'], [])

    def test_clerical_biography_requires_affiliation_review_but_dual_role_can_pass(self):
        self.assertTrue(administrative_only('汪某，任教学干事，负责日常教学工作。',''))
        self.assertTrue(administrative_only('何某，硕士研究生毕业，现任办公室科研秘书。',''))
        self.assertFalse(administrative_only('李某，副教授，兼任教学秘书。','副教授'))
        self.assertFalse(administrative_only('李某，教学秘书，主讲大学语文课程。',''))
        self.assertFalse(administrative_only('李某，专任教师，邮箱li@test.edu.cn。',''))

    def test_profile_heading_suffix_is_corrected_with_evidence_and_original_is_unchanged(self):
        from test_workbench import fixture
        with tempfile.TemporaryDirectory() as temp:
            store,key=fixture(Path(temp));root=Path(store.job(key)['run_dir'])
            (root/'page/body-text.txt').write_text('张三，教授，博士。研究方向：材料科学与催化。完整研究与教学经历。',encoding='utf8')
            pages=json.loads((root/'pages.json').read_text(encoding='utf8'));pages[0]['title']='张三简介'
            (root/'pages.json').write_text(json.dumps(pages),encoding='utf8')
            obs=json.loads((root/'observations.json').read_text(encoding='utf8'));obs.append({**obs[0],'name':'张三简介','evidence':'张三简介'})
            raw=json.dumps(obs);(root/'observations.json').write_text(raw,encoding='utf8');build(store,key)
            c=store.catalog(key);self.assertEqual(sum(p['review']['status']=='auto_accepted' for p in c['people']),1)
            self.assertEqual(sum(p['review']['status']=='duplicate' for p in c['people']),1)
            self.assertTrue(all(p['review']['fields']['name']=='张三' for p in c['people']))
            self.assertEqual((root/'observations.json').read_text(encoding='utf8'),raw)

    def test_name_only_observation_does_not_block_verified_profile_or_merge_by_name(self):
        from test_workbench import fixture
        with tempfile.TemporaryDirectory() as temp:
            store,key=fixture(Path(temp));root=Path(store.job(key)['run_dir'])
            text='张三，教授，博士。研究方向：材料科学与催化。完整研究工作与教学经历。'
            (root/'page/body-text.txt').write_text(text,encoding='utf8')
            obs=json.loads((root/'observations.json').read_text(encoding='utf8'))
            obs.append({'name':'张三','profile_url':'','source_url':'https://test.edu.cn/overview','evidence':'张三'})
            (root/'observations.json').write_text(json.dumps(obs),encoding='utf8');build(store,key)
            people=store.catalog(key)['people'];self.assertEqual(len(people),2)
            self.assertEqual(next(p for p in people if p['profile_url'])['review']['status'],'auto_accepted')
            self.assertEqual(next(p for p in people if not p['profile_url'])['review']['status'],'pending')
            obs.append({'name':'张三','profile_url':'https://test.edu.cn/zhang2','source_url':'https://test.edu.cn/list','evidence':'张三'})
            (root/'observations.json').write_text(json.dumps(obs),encoding='utf8');build(store,key)
            self.assertTrue(all(p['review']['status']=='pending' for p in store.catalog(key)['people']))
            (root/'second').mkdir();(root/'second/body-text.txt').write_text('张三，讲师。研究方向：医学、病理学与公共卫生。完整教学与科研工作经历。',encoding='utf8')
            pages=json.loads((root/'pages.json').read_text(encoding='utf8'));pages.append({'url':'https://test.edu.cn/zhang2','directory':'second','title':'张三','body_status':'text_saved','body_chars':40})
            (root/'pages.json').write_text(json.dumps(pages),encoding='utf8')
            (root/'observations.json').write_text(json.dumps(obs),encoding='utf8');build(store,key)
            self.assertTrue(all(p['review']['status']=='pending' for p in store.catalog(key)['people']))

    def test_teaching_heading_is_not_professor(self):
        f = fields_from_text('马娟', '教育经历\n工作经历\n教授课程\n会计学\n社会兼职')
        self.assertEqual(f['title']['value'], '')

    def test_explicit_clinical_title_beats_historical_mentions(self):
        f = fields_from_text('王萌', '姓名：王萌\n职称：主治医师\n个人简介：曾随张教授学习。邮箱：wang@ntu.edu.cn')
        self.assertEqual(f['title']['value'], '主治医师')
        self.assertEqual(f['email']['value'], 'wang@ntu.edu.cn')

    def test_pdf_row_keeps_dual_titles_and_page_owner(self):
        rows = pdf_table_rows('[page 2]\n姓名 性别 出生年月 职称 学科方向 研究方向 邮箱\n史加海 男 1971.08 主任医师，教授 护理 临床护理 sjh@ntu.edu.cn\n严海鸥 女 1977.11 主任护师 护理 慢病 yho0704@163.')
        self.assertEqual([r['name'] for r in rows], ['史加海', '严海鸥'])
        self.assertEqual(rows[0]['page'], 2)
        self.assertEqual(fields_from_text('史加海', rows[0]['text'])['title']['value'], '主任医师、教授')
        self.assertIn('邮箱格式不完整', fields_from_text('严海鸥', rows[1]['text'])['anomalies'])

    def test_person_card_is_added_without_navigation(self):
        soup = BeautifulSoup('<nav>教授 客座教授</nav><div class="topleft"><h1 class="arti_title">马娟</h1><p>副教授</p><p>邮箱：ma@ntu.edu.cn</p></div><div class="resume">教育经历</div>', 'lxml')
        result = profile_card(soup)
        self.assertIn('ma@ntu.edu.cn', result)
        self.assertNotIn('客座教授', result)

    def test_historical_positions_do_not_override_introduction(self):
        f = fields_from_text('张宏', '张宏，副教授，博士。\n教育经历\n2018年任讲师。导师为李教授。')
        self.assertEqual(f['title']['value'], '副教授')

    def test_chemical_at_sign_is_not_an_invalid_email(self):
        self.assertEqual(fields_from_text('张宏','张宏，教授。研究 Au@SiO2 和 Ni@Pd。')['anomalies'],[])

    def test_pdf_reordered_bio_and_layout_email(self):
        f=fields_from_text('张宏','主讲课程\n工程力学\n主要成果\n论文 30 篇\n基本情况\n张宏，教授，硕士生导师。邮箱：zhang@qq.co\u2006m')
        self.assertEqual(f['title']['value'],'教授')
        self.assertEqual(f['email']['value'],'zhang@qq.com')

    def test_mixed_pdf_keeps_native_text_and_ocr_image_text(self):
        from PIL import Image, ImageDraw, ImageFont
        from pypdf import PdfReader,PdfWriter
        from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject,ArrayObject
        from ocr_media import read_pdf
        image=Image.new('RGB',(800,250),'white')
        font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',32) if Path('C:/Windows/Fonts/arial.ttf').exists() else ImageFont.truetype('DejaVuSans.ttf',32)
        ImageDraw.Draw(image).text((25,25),'Biography hidden in image 2026',fill='black',font=font)
        data=io.BytesIO();image.save(data,format='PDF')
        writer=PdfWriter();writer.add_page(PdfReader(io.BytesIO(data.getvalue())).pages[0]);page=writer.pages[0]
        page['/Resources'][NameObject('/Font')]=DictionaryObject({NameObject('/FTest'):writer._add_object(DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')}))})
        stream=DecodedStreamObject();stream.set_data(b'BT /FTest 12 Tf 25 20 Td (Native layer longer than forty characters must not prevent image OCR.) Tj ET')
        page[NameObject('/Contents')]=ArrayObject([page.raw_get('/Contents'),writer._add_object(stream)])
        output=io.BytesIO();writer.write(output)
        with tempfile.TemporaryDirectory() as temp:
            result=read_pdf(output.getvalue(),Path(temp))
            self.assertEqual(result['pages'][0]['method'],'hybrid_ocr')
            self.assertIn('Native layer',result['text'])
            self.assertIn('Biography',result['pages'][0]['ocr_text'])

    def test_automatic_export_manual_override_and_stale_input(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);store=Store(root/'test.db')
            batch=store.create_batch('test',[{'university':'测试大学','college':'测试学院','url':'https://test.edu.cn/'}])
            key=store.listing()['jobs'][0]['id'];(root/'page').mkdir()
            (root/'page/body-text.txt').write_text('张宏，教授，博士。研究方向：材料。邮箱：zhang@test.edu.cn',encoding='utf-8')
            (root/'pages.json').write_text(json.dumps([{'url':'https://test.edu.cn/person','directory':'page','title':'张宏','body_chars':50,'body_status':'text_saved'}]),encoding='utf-8')
            obs=[{'name':'张宏','profile_url':'https://test.edu.cn/person','source_url':'https://test.edu.cn/list','evidence':'张宏'}]
            (root/'observations.json').write_text(json.dumps(obs),encoding='utf-8')
            store.update(key,state='finished',run_dir=str(root));build(store,key)
            person=store.catalog(key)['people'][0]
            self.assertEqual(person['review']['status'],'auto_accepted')
            client=TestClient(make_app(store));result=client.get(f'/api/jobs/{key}/export').json()
            self.assertEqual(result['accepted'][0]['title'],'教授')
            self.assertEqual(result['accepted'][0]['acceptance'],'auto_accepted')
            store.decide(key,person['id'],{'status':'excluded','actor':'复核员','reason':'测试人工覆盖','evidence':'https://test.edu.cn/list','revision':0})
            build(store,key)
            self.assertEqual(store.catalog(key)['people'][0]['review']['status'],'excluded')
            self.assertEqual(client.get(f'/api/jobs/{key}/export').json()['accepted'],[])
            # Modified evidence invalidates the automation without deleting human decisions.
            (root/'issues.json').write_text('[]',encoding='utf-8')
            self.assertEqual(store.catalog(key)['automation'],{})
            self.assertEqual(store.catalog(key)['people'][0]['review']['status'],'excluded')


if __name__ == '__main__':
    unittest.main()
