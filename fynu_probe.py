"""Save the supplied college homepage and its explicitly linked faculty branches."""
import asyncio
import argparse
import hashlib
from datetime import timedelta, datetime, timezone
from urllib.parse import urljoin

from benchmark import new_run, write_json
from crawlee import ConcurrencySettings, service_locator
from crawlee.configuration import Configuration
from crawlee.crawlers import BeautifulSoupCrawler
from crawlee.events import LocalEventManager
from crawlee.request_loaders import ThrottlingRequestManager
from crawlee.storage_clients import FileSystemStorageClient
from crawlee.storages import RequestQueue
from compatible_http import CompatibleHttpClient

ENTRY = 'https://www.fynu.edu.cn/hxycl/'


async def make_crawler(out, max_requests, *, domains=None, handler_seconds=45):
    config = Configuration(storage_dir=str(out / 'storage'), purge_on_start=False)
    storage = FileSystemStorageClient()
    events = LocalEventManager()
    service_locator.set_configuration(config)
    service_locator.set_storage_client(storage)
    service_locator.set_event_manager(events)
    queue = await RequestQueue.open(configuration=config, storage_client=storage)
    throttled = ThrottlingRequestManager(inner=queue, domains=domains or ['www.fynu.edu.cn'],
                                        request_manager_opener=RequestQueue.open)
    return BeautifulSoupCrawler(
        http_client=CompatibleHttpClient(),
        request_manager=throttled, configuration=config, storage_client=storage, event_manager=events,
        concurrency_settings=ConcurrencySettings(min_concurrency=1, desired_concurrency=1, max_concurrency=1),
        max_request_retries=1, max_session_rotations=0, retry_on_blocked=False, use_session_pool=False,
        respect_robots_txt_file=True, max_requests_per_crawl=max_requests,
        request_handler_timeout=timedelta(seconds=handler_seconds),
    )


async def save_page(context, out, *, capture_body=True):
    url = context.request.url
    loaded = str(context.request.loaded_url or url)
    raw = await context.http_response.read()
    key = hashlib.sha256(url.encode()).hexdigest()[:16]
    folder = out / key
    folder.mkdir(exist_ok=True)
    (folder / 'source.html').write_bytes(raw)
    (folder / 'page-text.txt').write_text(context.soup.get_text('\n', strip=True), encoding='utf-8')
    links = [{'text': a.get_text(' ', strip=True), 'url': urljoin(loaded, a['href'])}
             for a in context.soup.select('a[href]')]
    write_json(folder / 'links.json', links)
    row = {'url': url, 'loaded_url': loaded, 'directory': key, 'bytes': len(raw),
           'sha256': hashlib.sha256(raw).hexdigest(), 'status': context.http_response.status_code,
           'title': context.soup.title.get_text(strip=True) if context.soup.title else '',
           'retrieved_at': datetime.now(timezone(timedelta(hours=8))).isoformat(), 'links': links}
    body = context.soup.select_one('.v_news_content') if capture_body else None
    if body:
        (folder / 'body.html').write_text(str(body), encoding='utf-8')
        (folder / 'body-text.txt').write_text(body.get_text('\n', strip=True), encoding='utf-8')
        row['body_chars'] = len(body.get_text('\n', strip=True))
    write_json(folder / 'metadata.json', row)
    return row


async def main(urls=None):
    out = new_run('fynu-discovery')
    print(f'RUN_DIR={out}', flush=True)
    crawler = await make_crawler(out, 8)
    pages, failures, skipped = [], [], []

    @crawler.pre_navigation_hook
    async def pace(context):
        await asyncio.sleep(2)

    @crawler.router.default_handler
    async def handle(context):
        item = await save_page(context, out)
        pages.append(item)
        write_json(out / 'pages.json', pages)
        if context.request.url == ENTRY:
            selected = [link for link in item['links'] if link['text'] in
                        {'教授团队','硕士生导师','博士团队','教师队伍','学院概况'}]
            write_json(out / 'entry-links.json', selected)
            await crawler.add_requests(list(dict.fromkeys(link['url'] for link in selected)))
        print(item['title'], item['url'], item['bytes'], flush=True)

    @crawler.failed_request_handler
    async def failure(context, error):
        failures.append({'url': context.request.url,'error': str(error)})
        write_json(out / 'failures.json', failures)

    @crawler.on_skipped_request
    async def skip(url, reason):
        skipped.append({'url': str(url),'reason': str(reason)})
        write_json(out / 'skipped.json', skipped)

    await crawler.run(urls or [ENTRY])
    write_json(out / 'summary.json', {'pages':len(pages), 'failures':failures,'skipped':skipped})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('urls', nargs='*')
    asyncio.run(main(parser.parse_args().urls))
