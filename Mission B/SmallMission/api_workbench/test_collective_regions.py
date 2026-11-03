"""Frozen provider responses check URL handling, not model interpretation."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from ai_regions import prepare
from api_engine import ModelEngine
from audit import reconcile
from reporting import verification_summary


URL = 'https://example.edu/overview/staff.htm'
ARTICLE = '''<title>师资队伍</title><nav><a href="/staff-directory">教授名册</a></nav>
<main><h1>师资队伍</h1><ul class="articles"><li>
<a href="../info/team.htm">学院师资队伍</a><span>2025-12-19</span>
</li></ul></main>'''


class FrozenClient:
    model = 'offline-frozen'
    max_calls = 2

    def __init__(self, plans):
        self.plans, self.calls = plans, []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def ask(self, label, system, payload, **kwargs):
        answer = deepcopy(self.plans[len(self.calls)])
        self.calls.append({'label': label})
        return answer


def selection(html, status='ready', selector='.articles', exclude=()):
    soup, _, _, _ = prepare(html, URL)
    return {'status': status,
            'roster_regions': [int(soup.select_one(selector)['data-mb-id'])] if selector else [],
            'pagination_regions': [],
            'exclude_regions': [{'id': int(soup.select_one(item)['data-mb-id']),
                                 'kind': 'navigation', 'reason': '独立栏目导航'} for item in exclude],
            'reason': '冻结结构判断；不代表新提示模型验证'}


class CollectiveSourceTests(unittest.IsolatedAsyncioTestCase):
    async def evaluate(self, html, plans, original=('https://example.edu/info/team.htm',)):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            async with ModelEngine(root/'out', root/'cache', None, client=FrozenClient(plans)) as engine:
                result = await engine.analyze(html, URL, root/'out'/'source')
        task = {'id': 'collective', 'school': '测试大学', 'college': '测试学院', 'roster_url': URL,
                'rows': [{'file': 'input.xlsx', 'sheet': '名单', 'row': i+2, 'value': url,
                          'url': url, 'values': [], 'hyperlink_mismatch': False}
                         for i, url in enumerate(original)]}
        reconciled = reconcile(task, result)
        return result, reconciled, verification_summary(reconciled)

    async def test_agreed_collective_article_keeps_exact_url_and_excludes_directory(self):
        plan = selection(ARTICLE, exclude=('nav',))
        result, _, summary = await self.evaluate(ARTICLE, [plan, plan])
        self.assertTrue(result['complete'], result['issues'])
        self.assertEqual(set(result['links']), {'https://example.edu/info/team.htm'})
        self.assertEqual(summary['verification_result'], '正确')

    async def test_uncertain_qualification_does_not_promote_article_or_delete_input(self):
        # Dated article layout alone cannot establish a roster: mixed topics,
        # independent directories, and general news still need qualification.
        for html in (ARTICLE,
                     ARTICLE.replace('学院师资队伍', '教师培训与教学获奖'),
                     '<main class="articles"><a href="/list">教授名册</a><a href="/other">导师名册</a></main>',
                     ARTICLE.replace('师资队伍', '学院新闻')):
            with self.subTest(html=html):
                uncertain = selection(html, 'uncertain', None)
                result, reconciled, summary = await self.evaluate(html, [uncertain, uncertain])
                self.assertFalse(result['complete'])
                self.assertEqual(result['links'], {})
                self.assertEqual(summary['verification_result'], '特殊情况')
                self.assertEqual([d['new_url'] for d in reconciled['diffs']],
                                 ['https://example.edu/info/team.htm'])

    async def test_disagreement_on_collective_qualification_stays_special(self):
        ready = selection(ARTICLE)
        uncertain = selection(ARTICLE, 'uncertain', None)
        result, _, summary = await self.evaluate(ARTICLE, [ready, uncertain])
        self.assertFalse(result['complete'])
        self.assertEqual(summary['verification_result'], '特殊情况')

    async def test_agreed_linkless_collective_text_cannot_clear_original(self):
        html = '<main class="articles">学院师资队伍：甲、乙教师介绍</main>'
        plan = selection(html, 'no_links')
        result, reconciled, summary = await self.evaluate(html, [plan, plan])
        self.assertFalse(result['complete'])
        self.assertEqual(summary['verification_result'], '特殊情况')
        self.assertEqual([d['new_url'] for d in reconciled['diffs']],
                         ['https://example.edu/info/team.htm'])

    async def test_collective_article_with_uncovered_parallel_article_stays_special(self):
        html = ARTICLE.replace('</li></ul>', '</li><li><a href="/other-team">另一团队介绍</a><span>2025-12-19</span></li></ul>')
        plan = selection(html, selector='.articles li')
        result, _, summary = await self.evaluate(html, [plan, plan])
        self.assertFalse(result['complete'])
        self.assertEqual(set(result['links']), {'https://example.edu/info/team.htm'})
        self.assertEqual(summary['verification_result'], '特殊情况')


if __name__ == '__main__':
    unittest.main()
