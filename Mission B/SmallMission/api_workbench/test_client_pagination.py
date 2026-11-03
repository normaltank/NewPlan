"""Client paging through real source reads and a local Chromium origin."""
import asyncio
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from api_engine import ModelEngine
from audit import Fetcher, reconcile, run
from openpyxl import load_workbook
from runtime_paths import APP_ROOT
from test_multisource import paired_file


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
                                for i,u in enumerate([urljoin(url,u) for u in inputs] if inputs is not None else [target],1)]}
                result = reconcile(task, source['parsed'])
                evidence = {p.relative_to(out).as_posix():p.read_text('utf-8') for p in out.rglob('*') if p.suffix in {'.json','.html'}}
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

    def test_api_run_exports_client_pages_with_exact_urls_and_three_categories(self):
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path)
                self.send_response(200 if self.path in {'/staff.html','/wrong.html','/pending.html'} else 404)
                self.send_header('Content-Type', 'text/html; charset=utf-8'); self.end_headers()
                body = HTML.replace('id="preload"', 'id="preload" hidden') if self.path == '/pending.html' else HTML
                self.wfile.write(body.encode('utf-8'))
            def log_message(self, *args): pass
        server = ThreadingHTTPServer(('127.0.0.1',0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        base = 'http://127.0.0.1:' + str(server.server_port)
        with tempfile.TemporaryDirectory(dir=APP_ROOT) as directory:
            root = Path(directory); inputs = root/'input'; inputs.mkdir()
            for index, (college, page, target) in enumerate([
                    ('正确学院','staff','/person/a'), ('差异学院','wrong','/person/other'),
                    ('待核学院','pending','/person/original')]):
                paired_file(inputs/(str(index)+'.xlsx'), '本地大学', college, [base+'/'+page+'.html'], [base+target])
            config = root/'plans.json'; config.write_text('{"plans":{}}',encoding='utf-8')
            args = SimpleNamespace(input=inputs, output=root/'output', plans=config, no_browser=False,
                                   replay=None, mode='deepseek', cache_dir=root/'cache')
            client = Client()
            try:
                with patch.dict(os.environ, {'NO_PROXY':'127.0.0.1,localhost'}), \
                        patch('api_engine.DeepSeekJSON', return_value=client):
                    out, results, manifest = asyncio.run(run(args))
                by_college = {r['college']:r for r in results}
                for college in ('正确学院','差异学院'):
                    self.assertTrue(by_college[college]['complete'], by_college[college]['reason'])
                    self.assertEqual(by_college[college]['corrected_urls'], [base+'/person/a'])
                self.assertEqual((by_college['差异学院']['stats']['missing'],
                                  by_college['差异学院']['stats']['extra']), (1,1))
                pending = by_college['待核学院']
                self.assertTrue(pending['needs_human'])
                self.assertEqual(pending['corrected_urls'], [])
                self.assertEqual(pending['diffs'][0]['action'], '未判定，原样保留')
                self.assertIn('标记为隐藏', pending['reason'])
                summary = load_workbook(out/manifest['summary_filename'], read_only=True)
                rows = list(summary.active.values); summary.close()
                self.assertEqual({r[1]:r[2] for r in rows[1:]},
                                 {'正确学院':'正确','差异学院':'错误','待核学院':'特殊情况'})
                details = load_workbook(out/manifest['report_filename'], read_only=True)
                self.assertEqual(list(details['核验汇总'].values), rows); details.close()
                self.assertEqual(json.loads((out/'results.json').read_text('utf-8')), results)
                imported = subprocess.run([sys.executable, '-I', '-c',
                    'import sys; sys.path.insert(0,sys.argv[1]); import api_engine; print(api_engine.__file__)',
                    str(out/'code')], cwd=out/'code', capture_output=True, text=True, timeout=30)
                self.assertEqual(imported.returncode, 0, imported.stderr)
                self.assertEqual(Path(imported.stdout.strip()), out/'code'/'api_engine.py')
                saved = out/'code'/'client_pagination.py'
                self.assertEqual(saved.read_bytes(), Path(__file__).with_name('client_pagination.py').read_bytes())
                self.assertEqual(manifest['code_sha256']['client_pagination.py'], hashlib.sha256(saved.read_bytes()).hexdigest())
                self.assertTrue(all(p in {'/staff.html','/wrong.html','/pending.html'} for p in requests), requests)
            finally:
                if os.environ.get('CLIENT_PAGING_EVIDENCE'):
                    destination = Path(os.environ['CLIENT_PAGING_EVIDENCE'])/self._testMethodName
                    destination.mkdir(parents=True,exist_ok=True)
                    shutil.copytree(root,destination/str(len(list(destination.iterdir()))+1))
                server.shutdown(); server.server_close(); thread.join()

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
        inputs = ['/squ_wxy/contents/4021/'+name+'.html' for name in
                  ('12926','12927','14536','13209','13210','14931','15036')]
        source, result, requests, _ = self.read(html, selector='.page-layout',inputs=inputs)
        self.assertTrue(result['complete'], result['reason'])
        self.assertEqual((result['stats']['matched'],result['stats']['missing'],result['stats']['extra']),(7,0,0))
        proof = source['parsed']['client_pagination']
        self.assertEqual([len(p['entries']) for p in proof['pages']], [16,2])
        self.assertEqual(proof['entry_count'],18)
        self.assertEqual({u.split('/contents/')[-1] for u in result['corrected_urls']},
                         {'4021/12926.html','4021/12927.html','4021/14536.html','4021/13209.html',
                          '4021/13210.html','4021/14931.html','4021/15036.html'})
        self.assertEqual(sum(not e['urls'] for p in proof['pages'] for e in p['entries']),11)
        self.assertTrue(all(p == '/staff.html' for p in requests), requests)
        self.assertEqual(source['attempts'][-1]['method'],'HTTP')
        self.assertEqual(proof['selected_html_sha256'],source['attempts'][-1]['html_sha256'])

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

    def test_equal_input_count_with_different_url_still_reports_missing_and_extra(self):
        _, result, _, _ = self.read(inputs=['https://example.edu.cn/unrelated'])
        self.assertTrue(result['complete'], result['reason'])
        self.assertEqual((result['stats']['missing'],result['stats']['extra']),(1,1))
        self.assertEqual(len(result['corrected_urls']),1)

    def test_equal_page_entry_count_with_replaced_url_is_not_certified(self):
        html = HTML.replace('<div class="card">丙</div>', '<a class="card" href="/person/b">丙</a>')
        html = html.replace("map(x=>x.outerHTML)", "map(x=>n===2?x.outerHTML.replace('/person/b','/person/c'):x.outerHTML)")
        _, result, _, _ = self.read(html)
        self.assertTrue(result['needs_human'], result['reason'])
        self.assertIn('条目多重集不一致', result['reason'])

    def test_unresolved_next_added_on_initial_render_preserves_pending_paging(self):
        html = HTML.replace(';render(1);', ';render(1);document.body.insertAdjacentHTML(\'beforeend\',\'<div class="wp_paging"><a href="javascript:unknown()">下页</a></div>\');')
        source, result, requests, evidence = self.read(html)
        self.assertTrue(result['needs_human'], result['reason'])
        self.assertFalse(result['complete'])
        self.assertIn('下一页依赖脚本', result['reason'])
        self.assertEqual(result['corrected_urls'], [])
        self.assertEqual(result['diffs'][0]['action'], '未判定，原样保留')
        proof = source['parsed']['client_pagination']
        self.assertFalse(proof['complete'])
        self.assertIsNone(BeautifulSoup(evidence[source['attempts'][-1]['html_path']], 'lxml').select_one('.wp_paging'))
        self.assertIsNotNone(BeautifulSoup(evidence[proof['initial']['html_path']], 'lxml').select_one('.wp_paging'))
        self.assertTrue(all(p == '/staff.html' for p in requests), requests)

    def test_unresolved_next_added_after_client_click_preserves_pending_paging(self):
        html = HTML.replace('history.replaceState', 'if(n===2)document.body.insertAdjacentHTML(\'beforeend\',\'<div class="wp_paging"><a href="javascript:unknown()">下页</a></div>\');history.replaceState')
        source, result, requests, evidence = self.read(html)
        self.assertTrue(result['needs_human'], result['reason'])
        self.assertFalse(result['complete'])
        self.assertIn('下一页依赖脚本', result['reason'])
        self.assertEqual(result['corrected_urls'], [])
        self.assertEqual(result['diffs'][0]['action'], '未判定，原样保留')
        proof = source['parsed']['client_pagination']
        self.assertFalse(proof['complete'])
        for path in (source['attempts'][-1]['html_path'], proof['initial']['html_path']):
            self.assertIsNone(BeautifulSoup(evidence[path], 'lxml').select_one('.wp_paging'))
        self.assertEqual([p['page'] for p in proof['pages']], [1,2])
        self.assertIsNotNone(BeautifulSoup(evidence[proof['pages'][-1]['html_path']], 'lxml').select_one('.wp_paging'))
        self.assertTrue(all(p == '/staff.html' for p in requests), requests)

    def test_unwrapped_unresolved_next_stays_pending_on_initial_render_and_after_click(self):
        variants = [('unknown', '<a href="javascript:unknown()">下页</a>'),
                    ('empty', '<a href="">下页</a>'),
                    ('event', '<a href="/unread.html" onclick="unknown()">下页</a>')]
        for timing in ('initial', 'click'):
            for kind, anchor in variants:
                with self.subTest(timing=timing, kind=kind):
                    insert = "document.body.insertAdjacentHTML('beforeend'," + json.dumps(anchor) + ');'
                    html = (HTML.replace(';render(1);', ';render(1);'+insert) if timing == 'initial' else
                            HTML.replace('history.replaceState', 'if(n===2){'+insert+'}history.replaceState'))
                    source, result, requests, evidence = self.read(html)
                    self.assertTrue(result['needs_human'], result['reason'])
                    self.assertFalse(result['complete'])
                    self.assertIn('下一页依赖脚本', result['reason'])
                    self.assertEqual(result['corrected_urls'], [])
                    self.assertEqual(result['diffs'][0]['action'], '未判定，原样保留')
                    proof = source['parsed']['client_pagination']
                    self.assertFalse(proof['complete'])
                    self.assertIsNone(BeautifulSoup(evidence[source['attempts'][-1]['html_path']], 'lxml').select_one('body > a'))
                    self.assertEqual([p['page'] for p in proof['pages']], [1] if timing == 'initial' else [1,2])
                    self.assertIsNotNone(BeautifulSoup(evidence[proof['pages'][-1]['html_path']], 'lxml').select_one('body > a'))
                    self.assertTrue(all(p == '/staff.html' for p in requests), requests)

    def test_unwrapped_hash_next_stays_pending_on_initial_render_and_after_click(self):
        for timing in ('initial', 'click'):
            for href in ('#', '  #  '):
                with self.subTest(timing=timing, href=href):
                    anchor = '<a href="'+href+'">下页</a>'
                    insert = "document.body.insertAdjacentHTML('beforeend'," + json.dumps(anchor) + ');'
                    html = (HTML.replace(';render(1);', ';render(1);'+insert) if timing == 'initial' else
                            HTML.replace('history.replaceState', 'if(n===2){'+insert+'}history.replaceState'))
                    source, result, requests, evidence = self.read(html)
                    self.assertTrue(result['needs_human'], result['reason'])
                    self.assertFalse(result['complete'])
                    self.assertIn('下一页依赖脚本', result['reason'])
                    self.assertEqual(result['corrected_urls'], [])
                    self.assertEqual(result['diffs'][0]['action'], '未判定，原样保留')
                    proof = source['parsed']['client_pagination']
                    self.assertFalse(proof['complete'])
                    self.assertEqual([p['page'] for p in proof['pages']], [1] if timing == 'initial' else [1,2])
                    self.assertIsNone(BeautifulSoup(evidence[source['attempts'][-1]['html_path']], 'lxml').select_one('body > a'))
                    rendered = BeautifulSoup(evidence[proof['pages'][-1]['html_path']], 'lxml').select_one('body > a')
                    self.assertEqual(rendered['href'].strip(), '#')
                    self.assertTrue(all(p == '/staff.html' for p in requests), requests)

    def test_unwrapped_http_and_nonempty_fragment_next_text_remain_ordinary_links(self):
        for href in ('/person/a', '#details'):
            with self.subTest(href=href):
                anchor = '<a href="'+href+'">下页</a>'
                insert = "document.body.insertAdjacentHTML('beforeend'," + json.dumps(anchor) + ');'
                source, result, requests, _ = self.read(HTML.replace(';render(1);', ';render(1);'+insert))
                self.assertTrue(result['complete'], result['reason'])
                self.assertFalse(result['needs_human'])
                self.assertTrue(source['parsed']['client_pagination']['complete'])
                self.assertEqual(result['corrected_urls'], [source['roster_url'].replace('/staff.html','/person/a')])
                self.assertTrue(all(p == '/staff.html' for p in requests), requests)

    def test_unwrapped_plain_http_next_text_does_not_block_client_proof(self):
        html = HTML.replace(';render(1);', ';render(1);document.body.insertAdjacentHTML(\'beforeend\',\'<a href="/person/a">下页</a>\');')
        source, result, requests, _ = self.read(html)
        self.assertTrue(result['complete'], result['reason'])
        self.assertFalse(result['needs_human'])
        self.assertTrue(source['parsed']['client_pagination']['complete'])
        self.assertEqual(len(result['corrected_urls']), 1)
        self.assertTrue(all(p == '/staff.html' for p in requests), requests)

    def test_new_independent_http_next_is_not_covered_by_client_pager(self):
        html = HTML.replace(';render(1);', ';render(1);document.body.insertAdjacentHTML(\'beforeend\',\'<div class="wp_paging"><a href="/unread.html">下一页</a></div>\');')
        source, result, requests, _ = self.read(html)
        self.assertTrue(result['needs_human'], result['reason'])
        self.assertFalse(result['complete'])
        self.assertEqual(result['corrected_urls'], [])
        self.assertEqual(result['diffs'][0]['action'], '未判定，原样保留')
        self.assertFalse(source['parsed']['client_pagination']['complete'])
        self.assertTrue(all(p == '/staff.html' for p in requests), requests)

    def test_roster_entry_named_next_and_disabled_other_pager_do_not_block_proof(self):
        for html, pending in ((HTML.replace('>甲<', '>下一页<'), True),
                     (HTML.replace(';render(1);', ';render(1);document.body.insertAdjacentHTML(\'beforeend\',\'<div class="wp_paging"><a aria-disabled="true" href="/unread.html">下一页</a></div>\');'), False)):
            with self.subTest(pending=pending):
                source, result, requests, _ = self.read(html)
                self.assertTrue(source['parsed']['client_pagination']['complete'], result['reason'])
                self.assertEqual(result['needs_human'], pending)
                if pending:
                    self.assertIn('存在未被识别为分页区域的翻页入口', result['reason'])
                else:
                    self.assertTrue(result['complete'], result['reason'])
                    self.assertEqual(len(result['corrected_urls']), 1)
                self.assertTrue(all(p == '/staff.html' for p in requests), requests)

    def test_second_unresolved_pager_cannot_be_cleared_by_first_pager_evidence(self):
        html = HTML.replace('</body>', '<div class="wp_paging"><a href="javascript:;">下页</a></div></body>')
        source, result, _, _ = self.read(html)
        self.assertTrue(result['needs_human'])
        self.assertIn('下一页依赖脚本',result['reason'])
        self.assertFalse(source['parsed']['client_pagination']['complete'])

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
