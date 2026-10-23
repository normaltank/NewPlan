import asyncio
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx
from evaluate import markdown_text, apply_candidate, attachment_suffix
from fetch_client import FetchClient


class AdapterTests(unittest.TestCase):
    def test_real_commonmark_email_escapes(self):
        text,_=markdown_text(r"仇晓黎教授 邮箱\:qiuxiaoli\@seu\.edu\.cn")
        self.assertIn("qiuxiaoli@seu.edu.cn",text)
        self.assertNotIn("\\",text)

    def test_mailto_label_keeps_address(self):
        text,_=markdown_text("张三 [电子邮箱](mailto:zhang@example.edu.cn)")
        self.assertIn("zhang@example.edu.cn",text)

    def test_failure_does_not_mutate_origin_or_saved_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'p').mkdir();(root/'p/body-text.txt').write_text('张三 教授',encoding='utf8')
            page={'url':'https://example.edu/p','directory':'p','kind':'profile','status':200,'body_status':'text_saved'}
            before=page.copy()
            result=apply_candidate(root,page,{'status':'provider_no_usable_content','http_status':404},{'张三'})
            self.assertEqual(page,before)
            self.assertFalse(result['applied'])
            self.assertEqual((root/'p/body-text.txt').read_text(encoding='utf8'),'张三 教授')

    def test_candidate_preserves_original_and_attachment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'p').mkdir();old='张三\n[图片文字 / OCR 待复核]\n张三 学习经历'
            (root/'p/body-text.txt').write_text(old,encoding='utf8')
            (root/'p/source.html').write_text('<p>张三</p>',encoding='utf8')
            page={'url':'https://example.edu/p','directory':'p','kind':'profile','status':200,'body_status':'ocr_candidate'}
            result=apply_candidate(root,page,{'status':'ok','content':'张三 教授\n邮箱 zhang@example.edu.cn'},{'张三'})
            self.assertTrue(result['applied'])
            self.assertEqual((root/'p/body-text.txt').read_text(encoding='utf8'),old)
            self.assertEqual((root/'p/source.html').read_text(encoding='utf8'),'<p>张三</p>')
            self.assertIn('张三 学习经历',(root/page['body_path']).read_text(encoding='utf8'))

    def test_wrong_person_stays_unapplied(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'p').mkdir()
            page={'url':'https://example.edu/p','directory':'p','kind':'profile','status':200}
            result=apply_candidate(root,page,{'status':'ok','content':'李四 教授'},{'张三'})
            self.assertFalse(result['applied'])
            self.assertNotIn('body_path',page)


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_404_is_provider_failure_with_unknown_origin_status(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'DEEPSEEK_API_KEY':'test-secret-placeholder'}):
            client=FetchClient(Path(tmp),transport=httpx.MockTransport(lambda req:httpx.Response(404,json={'error':{'code':'not_found'}})))
            try:
                result=await client.fetch('https://example.edu/p')
            finally:
                await client.close()
            self.assertIsNone(result['origin_status'])
            self.assertEqual(result['status'],'provider_no_usable_content')
            self.assertEqual(len(client.calls),1)
            self.assertFalse(client.calls[0]['billable_success'])


if __name__=='__main__':unittest.main()
