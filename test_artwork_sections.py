import json
import hashlib
import tempfile
import unittest
from pathlib import Path
from image_triage import artwork_context, triage_image, without_artwork_ocr
from quality_pipeline import build
from workbench_store import Store

NATIVE='张宏，教授，博士生导师。研究方向为中国书法与绘画，承担课程教学及创作工作，发表多篇研究论文。'

class ArtworkTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);(self.root/'page').mkdir()
        self.page={'url':'https://test.edu.cn/teacher','directory':'page','body_selector':'.v_news_content','title':'张宏'}
        self.art={'directory':'art','source_url':'https://test.edu.cn/a.jpg','text':'山高水长\n张宏书',
                  'lines':[{'text':'山高水长','confidence':.6},{'text':'张宏书','confidence':.5}]}
        self.marker={'directory':'marker','source_url':'https://test.edu.cn/title.png','text':'个人作品',
                     'lines':[{'text':'个人作品','confidence':.999}]}
        self.images={'art':self.art,'marker':self.marker}
    def context(self,html):
        (self.root/'page/source.html').write_text('<div class="v_news_content">'+html+'</div>',encoding='utf8')
        return artwork_context(self.root,self.page,self.images)
    def test_graphic_heading_and_signature_are_art_not_biography(self):
        context=self.context('<p>'+NATIVE+'</p><p><img src="title.png"></p><p><img src="a.jpg"></p>')
        result=triage_image(self.art,self.root,'张宏',NATIVE,artwork=context[self.art['source_url']])
        self.assertEqual(result['role'],'artwork');self.assertFalse(result['review_required'])
        self.assertIn('sha256',result['section_evidence'])
    def test_low_quality_heading_and_unlabelled_art_cannot_be_skipped(self):
        self.marker['lines'][0]['confidence']=.8
        self.assertFalse(self.context('<img src="title.png"><img src="a.jpg">'))
        self.assertFalse(self.context('<img src="a.jpg"><p>个人作品</p>'))
    def test_new_biography_section_closes_artwork_scope(self):
        self.assertFalse(self.context('<h3>个人作品</h3><h3>个人简介</h3><img src="a.jpg">'))
        self.assertFalse(self.context('<h3>个人作品</h3><p>联系方式</p><img src="a.jpg">'))
    def test_resume_or_email_inside_work_section_remains_reviewable(self):
        context=self.context('<p>个人作品</p><img src="a.jpg">')
        self.art['text']='邮箱：bad@example.edu.cn';self.art['lines']=[{'text':self.art['text'],'confidence':.5}]
        self.assertTrue(triage_image(self.art,self.root,'张宏',NATIVE,artwork=context[self.art['source_url']])['review_required'])
    def test_image_only_resume_not_discarded_despite_section_label(self):
        context=self.context('<p>个人作品</p><img src="a.jpg">')
        self.assertNotEqual(triage_image(self.art,self.root,'张宏','',artwork=context[self.art['source_url']])['role'],'artwork')
    def test_clean_delivery_preserves_pdf_and_unclassified_image(self):
        text=NATIVE+'\n\n[图片文字 / OCR 待复核]\n书法乱码\n邮箱\n\n[个人页 PDF 附件全文]\n附件简历'
        kept={**self.art,'directory':'keep','text':'邮箱'}
        out=without_artwork_ocr(text,[self.art,kept],[{'directory':'art','role':'artwork'}])
        self.assertNotIn('书法乱码',out);self.assertIn('邮箱',out);self.assertTrue(out.endswith('附件简历'))
    def test_saved_reassessment_keeps_raw_and_removes_false_review(self):
        self.context('<p>'+NATIVE+'</p><p>个人作品</p><img src="a.jpg">')
        original=NATIVE+'\n\n[图片文字 / OCR 待复核]\n'+self.art['text']
        (self.root/'page/body-text.txt').write_text(original,encoding='utf8')
        (self.root/'page/native-text.txt').write_text(NATIVE,encoding='utf8')
        data={'pages.json':[{**self.page,'body_chars':len(original),'body_status':'ocr_candidate','ocr_media':['art']}],
              'observations.json':[{'name':'张宏','profile_url':self.page['url'],'source_url':'https://test.edu.cn/list','evidence':'张宏'}],
              'media.json':[self.art],'issues.json':[{'kind':'ocr_review_required','url':self.page['url'],'media':['art']}]}
        for name,value in data.items():(self.root/name).write_text(json.dumps(value),encoding='utf8')
        store=Store(self.root/'test.db');store.create_batch('test',[{'university':'测试大学','college':'测试学院','url':'https://test.edu.cn/'}])
        key=store.listing()['jobs'][0]['id'];store.update(key,state='finished',run_dir=str(self.root));build(store,key)
        cat=store.catalog(key);p=cat['people'][0]
        self.assertEqual(p['review']['status'],'auto_accepted');self.assertEqual(p['review']['fields']['biography'],NATIVE)
        self.assertEqual(cat['issues'][0]['review']['status'],'resolved')
        self.assertEqual((self.root/'page/body-text.txt').read_text(encoding='utf8'),original)
        self.assertEqual(p['automatic']['body_sha256'],hashlib.sha256(original.encode()).hexdigest())

if __name__=='__main__':unittest.main()
