"""Failures reduced from the October 26 support logs."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from ai_regions import prepare
from api_engine import ModelEngine, qualification, check_coverage
from audit import pagination_family

URL = 'https://example.edu.cn/staff/index.htm'
ROSTER = '<div class="outer"><nav><a href="/news">新闻</a></nav><ul class="roster"><li><a href="/a">甲</a></li><li><a href="/b">乙</a></li></ul></div>'


def answer(html, *, conflict=False, first=False, empty=False):
    soup, _, _, _ = prepare(html, URL)
    ident = lambda selector: int(soup.select_one(selector)['data-mb-id'])
    return {'status': 'no_links' if empty else 'ready',
            'roster_regions': [ident('.roster li' if first else '.roster')],
            'pagination_regions': [ident('.pager')] if soup.select_one('.pager') else [],
            'exclude_regions': [{'id': ident('.outer' if conflict else 'nav'),
                                 'kind': 'navigation', 'reason': '侧栏导航'}],
            'reason': '名单正文'}


def evaluate(html, url=URL):
    soup, nodes, anchors, _ = prepare(html, url)
    plans = [answer(html), answer(html)]
    return qualification(soup, nodes, anchors, plans, url)[0]


class PagingLogTests(unittest.TestCase):
    def test_observed_paging_families_and_scope(self):
        for first, second in [('Index.html', 'Index_2.html'), ('Index.aspx', 'Index_15.aspx'),
                              ('index.htm', 'index1.htm'), ('', 'index_2.shtml'),
                              ('shizi', 'shizi_2'), ('szdw', 'szdw_2')]:
            with self.subTest(first=first):
                base = 'https://example.edu.cn/staff/'
                self.assertEqual(pagination_family(base + first), pagination_family(base + second))
        for other in ('https://other.edu.cn/staff/Index_2.html',
                      'https://example.edu.cn/news/Index_2.html',
                      'https://example.edu.cn/staff/article_2.html'):
            self.assertNotEqual(pagination_family(URL), pagination_family(other))
        self.assertNotEqual(pagination_family('https://example.edu.cn/content_123'),
                            pagination_family('https://example.edu.cn/content_456'))

    def test_fixed_onclick_paging_is_followed_but_never_a_teacher(self):
        html = ROSTER + '''<div class="pager">共75条记录 1/6页
        <a href="#" onclick="location.href=encodeURI('index_2.shtml');">下一页</a>
        <a href="#" onclick="location.href=encodeURI('index_6.shtml');">尾页</a></div>'''
        result = evaluate(html, 'https://example.edu.cn/staff/')
        self.assertTrue(result['complete'], result['issues'])
        self.assertEqual(set(result['links']), {'https://example.edu.cn/a', 'https://example.edu.cn/b'})
        self.assertEqual(result['pagination_urls'], ['https://example.edu.cn/staff/index_2.shtml',
                                                    'https://example.edu.cn/staff/index_6.shtml'])
        check_coverage([{'roster_url': 'https://example.edu.cn/staff/', 'parsed': result}])
        self.assertFalse(result['complete'])

    def test_unknown_script_and_cross_column_target_still_require_review(self):
        for script in ("goNext()", "location.href=encodeURI('/news/index_2.shtml');",
                       "location.href=encodeURI('index_2.shtml');sendData()"):
            result = evaluate(ROSTER + '<div class="pager">1/2<a href="#" onclick="' + script + '">下一页</a></div>')
            self.assertFalse(result['complete'], script)
            self.assertFalse(result['pagination_urls'])

    def test_unselected_script_pager_stays_incomplete(self):
        html = ROSTER + '''<div class="pager"><a href="#" onclick="location.href=encodeURI('index_2.shtml');">下一页</a></div>'''
        soup, nodes, anchors, _ = prepare(html, URL)
        plan = answer(html); plan['pagination_regions'] = []
        result, _ = qualification(soup, nodes, anchors, [plan, plan], URL)
        self.assertFalse(result['complete'])
        self.assertIn('未被识别为分页区域', '；'.join(result['issues']))

    def test_disabled_terminal_controls_do_not_invent_another_page(self):
        html = ROSTER + '''<div class="pager"><a class="current">1</a>
        <a class="next disabled" href="javascript:void(0);">下一页</a>
        <a disabled href="?page=2">尾页</a><span>共1条信息/共1页</span></div>'''
        result = evaluate(html)
        self.assertTrue(result['complete'], result['issues'])
        self.assertEqual(result['pager_counters'], [(1, 1)])
        self.assertFalse(result['pagination_urls'])

    def test_chinese_counter_variants_keep_missing_middle_page_visible(self):
        for text in ('共22条，分3页，当前第 1 页', '第1页/总共3页,共22条'):
            result = evaluate(ROSTER + '<div class="pager">' + text + '<a href="index2.htm">尾页</a></div>')
            self.assertEqual(result['pager_counters'], [(1, 3)])
            check_coverage([{'roster_url': URL, 'parsed': result}])
            self.assertFalse(result['complete'])
            self.assertIn('缺少页码：2,3', '；'.join(result['issues']))


class SequenceClient:
    model = 'test-model'
    def __init__(self, plans, budget=20):
        self.plans, self.max_calls, self.calls, self.payloads = plans, budget, [], []
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    async def ask(self, label, system, payload, **kwargs):
        result = deepcopy(self.plans[len(self.calls)])
        self.calls.append({'label': label, 'usage': {}})
        self.payloads.append(payload)
        return result


class SelectionRepairTests(unittest.IsolatedAsyncioTestCase):
    async def run_engine(self, client, html=ROSTER):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            async with ModelEngine(root/'out', root/'cache', None, client=client) as engine:
                result = await engine.analyze(html, URL, root/'out'/'page')
                evidence = {p.name: p.read_text('utf-8') for p in (root/'out'/'page').glob('*.json')}
                return result, evidence

    async def test_ancestor_exclusion_is_rechecked_and_both_plans_retained(self):
        bad, good = answer(ROSTER, conflict=True), answer(ROSTER)
        client = SequenceClient([bad, good, good, good])
        result, evidence = await self.run_engine(client)
        self.assertTrue(result['complete'], result['issues'])
        self.assertEqual(len(client.calls), 4)
        self.assertEqual(len(result['links']), 2)
        self.assertIn('plans-initial.json', evidence)
        self.assertEqual(json.loads(evidence['plans-initial.json'])['plans'], [bad, good])
        self.assertEqual(client.payloads[2]['previous_selection'], bad)
        self.assertEqual(client.payloads[3]['previous_selection'], good)

    async def test_first_item_selection_gets_one_independent_recheck(self):
        small, good = answer(ROSTER, first=True), answer(ROSTER)
        client = SequenceClient([small, good, good, good])
        result, _ = await self.run_engine(client)
        self.assertTrue(result['complete'], result['issues'])
        self.assertEqual(len(result['links']), 2)
        self.assertEqual(len(client.calls), 4)

    async def test_persistent_disagreement_or_conflict_stays_special(self):
        good = answer(ROSTER)
        for bad in (answer(ROSTER, first=True), answer(ROSTER, conflict=True)):
            client = SequenceClient([bad, good, bad, good])
            result, _ = await self.run_engine(client)
            self.assertFalse(result['complete'])
            self.assertEqual(len(client.calls), 4)

    async def test_budget_shortfall_does_not_accept_a_single_recheck(self):
        client = SequenceClient([answer(ROSTER, conflict=True), answer(ROSTER)], budget=3)
        result, _ = await self.run_engine(client)
        self.assertFalse(result['complete'])
        self.assertEqual(len(client.calls), 2)

    async def test_recheck_agreement_on_urls_cannot_override_uncertain_scope(self):
        good, bad = answer(ROSTER), answer(ROSTER, conflict=True)
        uncertain = {**good, 'status': 'uncertain', 'reason': '主体仅为其他名册的入口目录'}
        client = SequenceClient([bad, good, uncertain, uncertain])
        result, _ = await self.run_engine(client)
        self.assertFalse(result['complete'])
        self.assertIn('不能确认名单范围', '；'.join(result['issues']))
        self.assertEqual(len(client.calls), 4)

    async def test_real_zero_links_and_good_results_do_not_recheck(self):
        for html, empty in [(ROSTER, False), ('<nav></nav><div class="roster">甲、乙</div>', True)]:
            plan = answer(html, empty=empty)
            client = SequenceClient([plan, plan])
            result, _ = await self.run_engine(client, html)
            self.assertEqual(result['complete'], not empty)
            self.assertEqual(len(client.calls), 2)


if __name__ == '__main__':
    unittest.main()
