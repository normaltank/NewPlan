import unittest
import tempfile
from pathlib import Path
from copy import deepcopy
from api_engine import ModelEngine
from audit import reconcile
from reporting import verification_summary
from ai_regions import prepare
from api_engine import qualification

URL = 'https://example.edu/staff'
CARDS = '<div class="cards">' + ''.join('<div class="card"><img src="x"><div class="info"><a href="/'+c+'">条目</a><p>简介</p></div></div>' for c in 'abcdef') + '</div>'

def evaluate(html, selectors, exclude=()):
    soup, nodes, anchors, _ = prepare(html, URL)
    plan = {'status':'ready', 'roster_regions':[int(n['data-mb-id']) for selector in selectors for n in soup.select(selector)], 'pagination_regions':[], 'exclude_regions':[{'id':int(soup.select_one(s)['data-mb-id']), 'kind':kind, 'reason':'结构明确'} for s,kind in exclude], 'reason':'名单'}
    return qualification(soup, nodes, anchors, [plan,plan], URL)[0]

class ParallelCoverageTests(unittest.TestCase):
    def test_agreed_first_card_cannot_certify_parallel_roster(self):
        result = evaluate(CARDS, ['.card:first-child'])
        self.assertFalse(result['complete'], result)
        self.assertEqual(set(result['links']), {'https://example.edu/a'})
        self.assertTrue(any('平行' in issue for issue in result['issues']))

    def test_complete_cards_and_parallel_groups_keep_exact_url_set(self):
        for html, selectors in [(CARDS, ['.cards']), (CARDS + CARDS, ['.cards'])]:
            result = evaluate(html, selectors)
            self.assertTrue(result['complete'], result['issues'])
            self.assertEqual(set(result['links']), {'https://example.edu/'+c for c in 'abcdef'})

    def test_omitted_parallel_group_stays_pending(self):
        result = evaluate('<main>'+CARDS+CARDS.replace('href="/a"', 'href="/g"')+'</main>', ['.cards:first-child'])
        self.assertFalse(result['complete'])
        self.assertNotIn('https://example.edu/g', result['links'])

    def test_navigation_related_and_pager_exclusions_never_add_urls(self):
        html = '<main>'+CARDS+CARDS.replace('cards', 'news').replace('href="/a"', 'href="/news"')+'</main>'
        result = evaluate(html, ['.card:first-child'], [('.news', 'related')])
        self.assertFalse(result['complete'])
        self.assertEqual(set(result['links']), {'https://example.edu/a'})
        for kind in ('navigation', 'related', 'pagination'):
            result = evaluate('<main>'+CARDS+CARDS.replace('cards', 'other')+'</main>', ['.cards'], [('.other', kind)])
            self.assertTrue(result['complete'], result['issues'])
            self.assertEqual(set(result['links']), {'https://example.edu/'+c for c in 'abcdef'})

    def test_text_only_and_duplicate_urls_do_not_create_missing_targets(self):
        html = CARDS.replace('href="/b"', 'href="/a"').replace('<a href="/c">条目</a>', '条目')
        result = evaluate(html, ['.card:first-child', '.card:nth-child(4)', '.card:nth-child(5)', '.card:nth-child(6)'])
        self.assertTrue(result['complete'], result['issues'])
        self.assertEqual(set(result['links']), {'https://example.edu/'+c for c in 'adef'})

    def test_selected_anchor_does_not_require_other_links_in_its_own_container(self):
        result = evaluate('<div><a href="/a">条目</a><section><a href="/news">新闻</a></section></div>', ['div > a'])
        self.assertTrue(result['complete'], result['issues'])
        self.assertEqual(set(result['links']), {'https://example.edu/a'})


class FrozenClient:
    model = 'offline-frozen'
    def __init__(self, plans, budget):
        self.plans, self.max_calls, self.calls, self.payloads = plans, budget, [], []
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    async def ask(self, label, system, payload, **kwargs):
        plan = deepcopy(self.plans[len(self.calls)])
        self.calls.append({'label':label})
        self.payloads.append(payload)
        return plan


class CoverageSourceTests(unittest.IsolatedAsyncioTestCase):
    async def run_source(self, budget, repair):
        soup, _, _, _ = prepare(CARDS, URL)
        small = {'status':'ready', 'roster_regions':[int(soup.select_one('.card')['data-mb-id'])], 'pagination_regions':[], 'exclude_regions':[], 'reason':'首卡'}
        good = {**small, 'roster_regions':[int(soup.select_one('.cards')['data-mb-id'])], 'reason':'全部卡片'}
        client = FrozenClient([small, small, good if repair else small, good if repair else small], budget)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            async with ModelEngine(root/'out', root/'cache', None, client=client) as engine:
                result = await engine.analyze(CARDS, URL, root/'out'/'source')
            initial = root/'out'/'source'/'plans-initial.json'
            self.assertTrue(initial.exists())
        task = {'id':'coverage', 'school':'测试大学', 'college':'测试学院', 'roster_url':URL,
                'rows':[{'file':'input.xlsx','sheet':'名单','row':i+2,'value':'https://example.edu/'+c,'url':'https://example.edu/'+c, 'values':[], 'hyperlink_mismatch':False} for i,c in enumerate('abcdef')]}
        reconciled = reconcile(task, result)
        return result, reconciled, client

    async def test_agreed_omission_rechecks_independently_and_can_recover(self):
        result, reconciled, client = await self.run_source(4, True)
        self.assertTrue(result['complete'], result['issues'])
        self.assertEqual(set(result['links']), {'https://example.edu/'+c for c in 'abcdef'})
        self.assertEqual(verification_summary(reconciled)['verification_result'], '正确')
        self.assertEqual(len(client.calls), 4)
        for payload in client.payloads[2:]:
            self.assertNotIn('other_selection', payload)
            self.assertIn('container', str(payload['structural_feedback']))
            self.assertIn('uncovered_peers', str(payload['structural_feedback']))
            self.assertEqual(payload['previous_selection']['reason'], '首卡')

    async def test_budget_or_persistent_omission_preserves_input_and_special_status(self):
        for budget in (2, 3, 4):
            result, reconciled, client = await self.run_source(budget, False)
            self.assertFalse(result['complete'])
            self.assertEqual(verification_summary(reconciled)['verification_result'], '特殊情况')
            self.assertEqual(len(reconciled['diffs']), 6)
            self.assertEqual([d['new_url'] for d in reconciled['diffs']], ['https://example.edu/'+c for c in 'abcdef'])
            self.assertEqual(len(client.calls), 4 if budget == 4 else 2)

if __name__ == '__main__': unittest.main()
