"""2026-10-22 live counterexample: JS photo roster was never rendered after zero links."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup
from api_engine import ModelEngine
from audit import Fetcher
from runtime_paths import APP_ROOT

URL = 'https://jgxy.slxy.edu.cn/szdw/jsfc1.htm'
FIXTURES = APP_ROOT / 'tests/fixtures/live_20261022'


class FixtureAPI:
    model = 'offline-fixture'
    max_calls = 20

    def __init__(self, disagree=False):
        self.calls = []
        self.disagree = disagree

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def ask(self, label, system, payload, **kwargs):
        self.calls.append({'label':label,'usage':{}})
        soup = BeautifulSoup(payload['html'], 'lxml')
        root = soup.select_one('#u_u5_imgcontent, .roster')
        if self.disagree:
            root = root.select('a')[len(self.calls) % 2]
        pagers = soup.select('.pb_sys_common')
        return {'status':'ready', 'roster_regions':[int(root['data-mb-id'])],
                'pagination_regions':[int(n['data-mb-id']) for n in pagers], 'exclude_regions':[], 'reason':'saved fixture'}


class RenderFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def read(self, static, rendered, *, failure=False, disagree=False):
        with tempfile.TemporaryDirectory(dir=APP_ROOT) as directory:
            root = Path(directory)
            fetcher = Fetcher(root / 'out')
            rendered_calls = []
            async def http(task):
                meta = {'method':'HTTP','status':200,'requested_url':URL,'final_url':URL}
                fetcher.save(task['id'], 'http', static, meta)
                return static, meta
            async def browser(task):
                rendered_calls.append(task['roster_url'])
                meta = {'method':'独立浏览器','status':400 if failure else 200,'requested_url':URL,'final_url':URL}
                if failure:
                    meta['error'] = 'isolated browser failure'
                fetcher.save(task['id'], 'browser', rendered, meta)
                return rendered, meta
            fetcher.http, fetcher.browser_fetch = http, browser
            client = FixtureAPI(disagree)
            async with ModelEngine(root / 'out', root / 'cache', None, client=client) as engine:
                source = await engine.read(fetcher, {'id':'fixture','roster_url':URL}, None, [URL])
            return source, rendered_calls, client.calls

    async def test_live_empty_static_anchors_render_into_six_real_profile_urls(self):
        source, renders, calls = await self.read((FIXTURES/'shangluo-http.html').read_text(encoding='utf-8'),
                                                (FIXTURES/'shangluo-browser.html').read_text(encoding='utf-8'))
        self.assertEqual(renders, [URL])
        self.assertTrue(source['parsed']['complete'], source['parsed']['issues'])
        self.assertEqual(set(source['parsed']['links']),
                         {f'https://jgxy.slxy.edu.cn/info/1148/{ident}.htm' for ident in ('3768','3552','3551','3550','3548','3547')})
        self.assertEqual(len(calls), 4)
        self.assertEqual(source['attempts'][-1]['method'], '独立浏览器')

    async def test_unchanged_zero_stays_special_without_repeating_model_calls(self):
        html = '<div class="roster"><a href="/hidden"></a>名单待更新</div>'
        source, renders, calls = await self.read(html, html)
        self.assertEqual(renders, [URL])
        self.assertFalse(source['parsed']['complete'])
        self.assertEqual(source['parsed']['links'], {})
        self.assertEqual(len(calls), 2)
        self.assertTrue(source['attempts'][-1]['selected_after_identical_render'])

    async def test_failed_render_does_not_make_zero_or_input_deletable(self):
        source, renders, calls = await self.read('<div class="roster">名单待更新</div>', '', failure=True)
        self.assertEqual(renders, [URL])
        self.assertFalse(source['parsed']['complete'])
        self.assertTrue(source['attempts'][-1]['selected_after_browser_failure'])
        self.assertEqual(len(calls), 2)

    async def test_successful_static_page_does_not_render(self):
        html = '<div class="roster"><a href="/a">甲</a><a href="/b">乙</a></div>'
        source, renders, calls = await self.read(html, html)
        self.assertTrue(source['parsed']['complete'])
        self.assertEqual(renders, [])
        self.assertEqual(len(calls), 2)

    async def test_nonzero_model_disagreement_remains_special(self):
        html = '<div class="roster"><a href="/a">甲</a><a href="/b">乙</a></div>'
        source, renders, calls = await self.read(html, html, disagree=True)
        self.assertFalse(source['parsed']['complete'])
        self.assertIn('两次结构判断选择的实际链接不一致', '；'.join(source['parsed']['issues']))
        self.assertEqual(renders, [])


if __name__ == '__main__':
    unittest.main()
