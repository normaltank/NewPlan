"""Bounded OpenSource experiment, independent of MyPlan runtime and databases."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import threading
import time
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / 'fixtures' / 'legacy-replay'
os.environ['CRAWL4_AI_BASE_DIRECTORY'] = str(ROOT / '.cache')
os.environ['LITELLM_LOCAL_MODEL_COST_MAP'] = 'True'

import trafilatura
from bs4 import BeautifulSoup
from crawl4ai import JsonCssExtractionStrategy
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawlee import ConcurrencySettings
from crawlee.configuration import Configuration
from crawlee.crawlers import BeautifulSoupCrawler
from crawlee.storage_clients import FileSystemStorageClient


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def compact(text):
    return re.sub(r'\s+', '', text)


def new_run(mode):
    now = datetime.now(timezone(timedelta(hours=8)))
    out = ROOT / 'runs' / f'{now:%Y%m%d-%H%M%S-%f}-{uuid.uuid4().hex[:8]}-{mode}'
    out.mkdir(parents=True)
    write_json(out / 'environment.json', {
        'time': now.isoformat(), 'mode': mode,
        'versions': {name: importlib.metadata.version(name) for name in
                     ['trafilatura', 'crawl4ai', 'crawlee', 'beautifulsoup4']},
        'scope': 'Exploratory experiment; whole-college completeness unverified',
        'llm_calls': 0,
    })
    return out


def extract_variants(html, url=''):
    strategies = {
        'trafilatura-default': lambda: trafilatura.extract(
            html, url=url or None, include_comments=False, include_tables=True) or '',
        'trafilatura-recall': lambda: trafilatura.extract(
            html, url=url or None, include_comments=False, include_tables=True,
            favor_recall=True) or '',
        'crawl4ai-markdown': lambda: DefaultMarkdownGenerator().generate_markdown(
            html, base_url=url, citations=False).raw_markdown,
    }
    result = {}
    for name, fn in strategies.items():
        start = time.perf_counter()
        try:
            text = fn()
            result[name] = {'text': text, 'chars': len(text), 'error': None}
        except Exception as exc:
            result[name] = {'text': '', 'chars': 0, 'error': repr(exc)}
        result[name]['seconds'] = round(time.perf_counter() - start, 4)
    return result


def roster(html, url, selector):
    schema = {
        'name': 'Configured saved faculty cards', 'baseSelector': selector,
        'fields': [
            {'name': 'name', 'selector': 'a', 'type': 'text'},
            {'name': 'href', 'selector': 'a', 'type': 'attribute', 'attribute': 'href'},
        ],
    }
    rows = JsonCssExtractionStrategy(schema).extract(url, html)
    return [{'name': row.get('name', '').strip(),
             'profile_url': urljoin(url, row['href']) if row.get('href') else ''}
            for row in rows]


def crawler_for(out, live=False, max_requests=8):
    return BeautifulSoupCrawler(
        configuration=Configuration(storage_dir=str(out / 'storage'), purge_on_start=False),
        storage_client=FileSystemStorageClient(),
        concurrency_settings=ConcurrencySettings(min_concurrency=1, max_concurrency=1, desired_concurrency=1),
        max_request_retries=1, max_session_rotations=0, retry_on_blocked=False,
        use_session_pool=False, max_requests_per_crawl=max_requests,
        request_handler_timeout=timedelta(seconds=45),
        respect_robots_txt_file=live,
    )


async def replay_queue(out, html_bytes):
    counts = Counter()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            counts[self.path] += 1
            failing = self.path == '/always-fails' or (
                self.path == '/retry-once' and counts[self.path] == 1)
            self.send_response(503 if failing else 200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(b'<html><body>planned failure</body></html>' if failing else html_bytes)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    ok, failed = [], []
    crawler = crawler_for(out)

    @crawler.router.default_handler
    async def handle(context):
        row = {'url': context.request.url, 'title': context.soup.title.get_text() if context.soup.title else '',
               'retry_count': context.request.retry_count}
        ok.append(row)
        await context.push_data(row)

    @crawler.failed_request_handler
    async def failure(context, error):
        failed.append({'url': context.request.url, 'retry_count': context.request.retry_count,
                       'error': str(error)})

    try:
        await crawler.run([base + '/ok', base + '/ok', base + '/retry-once', base + '/always-fails'])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    result = {'success': ok, 'failed': failed, 'server_request_counts': dict(counts),
              'kind': 'Local HTTP transport; deliberately injected failures; not a live college run'}
    write_json(out / 'queue-result.json', result)
    return result


async def replay(out):
    manifest = []
    metrics = []
    for name, selector, start_selector in [
        ('nxmu-0', '.v_news_content', None), ('nxmu-1', '.v_news_content', None),
        ('cuc-1', '.wp_articlecontent', None), ('cuc-2', '.wp_articlecontent', None),
        ('stbu-1', '.content', 'hr'),
    ]:
        source = FIXTURES / 'profile_content_scope' / f'{name}.html'
        sample = out / name
        sample.mkdir()
        shutil.copyfile(source, sample / 'source.html')
        raw = source.read_bytes()
        html = raw.decode('utf-8')
        soup = BeautifulSoup(html, 'lxml')
        reference = soup.select_one(selector)
        if reference is None:
            raise ValueError(f'Missing reference scope: {name}')
        if start_selector:
            marker = reference.select_one(start_selector)
            reference = BeautifulSoup(''.join(str(n) for n in marker.next_siblings), 'lxml')
        units = [str(s).strip() for s in reference.stripped_strings if len(compact(str(s))) >= 8]
        (sample / 'reference-text.txt').write_text(reference.get_text('\n', strip=True), encoding='utf-8')
        manifest.append({'id': name, 'original': str(source), 'sha256': hashlib.sha256(raw).hexdigest(),
                         'selector': selector, 'start_selector': start_selector,
                         'reference': 'Existing regression DOM scope, NOT independently annotated full biography',
                         'original_url': None})
        for engine, result in extract_variants(html).items():
            (sample / f'{engine}.txt').write_text(result.pop('text'), encoding='utf-8')
            text = (sample / f'{engine}.txt').read_text(encoding='utf-8')
            missing = [unit for unit in units if compact(unit) not in compact(text)]
            row = {'sample': name, 'engine': engine, **result, 'reference_units': len(units),
                   'retained_units': len(units)-len(missing), 'missing_units': missing}
            metrics.append(row)
    truth_path = FIXTURES / 'harvest_acceptance/real_source.json'
    truth = json.loads(truth_path.read_text(encoding='utf-8'))
    source = FIXTURES / 'harvest_acceptance/real_hnucm_directory.html'
    raw = source.read_bytes()
    actual_sha = hashlib.sha256(raw).hexdigest()
    if actual_sha != truth['sha256']:
        raise ValueError('Roster reference SHA mismatch')
    rows = roster(raw.decode('utf-8'), truth['url'], truth['selector'])
    expected = {tuple(pair) for pair in truth['expected_identities']}
    actual = {(row['name'], row['profile_url']) for row in rows}
    roster_result = {'count': len(rows), 'expected_count': len(expected),
                     'missing': sorted(expected-actual), 'extra': sorted(actual-expected),
                     'duplicate_count': len(rows)-len(actual),
                     'reference_scope': truth['scope'], 'rows': rows,
                     'schema_origin': 'Existing fixture selector, manually supplied; no automatic discovery'}
    write_json(out / 'roster-result.json', roster_result)
    shutil.copyfile(source, out / 'roster-source.html')
    manifest.append({'id': 'hnucm-roster', 'original': str(source), 'sha256': actual_sha,
                     'original_url': truth['url'], 'reference_file': str(truth_path)})
    write_json(out / 'inputs.json', manifest)
    write_json(out / 'profile-metrics.json', metrics)
    queue = await replay_queue(out, raw)
    lines = ['# 首轮保存页回放', '',
             '范围：5份既有个人页原件、1份有60条参考身份的名单原件，以及本地HTTP失败注入。',
             '正文指标只检查既有DOM范围内长度≥8的文本节点是否完整出现在输出；不等于全文完整性、字段正确性或跨站泛化。',
             'Crawl4AI 此处测试 CSS 提取与 HTML→Markdown 模块；未测试浏览器、自动规则生成或模型提取。', '',
             '| 样本 | 方法 | 保留参考文本节点 | 输出字符 | 秒 |', '|---|---|---:|---:|---:|']
    for row in metrics:
        lines.append(f"| {row['sample']} | {row['engine']} | {row['retained_units']}/{row['reference_units']} | {row['chars']} | {row['seconds']} |")
    lines += ['', f"名单：{len(rows)}条；参考差集漏项{len(expected-actual)}，多项{len(actual-expected)}。选择器由既有样本提供。",
              f"队列：成功{len(queue['success'])}个唯一URL，耗尽重试后失败{len(queue['failed'])}个。请求次数：{dict(queue['server_request_counts'])}",
              '', '全院完整性未验证。原文、提取输出、逐项缺失和版本均保存在同一运行目录。']
    (out / 'report.md').write_text('\n'.join(lines), encoding='utf-8')


async def live(out):
    """One supplied official roster, at most its first 3 unique same-host profiles."""
    url = 'https://xxgc.hnucm.edu.cn/szdw.htm'
    selector = 'div.list-big-box div.list-box ul.list-name > li'
    successes, failures, records = [], [], []
    crawler = crawler_for(out, live=True)

    @crawler.router.default_handler
    async def handle(context):
        await asyncio.sleep(1.5)
        current = str(context.request.url)
        raw = await context.http_response.read()
        key = hashlib.sha256(current.encode()).hexdigest()[:16]
        sample = out / key
        sample.mkdir(exist_ok=True)
        (sample / 'source.html').write_bytes(raw)
        html = raw.decode('utf-8', errors='replace')
        item = {'url': current, 'loaded_url': str(context.request.loaded_url),
                'status': context.http_response.status_code,
                'sha256': hashlib.sha256(raw).hexdigest(), 'sample_directory': key,
                'title': context.soup.title.get_text(strip=True) if context.soup.title else '',
                'collected_at': datetime.now(timezone(timedelta(hours=8))).isoformat()}
        if current == url:
            records.extend(roster(html, current, selector))
            write_json(out / 'roster-observations.json', records)
            links = list(dict.fromkeys(r['profile_url'] for r in records
                                      if r['profile_url'].startswith('https://xxgc.hnucm.edu.cn/')))[:3]
            item['roster_rows'] = len(records)
            item['profile_sample_urls'] = links
            await crawler.add_requests(links)
        for engine, result in extract_variants(html, current).items():
            (sample / f'{engine}.txt').write_text(result['text'], encoding='utf-8')
            item[engine] = {k: v for k, v in result.items() if k != 'text'}
        successes.append(item)
        await context.push_data(item)

    @crawler.failed_request_handler
    async def failure(context, error):
        failures.append({'url': context.request.url, 'retry_count': context.request.retry_count,
                         'error': str(error)})

    await crawler.run([url])
    result = {'entry_url': url, 'successes': successes, 'failures': failures,
              'roster_observations': len(records), 'whole_college_completeness': 'unverified',
              'limitations': ['Supplied entry, no discovery', 'At most 3 profiles',
                              'No pagination', 'No identity, affiliation or field validation',
                              'HTTP only; no JavaScript execution', 'No independently verified live reference']}
    write_json(out / 'live-result.json', result)
    (out / 'report.md').write_text('\n'.join([
        '# 首轮有界真实访问', '', f'入口：{url}',
        f'已保存页面：{len(successes)}；失败记录：{len(failures)}；名单观察：{len(records)}。',
        '仅访问给定名单和前三个同站个人链接。原件和三种正文输出已保存。',
        '观察数不等于已确认教师数；未核验入口发现、分页、身份、字段归属及全院完整性。',
        '若出现零结果，须查看抓取/robots/结构问题，不能推断学院无师资。',
    ]), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['replay', 'live'])
    args = parser.parse_args()
    output = new_run(args.mode)
    print(f'RUN_DIR={output}', flush=True)
    asyncio.run(replay(output) if args.mode == 'replay' else live(output))
    print((output / 'report.md').read_text(encoding='utf-8'), flush=True)
