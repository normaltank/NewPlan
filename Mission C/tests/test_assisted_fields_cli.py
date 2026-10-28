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

    def test_live_model_uses_json_and_persistent_budget_shared_with_fetch(self):
        source = self.root / 'live.html'
        source.write_text('<meta charset="utf-8"><section id="profile"><h1>陈晨</h1><p>电子邮箱：chen@example.edu</p></section><main>完整经历。</main>', encoding='utf-8')
        attempts = self.root / 'attempts'
        calls = []
        def send(client, request, **kwargs):
            calls.append(request)
            if request.url.path.endswith('/fetch'):
                return httpx.Response(200, json={'content': '提供方文字'}, request=request)
            payload = json.loads(request.content)
            self.assertEqual(payload['response_format'], {'type': 'json_object'})
            self.assertEqual(payload['thinking'], {'type': 'disabled'})
            self.assertEqual(payload['model'], 'deepseek-flash')
            self.assertIn('JSON', payload['messages'][0]['content'])
            return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {
                'content': json.dumps(self.plan())}}], 'usage': {'total_tokens': 42}}, request=request)
        def run(number, budget):
            out = self.root / ('live-' + str(number))
            main(['--url', 'https://example.edu/chen', '--html', str(source), '--output', str(out),
                  '--fetch-mode', 'supplement', '--model-mode', 'assist', '--allow-paid',
                  '--paid-max-calls', str(budget), '--paid-attempts', str(attempts)])
            return json.loads((out / 'teachers.json').read_text(encoding='utf-8'))[0]
        with patch.object(httpx.Client, 'send', send), patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'fake-secret'}, clear=True):
            row = run(1, 1)
            self.assertEqual(row['model']['error']['code'], 'model_budget_exhausted')
            row = run(2, 2)
            self.assertEqual(row['email'], 'chen@example.edu')
            self.assertEqual(row['model']['usage'], {'total_tokens': 42})
            row = run(3, 2)
            self.assertEqual(row['model']['error']['code'], 'model_attempt_exists')
        self.assertEqual(len(calls), 2)
        self.assertNotIn('fake-secret', ''.join(p.read_text(encoding='utf-8') for p in attempts.glob('*.json')))

    def test_live_model_http_failure_saved_and_unknown_timeout_never_resent(self):
        source = self.root / 'source.html'
        source.write_text('<h1>陈晨</h1><main>完整原文。</main>', encoding='utf-8')
        def run(number, attempts):
            out = self.root / str(number)
            main(['--url', 'https://example.edu/chen', '--html', str(source), '--output', str(out),
                  '--model-mode', 'assist', '--allow-paid', '--paid-max-calls', '3', '--paid-attempts', str(attempts)])
            return json.loads((out / 'teachers.json').read_text(encoding='utf-8'))[0], out
        def failed(client, request, **kwargs):
            return httpx.Response(500, content=b'{"error":"fake-secret"}', request=request)
        with patch.object(httpx.Client, 'send', failed), patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'fake-secret'}, clear=True):
            row, out = run(1, self.root / 'failed-attempts')
            self.assertEqual(row['model']['error']['code'], 'model_provider_http_error')
            self.assertNotIn('fake-secret', (out / '0001/model-response.json').read_text())
        with patch.object(httpx.Client, 'send', side_effect=httpx.ReadTimeout('fake-secret')), patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'fake-secret'}, clear=True):
            row, _ = run(2, self.root / 'unknown-attempts')
            self.assertEqual(row['model']['error']['code'], 'model_network_unknown')
            row, _ = run(3, self.root / 'unknown-attempts')
            self.assertEqual(row['model']['error']['code'], 'model_attempt_unknown')

    def test_split_public_and_collaborator_labels_are_not_personal_email(self):
        for block, email in [
            ('<dl><dt>学院邮箱</dt><dd>电子邮箱：office@example.edu</dd></dl>', 'office@example.edu'),
            ('<div><h3>合作者李明</h3><p>电子邮箱：li@example.edu</p></div>', 'li@example.edu'),
        ]:
            with self.subTest(email=email):
                _, row, _ = self.replay('<section id="profile"><h1>陈晨</h1>' + block +
                    '</section><main>陈晨的完整个人经历。</main>',
                    self.plan(email={'value': email, 'evidence': '电子邮箱：' + email}))
                self.assertEqual(row['email'], '')
                self.assertEqual(row['model']['candidates']['email']['reason'], 'other_person_or_public_context')
                self.assertEqual(row['model']['candidates']['email']['evidence'], '电子邮箱：' + email)
        # An unrelated publication/advisor elsewhere must not taint a personal contact.
        _, row, _ = self.replay('<section id="profile"><h1>陈晨</h1>'
            '<p>电子邮箱：chen@example.edu</p><h2>论文</h2><p>合作者李明，师从王宁。</p>'
            '</section><main>陈晨的完整个人经历。</main>')
        self.assertEqual(row['email'], 'chen@example.edu')

    def test_english_split_public_labels_reject_contacts_but_personal_email_remains_valid(self):
        for block in ('<dl><dt>Department email</dt><dd>Email: office@example.edu</dd></dl>',
                      '<div><h3>Collaborator Mary Jones</h3><p>Email: office@example.edu</p></div>'):
            with self.subTest(block=block):
                _, row, _ = self.replay('<section><h1>陈晨</h1>' + block +
                    '</section><main>陈晨的完整个人经历。</main>',
                    self.plan(email={'value': 'office@example.edu', 'evidence': 'Email: office@example.edu'}))
                self.assertEqual(row['email'], '')
                self.assertEqual(row['model']['candidates']['email']['reason'], 'other_person_or_public_context')
        _, row, _ = self.replay('<section><h1>陈晨</h1><p>Email: chen@example.edu</p></section>'
            '<main>陈晨的完整个人经历。</main>',
            self.plan(email={'value': 'chen@example.edu', 'evidence': 'Email: chen@example.edu'}))
        self.assertEqual(row['email'], 'chen@example.edu')

    def test_contact_cannot_borrow_identity_past_another_person_heading(self):
        _, row, _ = self.replay('<main><h1>陈晨</h1><p>本人完整经历。</p></main>'
            '<section><h1>陈晨</h1><div><h2>周宁</h2>'
            '<p>电子邮箱：zhou@example.edu</p></div></section>',
            self.plan(email={'value': 'zhou@example.edu', 'evidence': '电子邮箱：zhou@example.edu'},
                      body_selector=''))
        self.assertEqual(row['name'], '陈晨')
        self.assertEqual(row['email'], '')
        candidate = row['model']['candidates']['email']
        self.assertEqual(candidate['status'], 'unconfirmed')
        self.assertEqual(candidate['reason'], 'personal_ownership_not_confirmed')
        self.assertEqual(candidate['evidence'], '电子邮箱：zhou@example.edu')

    def test_contact_subsections_keep_other_person_ownership(self):
        for contact in ('<h3>联系方式</h3><p>电子邮箱：zhou@example.edu</p>',
                        '<h4>联系方式</h4><p>电子邮箱：zhou@example.edu</p>',
                        '<section><h3>联系方式</h3><div><p>电子邮箱：zhou@example.edu</p></div></section>'):
            with self.subTest(contact=contact):
                _, row, _ = self.replay('<main><h1>陈晨</h1><p>本人完整经历。</p></main>'
                    '<section><h1>陈晨</h1><div><h2>周宁</h2>' + contact + '</div></section>',
                    self.plan(email={'value': 'zhou@example.edu', 'evidence': '电子邮箱：zhou@example.edu'},
                              body_selector=''))
                self.assertEqual(row['name'], '陈晨')
                self.assertEqual(row['email'], '')
                self.assertEqual(row['model']['candidates']['email']['status'], 'unconfirmed')
                self.assertEqual(row['model']['candidates']['email']['reason'], 'personal_ownership_not_confirmed')

    def test_contact_subsections_keep_public_and_collaborator_boundaries(self):
        for owner in ('学院邮箱', '合作者李明', 'Department email', 'Collaborator Mary Jones'):
            for level in ('h3', 'h4'):
                with self.subTest(owner=owner, level=level):
                    _, row, _ = self.replay('<section><h1>陈晨</h1><h2>' + owner + '</h2><' + level +
                        '>联系方式</' + level + '><div><p>电子邮箱：other@example.edu</p></div></section>'
                        '<main>本人完整经历。</main>',
                        self.plan(email={'value': 'other@example.edu', 'evidence': '电子邮箱：other@example.edu'},
                                  body_selector=''))
                    self.assertEqual(row['email'], '')
                    self.assertEqual(row['model']['candidates']['email']['reason'], 'other_person_or_public_context')
        for contact in ('<h3>联系方式</h3>', '<h4>联系方式</h4>',
                        '<section><h3>联系方式</h3></section>'):
            with self.subTest(personal=contact):
                _, row, _ = self.replay('<section><h1>陈晨</h1><h2>论文</h2><p>合作者李明。</p>'
                    '<h2>个人资料</h2>' + contact + '<p>电子邮箱：chen@example.edu</p></section>'
                    '<main>本人完整经历。</main>', self.plan(body_selector=''))
                self.assertEqual(row['email'], 'chen@example.edu')
                self.assertEqual(row['model']['candidates']['email']['status'], 'applied')

    def test_wrapped_owner_heading_keeps_nested_contact_ownership(self):
        _, row, _ = self.replay('<main><h1>陈晨</h1><p>本人完整经历。</p></main>'
            '<section><h1>陈晨</h1><div><header><h2>周宁</h2></header>'
            '<div><h3>联系方式</h3><p>电子邮箱：zhou@example.edu</p></div></div></section>',
            self.plan(email={'value': 'zhou@example.edu', 'evidence': '电子邮箱：zhou@example.edu'},
                      body_selector=''))
        self.assertEqual(row['name'], '陈晨')
        self.assertEqual(row['email'], '')
        self.assertEqual(row['model']['candidates']['email']['status'], 'unconfirmed')
        self.assertEqual(row['model']['candidates']['email']['reason'], 'personal_ownership_not_confirmed')

    def test_rejected_expected_identity_cannot_be_restored_by_model(self):
        _, row, _ = self.replay('<section id="profile"><h1>王宁</h1>'
            '<p>职称：教授</p><p>电子邮箱：wang@example.edu</p></section>'
            '<main><h1>王宁</h1><p>王宁的完整个人经历。</p></main>',
            self.plan(name={'value': '王宁', 'evidence': '王宁'},
                      title={'value': '教授', 'evidence': '职称：教授'},
                      email={'value': 'wang@example.edu', 'evidence': '电子邮箱：wang@example.edu'}),
            options=('--name', '陈晨'))
        self.assertEqual(row['name'], '')
        self.assertIn('expected_name_not_confirmed', row['warnings'])
        for field in ('name', 'title', 'email'):
            self.assertNotEqual(row['model']['candidates'][field]['status'], 'applied')
            self.assertEqual(row['model']['candidates'][field]['reason'], 'expected_identity_not_confirmed')

    def test_personal_template_sibling_card_and_split_name_label_are_bound(self):
        html = ('<div id="container-0"><div class="teach_info"><h1 class="news_title">陈晨 教授</h1></div></div>'
                '<div id="container-1"><h3>个人资料</h3><p>电子邮箱：chen@example.edu</p>'
                '<main>完整经历。</main></div>')
        _, row, _ = self.replay(html)
        self.assertEqual(row['email'], 'chen@example.edu')
        _, row, _ = self.replay('<main><p><span>姓名：</span><span>陈晨</span></p>'
                                '<p>职称：教授，博士生导师</p><p>完整经历。</p></main>',
                                self.plan(title={'value': '教授，博士生导师', 'evidence': '职称：教授，博士生导师'}))
        self.assertEqual(row['model']['candidates']['title']['professional_value'], '教授')
        self.assertEqual(row['model']['candidates']['title']['qualifications'], ['博士生导师'])

    def test_fetch_plaintext_does_not_borrow_public_or_other_person_contacts(self):
        for context in ('学院邮箱', '合作者李明', '姓名：周宁'):
            with self.subTest(context=context):
                content = '姓名：陈晨\n完整经历。\n' + context + '\n电子邮箱：other@example.edu'
                plan = self.plan(email={'value': 'other@example.edu', 'evidence': '电子邮箱：other@example.edu'})
                response = {'choices': [{'finish_reason': 'stop', 'message': {
                    'content': json.dumps(plan, ensure_ascii=False)}}]}
                entry = {'url': 'https://example.edu/chen',
                         'source': {'error': {'code': 'http_412', 'message': 'cached failure'}},
                         'fetch': {**self.blob('split-fetch.json', json.dumps({'content': content})), 'provider_http_status': 200},
                         'model': {**self.blob('split-model.json', json.dumps(response)),
                                   'source_kind': 'deepseek-fetch',
                                   'source_sha256': hashlib.sha256(content.encode('utf-8')).hexdigest()}}
                manifest = self.root / 'split-provider.json'
                manifest.write_text(json.dumps({'version': 1, 'entries': [entry]}), encoding='utf-8')
                out = self.root / ('split-' + str(len(list(self.root.glob('split-*out')))) + 'out')
                with patch.object(httpx.Client, 'send', side_effect=AssertionError('offline requested network')), \
                        patch.dict(os.environ, {}, clear=True):
                    main(['--cache-manifest', str(manifest), '--fetch-mode', 'fallback',
                          '--model-mode', 'assist', '--output', str(out)])
                row = json.loads((out / 'teachers.json').read_text(encoding='utf-8'))[0]
                self.assertEqual(row['email'], '')
                self.assertIn(row['model']['candidates']['email']['status'], ('rejected', 'unconfirmed'))
                self.assertEqual(row['biography'], content)

    def test_fetch_only_model_uses_provider_text_binding_without_css_or_origin_success(self):
        content = '姓名：陈晨\n职称：教授\n电子邮箱：chen@example.edu\n完整经历。'
        response = {'choices': [{'finish_reason': 'stop', 'message': {
            'content': json.dumps(self.plan(title={'value': '教授', 'evidence': '职称：教授'}), ensure_ascii=False)}}]}
        entry = {'url': 'https://example.edu/chen',
                 'source': {'error': {'code': 'http_412', 'message': 'cached origin failure'}},
                 'fetch': {**self.blob('fetch.json', json.dumps({'content': content})), 'provider_http_status': 200},
                 'model': {**self.blob('provider-model.json', json.dumps(response)),
                           'source_kind': 'deepseek-fetch',
                           'source_sha256': hashlib.sha256(content.encode('utf-8')).hexdigest()}}
        manifest = self.root / 'provider-manifest.json'
        manifest.write_text(json.dumps({'version': 1, 'entries': [entry]}), encoding='utf-8')
        out = self.root / 'provider-out'
        with patch.object(httpx.Client, 'send', side_effect=AssertionError('offline requested network')), \
                patch.dict(os.environ, {}, clear=True):
            code = main(['--cache-manifest', str(manifest), '--fetch-mode', 'fallback',
                         '--model-mode', 'assist', '--output', str(out)])
        row = json.loads((out / 'teachers.json').read_text(encoding='utf-8'))[0]
        self.assertEqual(code, 1)
        self.assertEqual(row['name'], '陈晨')
        self.assertEqual(row['email'], 'chen@example.edu')
        self.assertEqual(row['status'], 'provider_candidate')
        self.assertEqual(row['error']['code'], 'http_412')
        self.assertEqual(row['biography'], content)
        self.assertEqual(row['model']['source_kind'], 'deepseek-fetch')
        self.assertEqual(row['field_status']['email'], 'provider_model_candidate')
        self.assertEqual(row['model']['selector']['status'], 'not_applicable_plaintext')


if __name__ == '__main__':
    unittest.main()
