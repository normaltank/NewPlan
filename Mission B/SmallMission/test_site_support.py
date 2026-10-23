"""Regression checks for the 2026-10-15 failed desktop batch."""
import asyncio
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from audit import Fetcher, lookup_plan, parse_roster, read_source, run
from runtime_paths import APP_ROOT
from test_multisource import paired_file


class PaginationTests(unittest.TestCase):
    def test_vsb_pagination_stays_in_same_column(self):
        body = '''<title>教师</title><div class="roster"><a href="/info/1.htm">甲</a></div>
        <div class="pb_sys_common"><a href="staff/2.htm">下页</a><a href="staff/1.htm">尾页</a>
        <a href="https://other.edu.cn/staff/1.htm">下一页</a></div>'''
        parsed = parse_roster(body, 'https://example.edu.cn/staff.htm', {'selector': '.roster'}, follow_pagination=True)
        self.assertEqual(parsed['pagination_urls'], ['https://example.edu.cn/staff/2.htm', 'https://example.edu.cn/staff/1.htm'])
        self.assertFalse(parsed['complete'])  # Suspicious cross-site paging cannot silently pass.
        self.assertEqual(list(parsed['links']), ['https://example.edu.cn/info/1.htm'])

    def test_webplus_disabled_pagination_is_not_an_unknown_page(self):
        body = '''<title>教师</title><div class="roster"><a href="/a">甲</a></div>
        <ul class="wp_paging"><li><a href="javascript:void(0);">尾页</a></li></ul>'''
        self.assertTrue(parse_roster(body, 'https://example.edu.cn/1/list.htm', {'selector': '.roster'}, follow_pagination=True)['complete'])

    def test_webplus_page_urls_preserve_column(self):
        body = '''<div class="roster"><a href="/a">甲</a></div>
        <div id="wp_pager"><a href="list2.htm">2</a><a href="list3.htm">尾页</a></div>'''
        p = parse_roster(body, 'https://example.edu.cn/17118/list.htm', {'selector': '.roster'}, follow_pagination=True)
        self.assertTrue(p['complete'])
        self.assertEqual(p['pagination_urls'], ['https://example.edu.cn/17118/list2.htm', 'https://example.edu.cn/17118/list3.htm'])

    def test_run_reads_all_pages_and_never_profiles_or_other_columns(self):
        with tempfile.TemporaryDirectory(dir=APP_ROOT) as d:
            root = Path(d); inputs = root / 'input'; inputs.mkdir()
            base = 'https://example.edu.cn/staff.htm'
            paired_file(inputs / 'test.xlsx', '大学', '学院', [base], ['https://example.edu.cn/a'])
            config = root / 'plans.json'; config.write_text(json.dumps({'plans': {base: {'selector': '.roster'}}}))
            calls = []
            async def fetch(fetcher, task):
                calls.append(task['roster_url'])
                part = 'a' if task['roster_url'] == base else 'b'
                body = f'<div class="roster"><a href="/{part}">姓名</a></div><div class="pb_sys_common"><a href="{base}">首页</a><a href="https://example.edu.cn/staff/1.htm">尾页</a></div>'
                meta = {'requested_url': task['roster_url'], 'final_url': task['roster_url'], 'status': 200, 'method': 'fixture'}
                fetcher.save(task['id'], 'http', body, meta)
                return body, meta
            with patch.object(Fetcher, 'http', fetch):
                _, results, _ = asyncio.run(run(SimpleNamespace(input=inputs, output=root/'output', plans=config, no_browser=True, replay=None)))
            self.assertEqual(len(calls), 2)
            self.assertTrue(results[0]['complete'])
            self.assertEqual(results[0]['stats']['source_unique'], 2)
            self.assertEqual(results[0]['stats']['missing'], 1)
            self.assertEqual(results[0]['sources'][1]['discovered_from'], base)

    def test_unreadable_following_page_never_deletes_original_links(self):
        with tempfile.TemporaryDirectory(dir=APP_ROOT) as d:
            root = Path(d); inputs = root/'input'; inputs.mkdir()
            base = 'https://example.edu.cn/staff.htm'
            paired_file(inputs/'test.xlsx', '大学', '学院', [base], ['https://example.edu.cn/a', 'https://example.edu.cn/b'])
            config = root/'plans.json'; config.write_text(json.dumps({'plans': {base: {'selector': '.roster'}}}))
            async def fetch(fetcher, task):
                main = task['roster_url'] == base
                body = '<div class="roster"><a href="/a">甲</a></div><div class="pb_sys_common"><a href="staff/1.htm">下页</a></div>' if main else 'Access denied'
                meta = {'requested_url': task['roster_url'], 'final_url': task['roster_url'], 'status': 200 if main else 403, 'method': 'fixture'}
                fetcher.save(task['id'], 'http', body, meta)
                return body, meta
            with patch.object(Fetcher, 'http', fetch):
                _, results, _ = asyncio.run(run(SimpleNamespace(input=inputs, output=root/'output', plans=config, no_browser=True, replay=None)))
            self.assertFalse(results[0]['complete'])
            self.assertIsNone(results[0]['stats']['extra'])
            self.assertEqual(len(results[0]['diffs']), 2)
            self.assertEqual(results[0]['sources'][1]['failure_kind'], 'access')

    def test_inert_script_buttons_with_multiple_declared_pages_fail_closed(self):
        body = '''<div class="roster"><a href="/a">甲</a></div><ul class="wp_paging">
        <a href="javascript:void(0);">下一页</a><em class="all_pages">3</em></ul>'''
        self.assertFalse(parse_roster(body, 'https://example.edu.cn/list.htm', {'selector': '.roster'}, follow_pagination=True)['complete'])

    def test_confirmed_no_outgoing_links_requires_matching_body_evidence(self):
        plan = {'selector': '.content', 'empty_confirmation_text': ['王伟', '研究专长']}
        source = 'https://example.edu.cn/info/1.htm'
        body = '<div class="content">王伟，研究专长。</div>'
        self.assertTrue(parse_roster(body, source, plan)['complete'])
        self.assertFalse(parse_roster('<div class="content"></div>', source, plan)['complete'])
        self.assertFalse(parse_roster(body, source, {'selector': '.content'})['complete'])

    def test_registered_plan_reused_only_for_its_own_column(self):
        config = {'plans': {'https://example.edu.cn/staff.htm': {'selector': '.roster'}}}
        self.assertIsNotNone(lookup_plan(config, 'http://example.edu.cn/staff/2.htm'))
        self.assertIsNone(lookup_plan(config, 'https://example.edu.cn/news/2.htm'))
        self.assertIsNone(lookup_plan(config, 'https://else.edu.cn/staff/2.htm'))


class FetchSelectionTests(unittest.TestCase):
    def test_successful_browser_recovery_skips_repeated_denied_http(self):
        with tempfile.TemporaryDirectory(dir=APP_ROOT) as d:
            async def check():
                async with Fetcher(Path(d)) as fetcher:
                    calls = []
                    async def http(task):
                        calls.append('http')
                        return 'Denied', {'status': 403, 'final_url': task['roster_url']}
                    async def browser(task):
                        calls.append('browser')
                        return '<div class="roster"><a href="/a">甲</a></div>', {'status': 200, 'final_url': task['roster_url']}
                    fetcher.http, fetcher.browser_fetch = http, browser
                    config = {'plans': {'https://example.edu.cn/list.htm': {'selector': '.roster'}}}
                    for n in ('', '2'):
                        await read_source(fetcher, {'id': 'page'+n, 'roster_url': f'https://example.edu.cn/list{n}.htm'}, config, None, [])
                    return calls
            self.assertEqual(asyncio.run(check()), ['http', 'browser', 'browser'])

    def test_explicit_ip_block_pauses_further_site_requests(self):
        with tempfile.TemporaryDirectory(dir=APP_ROOT) as d:
            async def check():
                async with Fetcher(Path(d), browser=False) as fetcher:
                    calls = []
                    async def http(task):
                        calls.append(task['roster_url'])
                        return '<title>网站防火墙</title>当前IP已被拉入黑名单', {'status': 403, 'final_url': task['roster_url']}
                    fetcher.http = http
                    for n in ('', '2'):
                        result = await read_source(fetcher, {'id': 'page'+n, 'roster_url': f'https://example.edu.cn/list{n}.htm'}, {'plans': {}}, None, [])
                    return calls, result
            calls, result = asyncio.run(check())
            self.assertEqual(len(calls), 1)
            self.assertEqual(result['failure_kind'], 'access')
            self.assertEqual(result['attempts'][0]['method'], '站点暂停')

    def test_unknown_static_html_does_not_make_a_redundant_browser_request(self):
        with tempfile.TemporaryDirectory(dir=APP_ROOT) as d:
            async def check():
                async with Fetcher(Path(d)) as fetcher:
                    async def http(task):
                        return '<title>师资</title><body>名单张三李四</body>', {'status': 200, 'final_url': 'https://example.edu.cn/list.htm'}
                    async def browser(task):
                        self.fail('Static unknown structure is not a browser loading failure')
                    fetcher.http, fetcher.browser_fetch = http, browser
                    return await read_source(fetcher, {'id': 'unknown', 'roster_url': 'https://example.edu.cn/list.htm'}, {'plans': {}}, None, [])
            self.assertEqual(asyncio.run(check())['failure_kind'], 'structure')


if __name__ == '__main__':
    unittest.main()
