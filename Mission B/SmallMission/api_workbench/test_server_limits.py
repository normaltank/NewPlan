"""Server limits exercised through input parsing and the complete audit run."""
import asyncio
import json
import os
from pathlib import Path
import shutil
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from input_adapter import parse_file, read_directory


def preserve_run(out, name):
    if os.environ.get('SERVER_LIMITS_EVIDENCE'):
        parent = Path(os.environ['SERVER_LIMITS_EVIDENCE'])/name
        parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(out, parent/str(len(list(parent.iterdir()))+1))


class ServerInputTests(unittest.TestCase):
    def test_server_input_keeps_tail_beyond_old_row_limit(self):
        from run_limits import RunLimits
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'large.tsv'
            path.write_text('学校\t学院\t师资URL\t教师URL\n' + ''.join(
                f'示例大学\t示例学院\thttps://example.edu/list\thttps://example.edu/person/{i}\n'
                for i in range(50001)), encoding='utf-8')
            rows, files, errors, _ = read_directory(path.parent, limits=RunLimits())
            self.assertEqual(errors, [])
            self.assertEqual(len(rows), 50001)
            self.assertEqual(rows[-1]['url'], 'https://example.edu/person/50000')

    def test_oversized_and_cumulative_rows_reject_whole_files_then_continue(self):
        from run_limits import RunLimits
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'a-large.tsv').write_text('x'*501, encoding='utf-8')
            row = '示例大学\t示例学院\thttps://example.edu/list\thttps://example.edu/person/1\n'
            (root/'b-rows.tsv').write_text(row*3, encoding='utf-8')
            (root/'c-good.tsv').write_text(row, encoding='utf-8')
            rows, files, errors, _ = read_directory(root, limits=RunLimits(input_file_bytes=500, data_rows_per_batch=2))
            self.assertEqual(errors, [])
            self.assertEqual([r['file'] for r in rows], ['c-good.tsv'])
            self.assertEqual([f['status'] for f in files], ['rejected', 'rejected', 'accepted'])
            self.assertTrue(all(f.get('reason') for f in files[:2]))

    def test_all_file_and_workbook_limits_refuse_whole_input_without_losing_later_files(self):
        from openpyxl import Workbook
        from run_limits import RunLimits
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            book = Workbook()
            book.active.append(['学校', '学院', '师资URL', '教师URL'])
            book.active.append(['示例大学', '示例学院', 'https://example.edu/list', 'https://example.edu/a'])
            book.active.merge_cells('A3:B4')
            book.active.merge_cells('C3:D4')
            path = root/'a.xlsx'
            book.save(path)
            for limits, reason in [(RunLimits(sheet_cells=10), '范围'),
                                   (RunLimits(merged_cells=6), '合并'),
                                   (RunLimits(xlsx_expanded_bytes=20), '解压')]:
                with self.subTest(reason=reason):
                    rows, issues, _ = parse_file(path, limits=limits)
                    self.assertEqual(rows, [])
                    self.assertIn(reason, '；'.join(issues))
            path.unlink()
            row = '示例大学\t示例学院\thttps://example.edu/list\thttps://example.edu/a\n'
            for i in range(22):
                (root/f'{i:02}.tsv').write_text(row, encoding='utf-8')
            rows, files, errors, _ = read_directory(root, limits=RunLimits())
            self.assertEqual((len(rows), len(files), errors), (22, 22, []))
            rows, files, errors, _ = read_directory(root, limits=RunLimits(files_per_batch=2))
            self.assertEqual(len(rows), 2)
            self.assertEqual(sum(f['status'] == 'rejected' for f in files), 20)
            self.assertTrue(all(f['sha256'] is None for f in files[2:]))

    def test_cumulative_row_limit_does_not_take_prefix_of_a_file(self):
        from run_limits import RunLimits
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            row = '示例大学\t示例学院\thttps://example.edu/list\thttps://example.edu/a\n'
            for name, count in [('a.tsv', 1), ('b.tsv', 2), ('c.tsv', 1)]:
                (root/name).write_text(row*count, encoding='utf-8')
            rows, files, _, _ = read_directory(root, limits=RunLimits(data_rows_per_batch=2))
            self.assertEqual([r['file'] for r in rows], ['a.tsv', 'c.tsv'])
            self.assertEqual([f['status'] for f in files], ['accepted', 'rejected', 'accepted'])

    def test_server_accepts_over_old_file_and_merged_cell_ceilings(self):
        from openpyxl import Workbook
        from run_limits import RunLimits
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root/'large.csv'
            path.write_text('school-'+'x'*(10*1024*1024)+',示例学院,https://example.edu/list,https://example.edu/tail\n', encoding='utf-8')
            rows, errors, _ = parse_file(path, limits=RunLimits())
            self.assertEqual(errors, [])
            self.assertEqual([r['url'] for r in rows], ['https://example.edu/tail'])
            book = Workbook()
            book.active.append(['学校', '学院', '师资URL', '教师URL'])
            book.active.append(['示例大学', '示例学院', 'https://example.edu/list', 'https://example.edu/tail'])
            book.active.merge_cells('A3:B25003')
            path = root/'merged.xlsx'
            book.save(path)
            rows, errors, _ = parse_file(path, limits=RunLimits())
            self.assertEqual(errors, [])
            self.assertEqual([r['url'] for r in rows], ['https://example.edu/tail'])

    def test_configuration_rejects_unbounded_or_misspelled_values(self):
        from run_limits import RunLimits
        for value in (0, -1, True, 1.5, float('inf'), float('nan'), None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                RunLimits.load({'client_pages': value})
        with self.assertRaises(ValueError):
            RunLimits.load({'client_page': 1000})


class ServerRunTests(unittest.IsolatedAsyncioTestCase):
    async def run_model(self, limits, htmls, finish_reason='stop', cache_dir=None):
        import httpx
        from bs4 import BeautifulSoup
        from audit import ROOT, run
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            root = Path(temp)
            inputs = root/'inputs'
            inputs.mkdir()
            (inputs/'rows.tsv').write_text(''.join(f'示例大学\t院{i}\t{url}\thttps://example.edu/tail\n'
                for i, url in enumerate(htmls)), encoding='utf-8')
            plans = root/'plans.json'
            plans.write_text('{"plans": {}}', encoding='utf-8')
            requests = []
            def respond(request):
                if request.url.path == '/chat/completions':
                    body = json.loads(request.content)
                    requests.append(body)
                    payload = json.loads(body['messages'][1]['content'])
                    soup = BeautifulSoup(payload['html'], 'lxml')
                    answer = {'status': 'ready', 'roster_regions': [int(soup.select_one('.roster')['data-mb-id'])],
                              'pagination_regions': [], 'exclude_regions': [], 'reason': '完整名单'}
                    return httpx.Response(200, json={'model': 'test', 'choices': [{'finish_reason': finish_reason,
                        'message': {'content': json.dumps(answer)}}]})
                return httpx.Response(200, text=htmls[str(request.url)])
            original = httpx.AsyncClient
            def client(**kwargs):
                return original(transport=httpx.MockTransport(respond), **kwargs)
            args = SimpleNamespace(input=inputs, output=root/'out', plans=plans, no_browser=True,
                                   replay=None, mode='deepseek', api_key='local-test-key', cache_dir=cache_dir or root/'cache', limits=limits)
            original_sleep = asyncio.sleep
            with patch('httpx.AsyncClient', side_effect=client), patch('asyncio.sleep', new=lambda _: original_sleep(0)):
                out, results, manifest = await run(args)
            preserve_run(out, self._testMethodName)
            return results, manifest, requests

    async def test_model_consumes_complete_large_input_with_configured_output_budget(self):
        from run_limits import RunLimits
        html = '<div>' + '名单背景'*60000 + '</div><div class="roster"><a href="/tail">末尾条目</a></div>'
        results, manifest, requests = await self.run_model(RunLimits(), {'https://example.edu/list': html})
        self.assertTrue(results[0]['complete'], results[0]['reason'])
        self.assertEqual(results[0]['corrected_urls'], ['https://example.edu/tail'])
        self.assertEqual(len(requests), 2)
        self.assertTrue(all(r['max_tokens'] == 8192 and '/tail' in r['messages'][1]['content'] for r in requests))
        self.assertEqual(manifest['api']['limits']['model_input_chars'], 1000000)

    async def test_large_observed_page_number_is_evidence_not_a_hidden_numeric_ceiling(self):
        from run_limits import RunLimits
        html = '<div class="roster"><a href="/tail">末尾</a><div class="pb_sys_common">10001/10001<a href="?page=10002">后一页</a></div></div>'
        results, _, requests = await self.run_model(RunLimits(source_pages_per_college=20000),
            {'https://example.edu/list?page=10001': html})
        self.assertEqual(len(results[0]['sources']), 1)
        self.assertIn('缺少页码', results[0]['reason'])
        self.assertEqual(len(requests), 2)

    async def test_model_budget_never_starts_one_half_of_a_pair_and_continues_colleges(self):
        from run_limits import RunLimits
        html = '<div class="roster"><a href="/tail">完整条目</a></div>'
        results, manifest, requests = await self.run_model(RunLimits(api_calls_per_batch=3),
            {f'https://example.edu/list/{i}.htm': html for i in range(3)})
        self.assertEqual([r['complete'] for r in results], [True, False, False])
        self.assertEqual(len(requests), 2)
        self.assertEqual([e['kind'] for e in manifest['limit_events']], ['api_calls_per_batch']*2)


    async def run_pages(self, source_count, limit, pagination=False):
        import httpx
        from audit import ROOT, run
        from run_limits import RunLimits
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            root = Path(temp)
            inputs = root/'inputs'
            inputs.mkdir()
            entries = [f'示例大学\t大院\thttps://example.edu/list/{i}.htm\thttps://example.edu/p/{i}\n'
                       for i in range(source_count)]
            entries.append('示例大学\t后院\thttps://example.edu/good.htm\thttps://example.edu/good-person\n')
            (inputs/'rows.tsv').write_text(''.join(entries), encoding='utf-8')
            if limit is None:
                from test_multisource import paired_file
                (inputs/'rows.tsv').unlink()
                paired_file(inputs/'a.xlsx', '示例大学', '大院',
                    [f'https://example.edu/list/{i}.htm' for i in range(source_count)],
                    [f'https://example.edu/p/{i}' for i in range(source_count)])
                paired_file(inputs/'b.xlsx', '示例大学', '后院',
                    ['https://example.edu/good.htm'], ['https://example.edu/good-person'])
            plans = root/'plans.json'
            plans.write_text(json.dumps({'plans': {url: {'selector': '.roster'} for url in [f'https://example.edu/list/{i}.htm' for i in range(source_count)] + ['https://example.edu/good.htm']}}), encoding='utf-8')
            calls = []
            def respond(request):
                calls.append(str(request.url))
                name = request.url.path.rsplit('/', 1)[-1].split('.')[0]
                target = '/good-person' if name == 'good' else '/p/'+name
                pages = pagination if type(pagination) is int else 2
                paging = ('<div class="pb_sys_common"><a href="/list/'+str(int(name)+1)+'.htm">下一页</a></div>'
                          if pagination and name.isdigit() and int(name)+1 < pages else '')
                return httpx.Response(200, text='<div class="roster"><a href="'+target+'">甲</a>'+paging+'</div>')
            original = httpx.AsyncClient
            def client(**kwargs):
                return original(transport=httpx.MockTransport(respond), **kwargs)
            args = SimpleNamespace(input=inputs, output=root/'out', plans=plans, no_browser=True,
                                   replay=None, mode='rules', limits=RunLimits(source_pages_per_college=limit) if limit is not None else None)
            original_sleep = asyncio.sleep
            with patch('audit.httpx.AsyncClient', side_effect=client), patch('audit.asyncio.sleep', new=lambda _: original_sleep(0)):
                # Disable pacing at the external time boundary, retaining real parsing and reconciliation.
                out, results, manifest = await run(args)
            preserve_run(out, self._testMethodName)
            return results, manifest, calls

    async def test_initial_source_page_budget_is_per_college_and_other_college_continues(self):
        from reporting import college_summaries
        results, manifest, calls = await self.run_pages(3, 2)
        summaries = college_summaries(results)
        self.assertEqual([r['verification_result'] for r in summaries], ['特殊情况', '正确'])
        self.assertEqual(calls, ['https://example.edu/good.htm'])
        self.assertEqual(len(manifest['limit_events'][0]['unprocessed_urls']), 3)

    async def test_discovered_page_limit_preserves_input_and_next_college(self):
        results, manifest, calls = await self.run_pages(1, 1, pagination=True)
        self.assertEqual([r['complete'] for r in results], [False, True])
        self.assertEqual(results[0]['diffs'][0]['action'], '未判定，原样保留')
        self.assertEqual(manifest['limit_events'][0]['unprocessed_urls'], ['https://example.edu/list/1.htm'])
        self.assertNotIn('https://example.edu/list/1.htm', calls)

    async def test_201_discovered_pages_keep_last_url_past_old_queue_limit(self):
        results, manifest, calls = await self.run_pages(1, 1000, pagination=201)
        self.assertEqual([r['complete'] for r in results], [True, True])
        self.assertEqual(len(results[0]['roster_urls']), 201)
        self.assertIn('https://example.edu/p/200', results[0]['corrected_urls'])
        self.assertEqual(len(calls), 202)
        self.assertEqual(manifest['limit_events'], [])

    async def test_desktop_retains_existing_initial_source_scope_without_server_profile(self):
        results, manifest, calls = await self.run_pages(201, None)
        self.assertEqual([r['complete'] for r in results], [True, True])
        self.assertEqual(len(calls), 202)
        self.assertEqual(manifest['limit_profile'], 'desktop')

    async def test_cache_reuse_requires_the_same_effective_limits(self):
        from run_limits import RunLimits
        htmls = {'https://example.edu/list': '<div class="roster"><a href="/tail">末尾</a></div>'}
        with tempfile.TemporaryDirectory() as temp:
            cache = Path(temp)/'cache'
            _, first, first_calls = await self.run_model(RunLimits(), htmls, cache_dir=cache)
            _, same, same_calls = await self.run_model(RunLimits(), htmls, cache_dir=cache)
            _, changed, changed_calls = await self.run_model(RunLimits(model_output_tokens=9000), htmls, cache_dir=cache)
        self.assertEqual((len(first_calls), len(same_calls), len(changed_calls)), (2, 0, 2))
        self.assertEqual(first['api']['contract'], same['api']['contract'])
        self.assertNotEqual(first['api']['contract'], changed['api']['contract'])

    async def test_model_character_limit_records_full_scope_without_partial_calls(self):
        from run_limits import RunLimits
        html = '<div class="roster"><a href="/tail">末尾</a></div>'
        results, manifest, requests = await self.run_model(RunLimits(model_input_chars=100),
            {'https://example.edu/list': html, 'https://example.edu/list2': html})
        self.assertEqual([r['complete'] for r in results], [False, False])
        self.assertEqual(requests, [])
        self.assertTrue(all(e['kind'] == 'model_input_chars' and e['observed'] > 100 for e in manifest['limit_events']))

    async def test_token_truncation_cannot_pass_even_with_valid_json(self):
        from run_limits import RunLimits
        html = '<div class="roster"><a href="/tail">末尾</a></div>'
        results, manifest, requests = await self.run_model(RunLimits(model_output_tokens=123),
            {'https://example.edu/list': html}, finish_reason='length')
        self.assertFalse(results[0]['complete'])
        self.assertEqual(results[0]['corrected_urls'], [])
        self.assertEqual(manifest['limit_events'][0]['kind'], 'model_output_tokens')
        self.assertEqual(requests[0]['max_tokens'], 123)


    async def test_run_reports_unparsed_file_without_inventing_college_and_continues(self):
        import httpx
        from audit import ROOT, run
        from run_limits import RunLimits
        from reporting import college_summary_rows
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inputs = root/'inputs'
            inputs.mkdir()
            (inputs/'a-large.tsv').write_text('x'*501, encoding='utf-8')
            (inputs/'b-good.tsv').write_text('示例大学\t示例学院\thttps://example.edu/list\thttps://example.edu/a\n', encoding='utf-8')
            plans = root/'plans.json'
            plans.write_text(json.dumps({'plans': {'https://example.edu/list': {'selector': '.roster'}}}), encoding='utf-8')
            def respond(request):
                return httpx.Response(200, text='<div class="roster"><a href="/a">甲</a></div>')
            original = httpx.AsyncClient
            def client(**kwargs):
                return original(transport=httpx.MockTransport(respond), **kwargs)
            args = SimpleNamespace(input=inputs, output=root/'out', plans=plans, no_browser=True,
                                   replay=None, mode='rules', limits=RunLimits(input_file_bytes=500))
            with patch('audit.httpx.AsyncClient', side_effect=client):
                out, results, manifest = await run(args)
            self.assertEqual([r['complete'] for r in results], [False, True])
            self.assertEqual((results[0]['school'], results[0]['college']), ('', ''))
            self.assertEqual(results[0]['input_file'], 'a-large.tsv')
            self.assertIn('a-large.tsv', college_summary_rows(results)[0][3])
            self.assertEqual(manifest['limits']['input_file_bytes'], 500)
            self.assertTrue((out/'code'/'run_limits.py').exists())
            preserve_run(out, self._testMethodName)


class ServerClientTests(unittest.TestCase):
    def test_low_client_page_and_time_limits_preserve_pending_scope(self):
        from run_limits import RunLimits
        from test_client_pagination import ClientPaginationTests, HTML
        runner = ClientPaginationTests('test_complete_client_pages_preserve_links_and_plain_entries')
        for limits, kind in [(RunLimits(client_pages=1), 'client_pages'),
                             (RunLimits(client_observation_seconds=1), 'client_observation_seconds')]:
            with self.subTest(kind=kind):
                html = HTML if kind == 'client_pages' else HTML.replace('</body>', '<script>const until=performance.now()+1500;while(performance.now()<until){}</script></body>')
                source, result, _, _ = runner.read(html, limits=limits)
                self.assertFalse(result['complete'])
                self.assertEqual(result['corrected_urls'], [])
                self.assertEqual(source['parsed']['client_pagination']['limit_event']['kind'], kind)

    def test_real_client_can_observe_31_pages_and_retains_tail_url(self):
        from run_limits import RunLimits
        from test_client_pagination import ClientPaginationTests
        cards = ''.join(f'<a class="card" href="/person/{i}">条目{i}</a>' for i in range(31))
        html = '''<html><head><meta charset="utf-8"><link rel="icon" href="data:,"></head><body>
        <main class="roster"><div id="preload" style="display:none">''' + cards + '''</div>
        <div id="visible"><a class="card" href="/person/0">条目0</a></div></main>
        <div id="pager" class="pb_sys_common"><span class="p_no_d">1</span>
        <a data-page="2" href="javascript:;">下页</a><a data-page="31" href="javascript:;">尾页</a></div>
        <script>const cards=[...document.querySelector('#preload').children];
        function render(n){document.querySelector('#visible').innerHTML=cards[n-1].outerHTML;
        document.querySelector('#pager').innerHTML='<span class="p_no_d">'+n+'</span>'+(n===31?
        '<span class="p_next p_fun_d">下页</span><span class="p_last p_fun_d">尾页</span>':
        '<a data-page="'+(n+1)+'" href="javascript:;">下页</a><a data-page="31" href="javascript:;">尾页</a>');}
        document.querySelector('#pager').addEventListener('click',e=>{if(e.target.dataset.page)render(+e.target.dataset.page)});
        </script></body></html>'''
        runner = ClientPaginationTests('test_complete_client_pages_preserve_links_and_plain_entries')
        source, result, _, _ = runner.read(html, limits=RunLimits(), inputs=[f'/person/{i}' for i in range(31)])
        self.assertTrue(result['complete'], result['reason'])
        self.assertEqual(len(source['parsed']['client_pagination']['pages']), 31)
        self.assertTrue(any(url.endswith('/person/30') for url in result['corrected_urls']))


if __name__ == '__main__':
    unittest.main()
