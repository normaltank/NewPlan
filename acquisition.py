"""Acquisition-first comparison: fixed real pages, HTTP vs rendered browser HTML."""
import asyncio
import argparse
import hashlib
import json
import time
import shutil
from pathlib import Path

from benchmark import ROOT, BeautifulSoup, crawler_for, new_run, write_json
from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

CASES = [
    {'id': 'hunan-professors-1', 'url': 'http://ls.hunnu.edu.cn/szdw/js.htm',
     'selector': '.dis-list a[href]', 'kind': 'Known paginated roster, first page'},
    {'id': 'hunan-professors-2', 'url': 'http://ls.hunnu.edu.cn/szdw/js/1.htm',
     'selector': '.dis-list a[href]', 'kind': 'Known paginated roster, second page'},
    {'id': 'qinghai-associate-professors', 'url': 'https://jsj.qhnu.edu.cn/szdw1/fjs.htm',
     'selector': None, 'kind': 'Historical discovery failure source, raw acquisition only'},
    {'id': 'sanming-professors', 'url': 'https://www.fjsmu.edu.cn/smxyszb/js/list.htm',
     'selector': 'span.Article_Title a[href]', 'kind': 'Historical discovery/pagination source'},
]


def save_page(out, engine, case, html, status, seconds, error=None, loaded_url=None):
    folder = out / engine / case['id']
    folder.mkdir(parents=True, exist_ok=True)
    raw = html.encode('utf-8') if isinstance(html, str) else html
    (folder / 'source.html').write_bytes(raw)
    soup = BeautifulSoup(raw, 'lxml')
    links = [{'text': a.get_text(' ', strip=True), 'href': a['href']}
             for a in soup.select('a[href]')]
    write_json(folder / 'links.json', links)
    (folder / 'page-text.txt').write_text(soup.get_text('\n', strip=True), encoding='utf-8')
    selected = [{'text': a.get_text(' ', strip=True), 'href': a['href']}
                for a in soup.select(case['selector'])] if case['selector'] else None
    row = {'engine': engine, **case, 'loaded_url': loaded_url,
           'http_status': status, 'bytes': len(raw),
           'sha256': hashlib.sha256(raw).hexdigest(),
           'title': soup.title.get_text(strip=True) if soup.title else '',
           'links': len(links), 'selected_observations': selected,
           'seconds': round(seconds, 3), 'error': error,
           'completeness': 'unverified'}
    write_json(folder / 'metadata.json', row)
    return row


async def main(reuse_http_run=None):
    out = new_run('acquisition')
    print(f'RUN_DIR={out}', flush=True)
    write_json(out / 'cases.json', CASES)
    rows = []
    by_url = {c['url']: c for c in CASES}
    http = crawler_for(out / 'crawlee-http', live=True)

    @http.router.default_handler
    async def handle(context):
        case = by_url[context.request.url]
        raw = await context.http_response.read()
        rows.append(save_page(out, 'crawlee-http', case, raw,
                              context.http_response.status_code, 0,
                              loaded_url=str(context.request.loaded_url)))
        await context.push_data(rows[-1])
        await asyncio.sleep(2)

    @http.failed_request_handler
    async def failure(context, error):
        rows.append(save_page(out, 'crawlee-http', by_url[context.request.url], b'', None, 0,
                              error=str(error)))

    if reuse_http_run:
        previous = Path(reuse_http_run)
        rows.extend(json.loads((previous / 'results.json').read_text(encoding='utf-8')))
        shutil.copytree(previous / 'crawlee-http', out / 'crawlee-http')
        write_json(out / 'http-provenance.json', {'reused_http_run': str(previous.resolve())})
        http_seconds = '复用已有访问，见http-provenance.json'
    else:
        started = time.perf_counter()
        await http.run([case['url'] for case in CASES])
        http_seconds = round(time.perf_counter()-started, 3)
    write_json(out / 'results.json', rows)
    config = BrowserConfig(channel='msedge', chrome_channel='msedge', headless=True, verbose=False,
                           ignore_https_errors=False, use_persistent_context=False)
    async with AsyncWebCrawler(config=config, base_directory=str(ROOT / '.cache')) as browser:
        for case in CASES:
            started = time.perf_counter()
            try:
                result = await asyncio.wait_for(browser.arun(
                    case['url'], config=CrawlerRunConfig(
                        cache_mode=CacheMode.BYPASS, page_timeout=30000,
                        wait_until='domcontentloaded', delay_before_return_html=2,
                        check_robots_txt=True, verbose=False,
                    )), timeout=45)
                row = save_page(out, 'crawl4ai-browser', case, result.html or '',
                                result.status_code, time.perf_counter()-started,
                                error=result.error_message if not result.success else None,
                                loaded_url=result.redirected_url or result.url)
                if result.markdown:
                    (out / 'crawl4ai-browser' / case['id'] / 'markdown.txt').write_text(
                        result.markdown.raw_markdown, encoding='utf-8')
            except Exception as exc:
                row = save_page(out, 'crawl4ai-browser', case, '', None,
                                time.perf_counter()-started, error=repr(exc))
            rows.append(row)
            write_json(out / 'results.json', rows)
            print(json.dumps({k: row[k] for k in ['id','engine','http_status','bytes','links','error']},
                             ensure_ascii=False), flush=True)
            await asyncio.sleep(2)
    report = ['# 获取原始数据对照', '',
              '固定4个已知页面：湖南师范大学教授名录的两个分页、青海师范大学副教授名录、三明学院教授名录。',
              'Crawlee 使用普通HTTP；Crawl4AI 使用本机Edge的独立无头实例，保存渲染后HTML。',
              '优先比较能否保存页面和链接；清理质量不作为获取失败。分页URL事先给定，本轮不声称自动发现或动态翻页完成。',
              f'HTTP整批耗时：{http_seconds}秒；单页HTTP耗时未单独计量。', '',
              '| 页面 | 工具 | 状态 | HTML字节 | 链接 | 指定选区观察数 |',
              '|---|---|---:|---:|---:|---:|']
    for row in rows:
        count = len(row['selected_observations']) if row['selected_observations'] is not None else '未配置'
        report.append(f"| {row['id']} | {row['engine']} | {row['http_status']} | {row['bytes']} | {row['links']} | {count} |")
    report += ['', '原始HTML、页面文本、全部链接和错误分别保留。200和非空HTML不单独证明人员数据齐全。',
               '历史失败发生在旧版本/运行，当前已知URL获取成功不证明历史整院失败已被解决。全院完整性未验证。']
    (out / 'report.md').write_text('\n'.join(report), encoding='utf-8')
    print((out / 'report.md').read_text(encoding='utf-8'), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--reuse-http-run')
    args = parser.parse_args()
    asyncio.run(main(args.reuse_http_run))
