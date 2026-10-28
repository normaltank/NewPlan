"""Public HTML -> qualified source regressions for inert roster anchors."""
from pathlib import Path
import unittest
from ai_regions import prepare
from api_engine import qualification

URL = 'https://example.edu.cn/staff/index.htm'
FIXTURE = Path(__file__).parent / 'tests/fixtures/noop_roster.html'
EXPECTED = {'https://example.edu.cn/profiles/alpha.htm', 'https://example.edu.cn/profiles/beta.htm'}


def evaluate(html):
    soup, nodes, anchors, _ = prepare(html, URL)
    plan = {'status': 'ready', 'roster_regions': [int(soup.select_one('.roster')['data-mb-id'])],
            'pagination_regions': [int(soup.select_one('.pager')['data-mb-id'])] if soup.select_one('.pager') else [], 'exclude_regions': [], 'reason': '名单条目'}
    return qualification(soup, nodes, anchors, [plan, plan], URL)[0]


class NoopRosterTests(unittest.TestCase):
    def test_summary_and_missing_profile_placeholders_keep_only_real_urls(self):
        result = evaluate(FIXTURE.read_text('utf-8'))
        self.assertEqual(set(result['links']), EXPECTED)
        self.assertTrue(result['complete'], result['issues'])

    def test_unknown_terminal_pager_event_is_not_certified_as_inert(self):
        html = FIXTURE.read_text('utf-8') + '<div class="pager">1/1<a href="javascript:void(0)" onclick="openTeacher()">末页</a></div>'
        result = evaluate(html)
        self.assertFalse(result['complete'], result['issues'])

    def test_unknown_scripts_and_event_navigation_require_review(self):
        original = FIXTURE.read_text('utf-8')
        for replacement in (
            'href="javascript:loadTeacher(42)"',
            'href="javascript:void(0);location.href=\'/other\'"',
            'href="javascript:VOID(0)"',
            'href="javascript:;" onclick="location.href=\'/other\'"',
            'href="javascript:;" onmousedown="openTeacher()"',
            'href="#" onclick="openTeacher()"',
        ):
            with self.subTest(replacement=replacement):
                result = evaluate(original.replace('href="javascript:;"', replacement))
                self.assertFalse(result['complete'])
                self.assertIn('名单存在脚本链接，目标尚未确定', result['issues'])

    def test_http_link_with_click_tracking_keeps_existing_success(self):
        html = FIXTURE.read_text('utf-8').replace('href="/profiles/alpha.htm"',
            'href="/profiles/alpha.htm" onclick="trackClick()"')
        result = evaluate(html)
        self.assertTrue(result['complete'], result['issues'])
        self.assertEqual(set(result['links']), EXPECTED)

    def test_exact_noop_spellings_preserve_real_links(self):
        for href in ('javascript:;', 'javascript:void(0)', 'javascript:void(0);', ' JavaScript:void(0); '):
            result = evaluate(FIXTURE.read_text('utf-8').replace('javascript:;', href))
            self.assertTrue(result['complete'], result['issues'])
            self.assertEqual(set(result['links']), EXPECTED)

    def test_no_http_roster_remains_special_even_with_only_noops(self):
        for content in ('<li>甲</li>', '<li><img alt="甲" src="/portrait.png"></li>',
                        '<li><a href="javascript:void(0)">甲</a></li>'):
            result = evaluate('<ul class="roster">' + content + '</ul>')
            self.assertFalse(result['complete'])
            self.assertEqual(result['links'], {})
            self.assertIn('名单零链接须人工确认', '；'.join(result['issues']))

    def test_plain_http_success_control_and_fixed_onclick_paging(self):
        html = '<ul class="roster"><li><a href="/profiles/alpha.htm">甲</a></li></ul>'
        html += """<div class="pager">1/2<a href="#" onclick="location.href=encodeURI('index_2.htm');">下一页</a></div>"""
        result = evaluate(html)
        self.assertTrue(result['complete'], result['issues'])
        self.assertEqual(set(result['links']), {'https://example.edu.cn/profiles/alpha.htm'})
        self.assertEqual(result['pagination_urls'], ['https://example.edu.cn/staff/index_2.htm'])


if __name__ == '__main__':
    unittest.main()
