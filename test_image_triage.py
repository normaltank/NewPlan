import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from image_triage import triage_image
from quality_pipeline import build
from workbench_store import Store


NATIVE = '张宏，男，教授，博士生导师。研究方向为材料科学与工程，长期从事材料结构和性能研究，在相关领域发表多篇论文，并承担多项教学与科研工作。'


class ImageTriageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'media').mkdir()
        image = Image.new('RGB', (128,128))
        image.putdata([((i*31)%256,(i*53)%256,(i*79)%256) for i in range(128*128)])
        image.save(self.root/'media/source.png')

    def media(self, pairs):
        return {'directory':'media','source_file':'source.png',
                'text':'\n'.join(text for text,_ in pairs),
                'lines':[{'text':text,'confidence':score} for text,score in pairs]}

    def test_scene_sign_and_low_confidence_logo_do_not_block(self):
        result=triage_image(self.media([('学术研讨会',.99),('Lee',.70)]),self.root,'张宏',NATIVE)
        self.assertEqual(result['role'],'scene_text')
        self.assertFalse(result['review_required'])

    def test_portrait_with_biography_is_still_material(self):
        result=triage_image(self.media([('学术研讨会',.99),('张宏，教授',.70)]),self.root,'张宏',NATIVE)
        self.assertEqual(result['role'],'material_text')
        self.assertTrue(result['review_required'])

    def test_one_uncertain_email_matters_even_in_long_clear_cv(self):
        result=triage_image(self.media([('材料科学教学工作',.99)]*20+[('abc@qq.com',.7)]),self.root,'张宏',NATIVE)
        self.assertTrue(result['review_required'])

    def test_short_title_is_not_ignored_as_logo(self):
        self.assertTrue(triage_image(self.media([('教授',.7)]),self.root,'张宏',NATIVE)['review_required'])

    def test_no_ocr_cannot_prove_image_only_biography_is_empty(self):
        result=triage_image(self.media([]),self.root,'张宏','张宏')
        self.assertTrue(result['review_required'])
        self.assertEqual(result['role'],'uncertain')

    def test_name_in_heading_and_concise_native_bio_support_photo(self):
        result=triage_image(self.media([('Lee',.7)]),self.root,'张宏',
                            '副教授，医学硕士。研究方向为急诊医学，承担急诊与灾难医学教学任务。',page_title='张宏')
        self.assertFalse(result['review_required'])

    def test_clear_image_only_cv_can_pass_quality_check(self):
        result=triage_image(self.media([('张宏，教授，研究方向为材料科学',.99)]),self.root,'张宏','')
        self.assertFalse(result['review_required'])
        self.assertEqual(result['role'],'material_text')

    def test_white_document_is_not_classified_as_scene_photo(self):
        Image.new('RGB',(128,128),'white').save(self.root/'media/source.png')
        result=triage_image(self.media([('南通大学材料工程学院交流资料',.7)]),self.root,'张宏',NATIVE)
        self.assertTrue(result['review_required'])
        self.assertNotEqual(result['role'],'scene_text')

    def test_missing_image_cannot_support_photo_classification(self):
        m=self.media([('南通大学材料工程学院交流资料',.7)]);m['source_file']='missing.png'
        self.assertTrue(triage_image(m,self.root,'张宏',NATIVE)['review_required'])

    def test_dense_unknown_text_cannot_be_dismissed_as_photo(self):
        m=self.media([('学术研讨会',.7)]*9)
        self.assertTrue(triage_image(m,self.root,'张宏',NATIVE)['review_required'])

    def test_reassessment_resolves_photo_issue_preserves_originals_and_manual_decision(self):
        root=self.root;store=Store(root/'test.db')
        store.create_batch('test',[{'university':'测试大学','college':'测试学院','url':'https://test.edu.cn/'}])
        key=store.listing()['jobs'][0]['id'];(root/'page').mkdir()
        original=NATIVE+'\n\n[图片文字 / OCR 待复核]\n学术研讨会\nLee'
        (root/'page/body-text.txt').write_text(original,encoding='utf-8')
        (root/'page/native-text.txt').write_text(NATIVE,encoding='utf-8')
        data={'pages.json':[{'url':'https://test.edu.cn/person','directory':'page','title':'张宏','body_chars':len(original),'body_status':'ocr_candidate','ocr_media':['media']}],
              'observations.json':[{'name':'张宏','profile_url':'https://test.edu.cn/person','source_url':'https://test.edu.cn/list','evidence':'张宏'}],
              'issues.json':[{'kind':'ocr_review_required','url':'https://test.edu.cn/person','media':['media']}],
              'media.json':[self.media([('学术研讨会',.99),('Lee',.7)])]}
        for name,value in data.items():(root/name).write_text(json.dumps(value),encoding='utf-8')
        store.update(key,state='finished',run_dir=str(root));build(store,key)
        cat=store.catalog(key)
        self.assertEqual(cat['people'][0]['review']['status'],'auto_accepted')
        self.assertEqual(cat['issues'][0]['review']['status'],'resolved')
        self.assertEqual(cat['people'][0]['automatic']['image_assessments'][0]['role'],'scene_text')
        store.decide(key,cat['issues'][0]['id'],{'status':'needs_followup','actor':'测试员','reason':'人工认为需再查','evidence':'https://test.edu.cn/person','revision':0})
        # Force a fresh assessment without altering an issue's identity.
        data['media.json'][0]['note']='replay';(root/'media.json').write_text(json.dumps(data['media.json']),encoding='utf-8')
        build(store,key)
        self.assertEqual(store.catalog(key)['issues'][0]['review']['status'],'needs_followup')
        self.assertEqual((root/'page/body-text.txt').read_text(encoding='utf-8'),original)


if __name__=='__main__':
    unittest.main()
