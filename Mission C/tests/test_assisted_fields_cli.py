"""Model assistance at the agreed saved source/cache -> CLI artifact boundary."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mission_c.cli import main


class AssistedFieldsCLI(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def blob(self, name, value):
        raw = value.encode('utf-8') if isinstance(value, str) else value
        (self.root / name).write_bytes(raw)
        return {'path': name, 'sha256': hashlib.sha256(raw).hexdigest()}

    def plan(self, **changes):
        return {'name': {'value': '陈晨', 'evidence': '陈晨'},
                'title': {'value': '', 'evidence': ''},
                'email': {'value': 'chen@example.edu', 'evidence': '电子邮箱：chen@example.edu'},
                'body_selector': '#profile', **changes}

    def replay(self, html, plan=None, response=None, entry_change=None, options=()):
        source = self.blob('source.html', '<meta charset="utf-8">' + html)
        if response is None:
            response = {'choices': [{'finish_reason': 'stop', 'message': {
                'content': json.dumps(plan or self.plan(), ensure_ascii=False)}}],
                        'usage': {'total_tokens': 42}}
        model = {**self.blob('model.json', json.dumps(response, ensure_ascii=False)),
                 'source_sha256': source['sha256']}
        entry = {'url': 'https://example.edu/chen', 'source': source, 'model': model}
        if entry_change:
            entry_change(entry)
        manifest = self.root / 'manifest.json'
        manifest.write_text(json.dumps({'version': 1, 'entries': [entry]}), encoding='utf-8')
        output = self.root / ('out-' + str(len(list(self.root.glob('out-*')))))
        with patch.object(httpx.Client, 'send', side_effect=AssertionError('offline requested network')), \
                patch.dict(os.environ, {}, clear=True):
            code = main(['--cache-manifest', str(manifest), '--model-mode', 'assist',
                         '--output', str(output), *options])
        return code, json.loads((output / 'teachers.json').read_text(encoding='utf-8'))[0], output

    def test_model_recovers_missing_personal_card_email_and_preserves_original_text(self):
        code, row, output = self.replay('<section id="profile"><h1>陈晨</h1>'
            '<div>电子邮箱：chen@example.edu</div></section>'
            '<main><p>陈晨的完整经历。</p><p>最后一项成果。</p></main>')
        self.assertEqual(code, 0)
        self.assertEqual(row['email'], 'chen@example.edu')
        self.assertEqual(row['model']['candidates']['email']['status'], 'applied')
        self.assertIn('最后一项成果。', row['biography'])
        self.assertEqual(row['model']['usage'], {'total_tokens': 42})
        self.assertTrue((output / row['model']['response_file']).is_file())

    def test_personal_fields_reject_public_contacts_collaborators_advisors_and_conflicts(self):
        html = ('<section id="profile"><h1>陈晨</h1><p>职称：教授</p>'
                '<p>学院邮箱：office@example.edu</p><p>师从王宁教授。</p>'
                '<h2>发表论文</h2><p>合作者李明，电子邮箱：li@example.edu</p></section>'
                '<aside><h1>王宁</h1><p>电子邮箱：wang@example.edu</p></aside>'
                '<main>陈晨的完整经历。</main>')
        for email, quote in [('office@example.edu', '学院邮箱：office@example.edu'),
                             ('li@example.edu', '合作者李明，电子邮箱：li@example.edu'),
                             ('wang@example.edu', '电子邮箱：wang@example.edu')]:
            with self.subTest(email=email):
                _, row, _ = self.replay(html, self.plan(email={'value': email, 'evidence': quote},
                    title={'value': '教授，博士生导师', 'evidence': '职称：教授，博士生导师'}))
                self.assertEqual(row['email'], '')
                self.assertNotEqual(row['model']['candidates']['email']['status'], 'applied')
        _, row, _ = self.replay('<section id="profile"><h1>陈晨</h1><p>职称：副教授</p>'
            '<p>师从王宁教授。</p><p>博士生导师</p></section><main><h1>陈晨</h1>陈晨，副教授。</main>',
            self.plan(title={'value': '教授', 'evidence': '师从王宁教授。'}, email={'value': '', 'evidence': ''}))
        self.assertEqual(row['title'], '副教授')
        self.assertEqual(row['model']['candidates']['title']['status'], 'rejected')
        _, row, _ = self.replay('<section id="profile"><h1>陈晨</h1><p>职称：教授，博士生导师</p>'
            '<p>电子邮箱：chen@example.edu</p></section><main>陈晨的完整经历。</main>',
            self.plan(title={'value': '教授，博士生导师', 'evidence': '职称：教授，博士生导师'}))
        self.assertEqual(row['title'], '教授')
        self.assertEqual(row['model']['candidates']['title']['professional_value'], '教授')
        self.assertEqual(row['model']['candidates']['title']['qualifications'], ['博士生导师'])

    def test_invalid_cached_response_is_explicit_and_does_not_change_source_fields(self):
        good = self.plan()
        responses = [
            ({'choices': [{'finish_reason': 'length', 'message': {'content': json.dumps(good)}}]}, 'model_incomplete_response'),
            ({'choices': []}, 'model_invalid_response'),
            ({'choices': [{'finish_reason': 'stop', 'message': {'content': '{broken'}}]}, 'model_invalid_response'),
            ({'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps({**good, 'name': '陈晨'})}}]}, 'model_invalid_response'),
            ({'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps({**good, 'url': 'https://other.edu/'})}}]}, 'model_url_mismatch'),
        ]
        for response, error in responses:
            with self.subTest(error=error):
                code, row, output = self.replay('<main><h1>陈晨</h1><p>陈晨，副教授。原文末段。</p></main>', response=response)
                self.assertEqual(code, 0)
                self.assertEqual(row['model']['error']['code'], error)
                self.assertEqual(row['title'], '副教授')
                self.assertIn('原文末段。', row['biography'])
                self.assertTrue((output / row['model']['response_file']).is_file())
        for change, error in [
            (lambda e: e['model'].update(source_sha256='0'*64), 'cache_source_hash_mismatch'),
            (lambda e: e['model'].update(sha256='0'*64), 'cache_hash_mismatch'),
            (lambda e: e['model'].update(url='https://other.edu/'), 'cache_url_mismatch'),
            (lambda e: e.pop('model'), 'cache_missing'),
        ]:
            with self.subTest(error=error):
                _, row, _ = self.replay('<main><h1>陈晨</h1>原文。</main>', entry_change=change)
                self.assertEqual(row['model']['error']['code'], error)
        _, row, _ = self.replay('<section id="profile"><h1>陈晨</h1><p>原文。</p></section>',
                              self.plan(email={'value': 'fake@example.edu', 'evidence': '电子邮箱：fake@example.edu'}))
        self.assertEqual(row['email'], '')
        self.assertEqual(row['model']['candidates']['email']['reason'], 'quote_not_in_source')

    def test_selector_requires_unique_identity_and_full_existing_coverage_without_model_summary(self):
        html = ('<section id="profile"><main><h1>陈晨</h1><p id="short">完整第一段。</p>'
                '<p>最后成果。</p></main><p>额外原文。</p></section>')
        for selector, status in [('#missing', 'not_unique'), ('p', 'not_unique'),
                                 ('[', 'invalid_selector'), ('#short', 'would_shrink'),
                                 ('#profile', 'applied')]:
            with self.subTest(selector=selector):
                _, row, output = self.replay(html, self.plan(body_selector=selector,
                    email={'value': '', 'evidence': ''}, biography='模型摘要，禁止作为简介。'))
                self.assertEqual(row['model']['selector']['status'], status)
                self.assertIn('完整第一段。', row['biography'])
                self.assertIn('最后成果。', row['biography'])
                self.assertNotIn('模型摘要', row['biography'])
                self.assertEqual((output / row['biography_file']).read_text(encoding='utf-8'), row['biography'])
                if status == 'applied':
                    self.assertIn('额外原文。', row['biography'])
                    self.assertEqual(row['content_selection'], 'model_selector_verified')
                else:
                    self.assertNotIn('额外原文。', row['biography'])


if __name__ == '__main__':
    unittest.main()
