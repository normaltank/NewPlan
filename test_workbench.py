"""Behavior tests use isolated SQLite and original-material fixtures, never live decisions."""
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont
from workbench import make_app
from workbench_store import Store, Conflict


def fixture(path):
    store=Store(path/'workbench.db')
    batch=store.create_batch('隔离验证',[{'university':'测试大学','college':'测试学院','url':'https://test.edu.cn/'}])
    job=store.claim()
    root=path/'fixture'
    (root/'page').mkdir(parents=True)
    (root/'page'/'body-text.txt').write_text('张三，教授。研究方向：材料。',encoding='utf8')
    (root/'page'/'source.html').write_text('<p>张三</p>',encoding='utf8')
    pages=[{'url':'https://test.edu.cn/zhang','kind':'profile','directory':'page','body_chars':18,
            'body_status':'text_saved','email_candidates':[],'title_candidates':['教授']}]
    obs=[{'name':'张三','profile_url':'https://test.edu.cn/zhang','source_url':'https://test.edu.cn/list','evidence':'张三','branch':'教师'}]
    for name,data in [('pages',pages),('observations',obs),('issues',[])]:
        (root/(name+'.json')).write_text(json.dumps(data,ensure_ascii=False),encoding='utf8')
    store.update(job['id'],state='finished',run_dir=str(root))
    return store,job['id']


def accept(revision=0):
    return {'revision':revision,'status':'accepted','actor':'隔离测试员','reason':'逐项核对官方证据','evidence':'https://test.edu.cn/zhang',
            'checks':{'identity_checked':True,'affiliation_checked':True,'fields_checked':True},
            'fields':{'name':'张三','title':'教授','email':'','profile_url':'https://test.edu.cn/zhang','biography':'张三，教授。研究方向：材料。','missing':{'email':'not_published'}}}


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store,self.key=fixture(Path(self.tmp.name))
        self.person=self.store.catalog(self.key)['people'][0]['id']
        self.client=TestClient(make_app(self.store))
    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()
    def test_optimistic_conflict_keeps_audit(self):
        self.store.decide(self.key,self.person,accept())
        with self.assertRaises(Conflict):self.store.decide(self.key,self.person,accept())
        self.assertEqual(len(self.store.history(self.key)),1)
    def test_missing_reason_cannot_be_silently_empty(self):
        data=accept();data['fields']['missing']={}
        with self.assertRaises(ValueError):self.store.decide(self.key,self.person,data)
    def test_accept_requires_identity_and_affiliation(self):
        data=accept();data['checks']['affiliation_checked']=False
        with self.assertRaises(ValueError):self.store.decide(self.key,self.person,data)
    def test_no_faculty_rejects_pending_or_accepted_person(self):
        data={**accept(),'status':'no_faculty','checks':{k:True for k in ('entry_checked','branches_checked','pagination_checked','rows_checked')}}
        with self.assertRaises(ValueError):self.store.decide(self.key,'__college__',data)
        self.store.decide(self.key,self.person,accept())
        with self.assertRaises(ValueError):self.store.decide(self.key,'__college__',data)
    def test_edit_invalidates_college_result_and_preserves_history(self):
        self.store.decide(self.key,self.person,accept())
        final={**accept(),'status':'verified','checks':{k:True for k in ('entry_checked','branches_checked','pagination_checked','rows_checked')}}
        self.store.decide(self.key,'__college__',final)
        self.store.decide(self.key,self.person,{**accept(1),'status':'needs_followup'})
        self.assertEqual(self.store.catalog(self.key)['college_review']['status'],'unverified')
        self.assertEqual(len(self.store.history(self.key)),4)
    def test_manual_add_invalidates_college_without_deleting_revision(self):
        self.store.decide(self.key,self.person,accept())
        final={**accept(),'status':'verified','checks':{k:True for k in ('entry_checked','branches_checked','pagination_checked','rows_checked')}}
        self.store.decide(self.key,'__college__',final)
        self.store.add_person(self.key,{'name':'李四','source_url':'https://test.edu.cn/li','actor':'测试','reason':'补漏'})
        self.assertEqual(self.store.catalog(self.key)['college_review']['revision'],2)
    def test_rerun_preserves_old_evidence_and_decisions(self):
        self.store.decide(self.key,self.person,accept())
        child=self.store.rerun(self.key,['https://test.edu.cn/list2'],'测试','补入口')
        self.assertEqual(self.store.job(child)['parent_id'],self.key)
        self.assertEqual(self.store.catalog(self.key)['people'][0]['review']['status'],'accepted')
        self.assertEqual(self.store.catalog(child)['people'],[])

    def test_continuation_keeps_unchanged_human_decision_and_rejects_duplicate_launch(self):
        root=Path(self.store.job(self.key)['run_dir'])
        (root/'targets.json').write_text('{}')
        self.store.decide(self.key,self.person,accept())
        child=self.store.continue_run(self.key,'测试',2,6)
        with self.assertRaises(Conflict):self.store.continue_run(self.key,'测试')
        dest=root.parent/'continued';shutil.copytree(root,dest)
        self.store.update(child,state='finished',run_dir=str(dest))
        self.store.carry_unchanged_reviews(child)
        p=self.store.catalog(child)['people'][0]
        self.assertEqual(p['review']['status'],'accepted')
        self.assertEqual(p['review']['inherited_from']['job_id'],self.key)
        self.assertEqual(self.store.catalog(child)['college_review']['status'],'unverified')
        self.assertEqual(self.store.catalog(self.key)['people'][0]['review']['status'],'accepted')

    def test_continuation_does_not_apply_old_acceptance_to_changed_body(self):
        root=Path(self.store.job(self.key)['run_dir']);(root/'targets.json').write_text('{}')
        self.store.decide(self.key,self.person,accept())
        child=self.store.continue_run(self.key,'测试',2,6)
        dest=root.parent/'changed';shutil.copytree(root,dest)
        (dest/'page/body-text.txt').write_text('张三的新材料',encoding='utf8')
        self.store.update(child,state='finished',run_dir=str(dest));self.store.carry_unchanged_reviews(child)
        self.assertEqual(self.store.catalog(child)['people'][0]['review']['revision'],0)
    def test_cross_origin_write_and_arbitrary_file_are_denied(self):
        r=self.client.post(f'/api/jobs/{self.key}/decisions/{self.person}',json=accept(),headers={'Origin':'https://evil.example'})
        self.assertEqual(r.status_code,403)
        self.assertEqual(self.client.get(f'/api/jobs/{self.key}/evidence',params={'path':'../workbench.db'}).status_code,404)
        root=Path(self.store.job(self.key)['run_dir']);(root/'api').mkdir();(root/'api'/'secret.json').write_text('{}')
        self.assertEqual(self.client.get(f'/api/jobs/{self.key}/evidence',params={'path':'api/secret.json'}).status_code,403)
    def test_export_only_accepted_and_formula_escape(self):
        self.assertEqual(self.client.get(f'/api/jobs/{self.key}/export').json()['accepted'],[])
        data=accept();data['fields']['name']='=HYPERLINK("x")'
        self.store.decide(self.key,self.person,data)
        r=self.client.get(f'/api/jobs/{self.key}/export?format=csv')
        self.assertIn("'=HYPERLINK",r.text)
    def test_same_name_different_url_is_not_merged(self):
        root=Path(self.store.job(self.key)['run_dir']);p=root/'observations.json';obs=json.loads(p.read_text(encoding='utf8'))
        obs.append({**obs[0],'profile_url':'https://test.edu.cn/another-zhang'});p.write_text(json.dumps(obs),encoding='utf8')
        people=self.store.catalog(self.key)['people'];self.assertEqual(len(people),2)
        self.assertIn('同名多来源',people[0]['flags'][0])
    def test_human_no_faculty_is_separate_from_failed_execution(self):
        self.store.decide(self.key,self.person,{**accept(),'status':'excluded','reason':'隔离样本：该记录不是目标学院教师'})
        self.store.update(self.key,state='failed')
        final={**accept(),'status':'no_faculty','reason':'隔离样本：官网明确说明无独立师资，人员已排除',
               'checks':{k:True for k in ('entry_checked','branches_checked','pagination_checked','rows_checked')}}
        self.store.decide(self.key,'__college__',final)
        self.assertEqual(self.store.job(self.key)['state'],'failed')
        self.assertEqual(self.store.catalog(self.key)['college_review']['status'],'no_faculty')


class OCRTests(unittest.TestCase):
    def test_image_and_scanned_pdf_keep_original_and_read_text(self):
        from ocr_media import read_image,read_pdf
        image=Image.new('RGB',(900,250),'white')
        draw=ImageDraw.Draw(image)
        font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',34) if Path('C:/Windows/Fonts/msyh.ttc').exists() else ImageFont.truetype('DejaVuSans.ttf',34)
        draw.text((20,30),'Research Faculty 2026',font=font,fill='black')
        draw.text((20,100),'Email: faculty@example.edu',font=font,fill='black')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);buf=io.BytesIO();image.save(buf,format='PNG')
            result=read_image(buf.getvalue(),root/'image')
            self.assertIn('2026',result['text']);self.assertTrue(result['lines'][0]['box'])
            buf=io.BytesIO();image.save(buf,format='PDF');(root/'pdf').mkdir()
            result=read_pdf(buf.getvalue(),root/'pdf')
            self.assertEqual(result['ocr_pages'],1);self.assertIn('2026',result['text'])


if __name__=='__main__':unittest.main()
