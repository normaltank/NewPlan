"""Client paging through real source reads and a local Chromium origin."""
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup
from api_engine import ModelEngine
from audit import Fetcher, reconcile


HTML = '''<html><head><meta charset="utf-8"><title>名单</title><link rel="icon" href="data:,"></head><body><main class="roster">
<div id="preload" style="display:none"><a class="card" href="/person/a">甲</a><div class="card">乙</div><div class="card">丙</div></div>
<div id="visible"><a class="card" href="/person/a">甲</a><div class="card">乙</div></div></main>
<div id="pager" class="pb_sys_common"><span class="p_no_d">1</span><a data-page="2" href="javascript:;">2</a><a data-page="2" href="javascript:;">下页</a><a data-page="2" href="javascript:;">尾页</a></div>
<script>
const cards=[...document.querySelector('#preload').children];
function render(n){document.querySelector('#visible').innerHTML=cards.slice((n-1)*2,n*2).map(x=>x.outerHTML).join('');
document.querySelector('#pager').innerHTML='<span class="p_no_d">'+n+'</span>'+ (n===1?'<a data-page="2" href="javascript:;">2</a><a data-page="2" href="javascript:;">下页</a><a data-page="2" href="javascript:;">尾页</a>':'<a data-page="1" href="javascript:;">1</a><span class="p_next p_fun_d">下页</span><span class="p_last p_fun_d">尾页</span>');
history.replaceState(null,'',n===1?location.pathname:location.pathname+'#page='+n);}
document.querySelector('#pager').addEventListener('click',e=>{if(e.target.dataset.page)render(+e.target.dataset.page)});render(1);
</script></body></html>'''


class Client:
    model = 'local-selection'
    max_calls = 50
    def __init__(self, selector='.roster'): self.calls, self.selector = [], selector
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    async def ask(self, label, system, payload, **kw):
        self.calls.append({'label': label})
        soup = BeautifulSoup(payload['html'], 'lxml')
        selector = self.selector[0 if label.endswith('locate') else 1] if isinstance(self.selector,tuple) else self.selector
        return {'status':'ready', 'roster_regions':[int(soup.select_one(selector)['data-mb-id'])],
                'pagination_regions':[int(soup.select_one('.pb_sys_common')['data-mb-id'])],
                'exclude_regions':[], 'reason':'实际名单'}


class ClientPaginationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from runtime_paths import browser_path
        from playwright.sync_api import sync_playwright
        executable = browser_path()
        if not executable:
            with sync_playwright() as pw:
                executable = pw.chromium.executable_path
        if not Path(executable).exists():
            raise unittest.SkipTest('Chromium not installed; no download attempted')

    def read(self, html=HTML, selector='.roster', cancel=None, inputs=None, browser=True):
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path)
                self.send_response(200 if self.path == '/staff.html' else 404)
                self.send_header('Content-Type','text/html; charset=utf-8'); self.end_headers()
                self.wfile.write(html.encode('utf-8'))
            def log_message(self, *args): pass
        server = ThreadingHTTPServer(('127.0.0.1',0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        url = 'http://127.0.0.1:' + str(server.server_port) + '/staff.html'
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            async def run():
                async with Fetcher(out, browser=browser) as fetcher, ModelEngine(out, out/'cache', None,
                        client=Client(selector), should_cancel=cancel) as engine:
                    return await engine.read(fetcher, {'id':'local','roster_url':url}, None, [url])
            try:
                with patch.dict(os.environ, {'NO_PROXY':'127.0.0.1,localhost'}):
                    source = asyncio.run(run())
                target = url.replace('/staff.html','/person/a')
                task = {'rows':[{'url':u,'value':u,'file':'input','sheet':'1','row':i,'hyperlink_mismatch':False}
                                for i,u in enumerate(inputs or [target],1)]}
                result = reconcile(task, source['parsed'])
                evidence = {str(p.relative_to(out)):p.read_text('utf-8') for p in out.rglob('*.json')}
                (out/'public-results.json').write_text(json.dumps({'source':source,'result':result,'requests':requests},ensure_ascii=False,indent=2),encoding='utf-8')
                return source, result, requests, evidence
            finally:
                if os.environ.get('CLIENT_PAGING_EVIDENCE'):
                    root = Path(os.environ['CLIENT_PAGING_EVIDENCE'])/self._testMethodName
                    root.mkdir(parents=True,exist_ok=True)
                    destination = root/str(len(list(root.iterdir()))+1)
                    shutil.copytree(out,destination)
                server.shutdown(); server.server_close(); thread.join()

    def test_complete_client_pages_preserve_links_and_plain_entries(self):
        source, result, requests, evidence = self.read()
        self.assertTrue(result['complete'], result['reason'])
        self.assertEqual(len(result['corrected_urls']),1)
        self.assertTrue(all(p == '/staff.html' for p in requests), requests)
        self.assertIn('client_pagination', source['parsed'])
        self.assertEqual([len(p['entries']) for p in source['parsed']['client_pagination']['pages']], [2,1])

    def test_same_url_set_and_entry_count_cannot_hide_a_missing_plain_entry(self):
        changed = HTML.replace('cards.slice((n-1)*2,n*2)', '(n===2?[cards[1]]:cards.slice(0,2))')
        source, result, _, _ = self.read(changed)
        self.assertTrue(result['needs_human'])
        self.assertIn('条目多重集不一致', result['reason'])
        self.assertEqual(result['corrected_urls'], [])
        self.assertEqual(result['diffs'][0]['action'], '未判定，原样保留')

    def test_pager_network_is_blocked_before_teacher_or_extra_source_access(self):
        for action in ("fetch('/person/a')", "location.href='/person/a'", "fetch('/extra')"):
            with self.subTest(action=action):
                html = HTML.replace('render(+e.target.dataset.page)', '{' + action + ';render(+e.target.dataset.page)}')
                source, result, requests, _ = self.read(html)
                self.assertTrue(result['needs_human'], result['reason'])
                self.assertTrue(source['parsed']['client_pagination']['blocked_requests'])
                self.assertTrue(all(p == '/staff.html' for p in requests), requests)

    def test_unknown_script_and_extra_event_are_never_excused(self):
        for html in (HTML.replace('data-page="2" href="javascript:;"', 'data-page="2" href="javascript:unknown()"'),
                     HTML.replace('id="pager" class=', 'id="pager" onclick="unknown()" class=')):
            with self.subTest(html=html):
                source, result, _, _ = self.read(html)
                self.assertTrue(result['needs_human'], result['reason'])
                self.assertEqual(result['corrected_urls'], [])

    def test_model_selection_must_cover_plain_preload_entries(self):
        source, result, _, _ = self.read(selector='#visible')
        self.assertTrue(result['needs_human'])
        self.assertFalse(source['parsed'].get('client_pagination',{}).get('complete'))

    def test_other_uncertainty_survives_complete_client_paging(self):
        html = HTML.replace('id="preload"', 'id="preload" hidden')
        source, result, _, _ = self.read(html)
        self.assertTrue(source['parsed']['client_pagination']['complete'])
        self.assertTrue(result['needs_human'])
        self.assertIn('标记为隐藏', result['reason'])

    def test_observed_original_cards_cover_16_plus_2_and_seven_exact_urls(self):
        html = (Path(__file__).parent/'fixtures/client_preload_observed.html').read_text('utf-8')
        source, result, requests, _ = self.read(html, selector='.page-layout')
        self.assertTrue(result['complete'], result['reason'])
        proof = source['parsed']['client_pagination']
        self.assertEqual([len(p['entries']) for p in proof['pages']], [16,2])
        self.assertEqual(proof['entry_count'],18)
        self.assertEqual({u.split('/contents/')[-1] for u in result['corrected_urls']},
                         {'4021/12926.html','4021/12927.html','4021/14536.html','4021/13209.html',
                          '4021/13210.html','4021/14931.html','4021/15036.html'})
        self.assertEqual(sum(not e['urls'] for p in proof['pages'] for e in p['entries']),11)
        self.assertTrue(all(p == '/staff.html' for p in requests), requests)

    def test_loop_missing_terminal_contradiction_preload_change_and_limit_stay_pending(self):
        variants = [
            HTML.replace('render(+e.target.dataset.page)', 'render(1)'),
            HTML.replace('p_next p_fun_d', 'p_next').replace('p_last p_fun_d','p_last'),
            HTML.replace("'<span class=\"p_no_d\">'+n", "'<span>1/3</span><span class=\"p_no_d\">'+n"),
            HTML.replace('render(+e.target.dataset.page)', "{document.querySelector('#preload').lastElementChild.textContent='变';render(+e.target.dataset.page)}"),
            HTML.replace('data-page="2" href="javascript:;">尾页', 'data-page="31" href="javascript:;">尾页'),
        ]
        for html in variants:
            with self.subTest(html=html):
                _, result, _, _ = self.read(html)
                self.assertTrue(result['needs_human'], result['reason'])
                self.assertEqual(result['corrected_urls'], [])

    def test_two_model_selections_are_not_replaced_by_browser_evidence(self):
        _, result, _, _ = self.read(selector=('#preload','#visible'))
        self.assertTrue(result['needs_human'])
        self.assertIn('两次结构判断', result['reason'])

    def test_stop_preserves_evidence_and_interrupts_before_client_clicks(self):
        calls = []
        def cancelled():
            calls.append(1)
            return len(calls) >= 3
        with self.assertRaises(InterruptedError):
            self.read(cancel=cancelled)


class OfflineReadTests(unittest.TestCase):
    def test_missing_browser_does_not_certify_a_preloaded_roster(self):
        runner = ClientPaginationTests('test_complete_client_pages_preserve_links_and_plain_entries')
        source, result, requests, _ = runner.read(browser=False)
        self.assertTrue(result['needs_human'])
        self.assertIn('下一页依赖脚本', result['reason'])
        self.assertEqual(len(source['parsed']['links']), 1)
        self.assertEqual(requests, ['/staff.html'])


if __name__ == '__main__': unittest.main()
