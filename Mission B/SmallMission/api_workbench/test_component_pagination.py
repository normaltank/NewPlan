"""Component paging through the college audit, with only HTTP/model substitutes."""
import asyncio
import csv
import itertools
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout

from bs4 import BeautifulSoup
import httpx

from audit import ROOT, run


SOURCE = 'https://example.edu.cn/list_photo.jsp?urltype=tree.TreeTempUrl&wbtreeid=1024'
PAGES = [SOURCE] + [
    'https://example.edu.cn/list_photo.jsp?a1125737t=4&a1125737p='
    + str(page) + '&a1125737c=6&urltype=tree.TreeTempUrl&wbtreeid=1024'
    for page in (2, 3, 4)]
TARGETS = ['https://example.edu.cn/person/' + str(page) for page in (1, 2, 3, 4)]


def page_html(current):
    # Minimal public fixture derived from the observed p_pages/p_no_d markup.
    items = []
    for number, target in enumerate(PAGES, 1):
        if number == current:
            items.append('<span class="p_no_d">' + str(number) + '</span>')
        else:
            items.append('<span class="p_no"><a href="' + target + '">'
                         + str(number) + '</a></span>')
    return ('<title>名单</title><div class="roster"><a href="/person/'
            + str(current) + '">条目</a></div><div class="pb_sys_common">'
            + '<span class="p_pages">' + ''.join(items) + '</span></div>')


class ModelClient:
    """The external model selects actual fixture regions; parsing stays real."""
    model = 'offline-component-pager'
    max_calls = 100

    def __init__(self):
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def ask(self, label, system, payload, **kwargs):
        self.calls.append({'label': label, 'usage': {}})
        soup = BeautifulSoup(payload['html'], 'lxml')
        return {'status': 'ready',
                'roster_regions': [int(soup.select_one('.roster')['data-mb-id'])],
                'pagination_regions': [int(soup.select_one('.pb_sys_common')['data-mb-id'])],
                'exclude_regions': [], 'reason': '实际名单与独立分页区域'}


class ComponentPaginationTests(unittest.TestCase):
    def audit(self, pages=None, inputs=None, source_url=SOURCE):
        pages = pages if pages is not None else dict(zip(PAGES, map(page_html, (1, 2, 3, 4))))
        requested = []

        def respond(request):
            url = str(request.url)
            requested.append(url)
            response = pages.get(url)
            if isinstance(response, int):
                return httpx.Response(response, text='<title>访问失败</title>')
            return httpx.Response(200, text=response) if response is not None else httpx.Response(404)

        original_client = httpx.AsyncClient
        transport = httpx.MockTransport(respond)
        clock = itertools.count(10, 10)
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            root = Path(temporary)
            source = root / 'input'
            source.mkdir()
            with (source / 'college.csv').open('w', encoding='utf-8-sig', newline='') as stream:
                writer = csv.writer(stream)
                writer.writerow(['学校', '学院', '师资URL', '教师URL'])
                writer.writerows(['测试大学', '测试学院', source_url, url] for url in (inputs or TARGETS))
            config = root / 'plans.json'
            config.write_text('{"plans":{}}', encoding='utf-8')
            args = SimpleNamespace(input=source, output=root / 'output', plans=config,
                                   no_browser=True, replay=None, mode='deepseek',
                                   cache_dir=root / 'cache', max_api_calls=100, api_key=None)
            with patch('audit.httpx.AsyncClient', side_effect=lambda **kw: original_client(transport=transport, **kw)), \
                    patch('audit.time', SimpleNamespace(monotonic=lambda: next(clock))), \
                    patch('api_engine.DeepSeekJSON', return_value=ModelClient()), redirect_stdout(io.StringIO()):
                _, results, _ = asyncio.run(run(args))
            return results[0], requested

    def test_actual_component_pages_are_all_visited_and_reconciled(self):
        result, requested = self.audit()
        self.assertEqual(requested, PAGES)
        self.assertTrue(result['complete'], result['reason'])
        self.assertEqual(set(result['corrected_urls']), set(TARGETS))
        self.assertFalse(result['needs_human'])

    def test_conflicting_current_page_cannot_certify_coverage(self):
        pages = dict(zip(PAGES, map(page_html, (1, 2, 3, 4))))
        pages[SOURCE] = pages[SOURCE].replace('<span class="p_pages">', '<span>2/4</span><span class="p_pages">')
        result, requested = self.audit(pages)
        self.assertEqual(requested, PAGES)
        self.assertTrue(result['needs_human'], result['reason'])
        self.assertIn('当前页', result['reason'])

    def test_component_boundaries_are_not_discarded_as_page_parameters(self):
        for target in (PAGES[1].replace('example.edu.cn', 'other.edu.cn'),
                       PAGES[1].replace('list_photo.jsp', 'other.jsp'),
                       PAGES[1].replace('wbtreeid=1024', 'wbtreeid=1025'),
                       PAGES[1].replace('a1125737', 'a9999999'),
                       PAGES[1].replace('a1125737c=6', 'a1125737c=7'),
                       PAGES[1] + '&category=other',
                       PAGES[1].replace('urltype=tree.TreeTempUrl', 'urltype=other')):
            with self.subTest(target=target):
                pages = dict(zip(PAGES, map(page_html, (1, 2, 3, 4))))
                pages[SOURCE] = pages[SOURCE].replace('</span></div>', '<a href="' + target + '">2</a></span></div>')
                result, requested = self.audit(pages)
                self.assertNotIn(target, requested)
                self.assertTrue(result['needs_human'], result['reason'])
                self.assertFalse(result['complete'])

    def test_missing_middle_page_is_visible_in_college_coverage(self):
        pages = dict(zip(PAGES, map(page_html, (1, 2, 3, 4))))
        removed = '<span class="p_no"><a href="' + PAGES[2] + '">3</a></span>'
        pages = {url: html.replace(removed, '') for url, html in pages.items()}
        result, requested = self.audit(pages)
        self.assertEqual(requested, [PAGES[0], PAGES[1], PAGES[3]])
        self.assertTrue(result['needs_human'])
        self.assertIn('缺少页码：3', result['reason'])
        self.assertIsNone(result['stats']['missing'])

    def test_failed_component_page_preserves_input_instead_of_certifying_first_page(self):
        pages = dict(zip(PAGES, map(page_html, (1, 2, 3, 4))))
        pages[PAGES[2]] = 503
        result, requested = self.audit(pages)
        self.assertEqual(requested, PAGES)
        self.assertTrue(result['needs_human'])
        self.assertIn('缺少页码：3', result['reason'])
        self.assertIn('HTTP 503', result['reason'])
        self.assertEqual([diff['new_url'] for diff in result['diffs']], TARGETS)

    def test_page_address_disagreeing_with_current_marker_is_not_covered(self):
        pages = dict(zip(PAGES, map(page_html, (1, 2, 3, 4))))
        pages[PAGES[1]] = page_html(1)
        result, requested = self.audit(pages)
        self.assertEqual(requested, PAGES)
        self.assertTrue(result['needs_human'])
        self.assertIn('地址与当前页', result['reason'])
        self.assertIn('缺少页码：2', result['reason'])

    def test_contradictory_component_totals_stay_special(self):
        for change in ('one-target', 'whole-page'):
            with self.subTest(change=change):
                pages = dict(zip(PAGES, map(page_html, (1, 2, 3, 4))))
                url = SOURCE if change == 'one-target' else PAGES[1]
                pages[url] = pages[url].replace('a1125737t=4', 'a1125737t=5', 1 if change == 'one-target' else -1)
                result, _ = self.audit(pages)
                self.assertTrue(result['needs_human'])
                self.assertIn('组件分页', result['reason'])

    def test_unknown_script_and_missing_current_marker_stay_special(self):
        for replacement in ('<a href="javascript:nextPage()">下一页</a>', '',
                            '<span class="p_no_d">0</span>',
                            '<span class="p_no_d">1</span><span class="p_no_d">2</span>'):
            with self.subTest(replacement=replacement):
                pages = dict(zip(PAGES, map(page_html, (1, 2, 3, 4))))
                pages[SOURCE] = pages[SOURCE].replace('<span class="p_no_d">1</span>', replacement)
                result, _ = self.audit(pages)
                self.assertTrue(result['needs_human'])

    def test_complete_component_pages_still_compare_urls_and_preserve_protocol_rules(self):
        supplied = [TARGETS[0].replace('https:', 'http:'), TARGETS[1], TARGETS[1], TARGETS[2],
                    'https://example.edu.cn/person/other']
        result, requested = self.audit(inputs=supplied)
        self.assertEqual(requested, PAGES)
        self.assertFalse(result['needs_human'])
        self.assertEqual((result['stats']['missing'], result['stats']['extra']), (1, 1))
        self.assertEqual(result['stats']['protocol_changes'], 1)
        self.assertEqual(result['stats']['input_duplicates'], 1)
        self.assertEqual(set(result['corrected_urls']), set(TARGETS))

    def test_existing_pagination_controls_keep_their_queue_behavior(self):
        for suffix in ('Index_2.html', 'Index_2.aspx', 'index1.htm', 'index_2.shtml', 'shizi_2', 'szdw_2'):
            with self.subTest(suffix=suffix):
                source = 'https://example.edu.cn/staff/' + ('shizi' if suffix == 'shizi_2' else 'szdw' if suffix == 'szdw_2' else '')
                # These endpoints are exercised by the existing region tests;
                # here the public college queue must actually read the target.
                target = 'https://example.edu.cn/staff/' + suffix
                first = '<div class="roster"><a href="/person/1">条目</a></div><div class="pb_sys_common">1/2<a href="' + target + '">下一页</a></div>'
                last = '<div class="roster"><a href="/person/2">条目</a></div><div class="pb_sys_common">2/2<a class="disabled" href="?page=3">下一页</a></div>'
                result, requested = self.audit({source: first, target: last}, inputs=TARGETS[:2], source_url=source)
                self.assertEqual(requested, [source, target])
                self.assertTrue(result['complete'], result['reason'])

    def test_query_terminal_pages_and_literal_onclick_keep_their_queue_behavior(self):
        first, last = SOURCE + '&page=1', SOURCE + '&page=2'
        for target in ('<a href="' + last + '">下一页</a>',
                       '<a href="#" onclick="location.href=encodeURI(\'' + last + '\');">下一页</a>'):
            with self.subTest(target=target):
                pages = {first: '<div class="roster"><a href="/person/1">条目</a></div><div class="pb_sys_common">1/2' + target + '</div>',
                         last: '<div class="roster"><a href="/person/2">条目</a></div><div class="pb_sys_common">第[2]页 共[2]页<a href="' + SOURCE + '&page=3">后一页</a><a disabled href="' + SOURCE + '&page=4">下一页</a></div>'}
                result, requested = self.audit(pages, inputs=TARGETS[:2], source_url=first)
                self.assertEqual(requested, [first, last])
                self.assertTrue(result['complete'], result['reason'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
