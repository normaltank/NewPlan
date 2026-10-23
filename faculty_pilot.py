"""Follow the actual roster pager, retain every observation, capture linked profiles."""
import asyncio
import hashlib
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin, urlparse

from benchmark import crawler_for, extract_variants, new_run, roster, write_json

ENTRY = 'https://xxgc.hnucm.edu.cn/szdw.htm'
CARD_SELECTOR = 'div.list-big-box div.list-box ul.list-name > li'


async def main():
    out = new_run('faculty-pilot')
    print(f'RUN_DIR={out}', flush=True)
    crawler = crawler_for(out, live=True, max_requests=110)
    roster_urls = {ENTRY}
    profile_urls = set()
    observations, pages, failures, skipped = [], [], [], []
    caps = []

    def save_progress():
        write_json(out / 'observations.json', observations)
        write_json(out / 'pages.json', pages)
        write_json(out / 'failures.json', failures)

    @crawler.pre_navigation_hook
    async def pace(context):
        await asyncio.sleep(2)

    @crawler.router.default_handler
    async def handle(context):
        url = context.request.url
        loaded = str(context.request.loaded_url or url)
        raw = await context.http_response.read()
        key = hashlib.sha256(url.encode()).hexdigest()[:16]
        folder = out / key
        folder.mkdir(exist_ok=True)
        (folder / 'source.html').write_bytes(raw)
        html = raw.decode('utf-8', errors='replace')
        item = {'url': url, 'loaded_url': loaded, 'status': context.http_response.status_code,
                'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
                'title': context.soup.title.get_text(strip=True) if context.soup.title else '',
                'kind': 'roster' if url in roster_urls else 'profile', 'directory': key,
                'retrieved_at': datetime.now(timezone(timedelta(hours=8))).isoformat()}
        if url in roster_urls:
            found = roster(html, loaded, CARD_SELECTOR)
            for row in found:
                observations.append({**row, 'roster_url': url})
            item['observations'] = len(found)
            item['pager_text'] = [p.get_text(' ', strip=True) for p in context.soup.select('.p_pages')]
            next_links = [urljoin(loaded, a['href']) for a in context.soup.select('.p_pages .p_next a[href]')]
            item['next_urls'] = next_links
            item['terminal_pager_observed'] = bool(context.soup.select('.p_pages .p_next_d'))
            requests = []
            for next_url in next_links:
                if urlparse(next_url).netloc == urlparse(ENTRY).netloc and next_url not in roster_urls:
                    if len(roster_urls) >= 10:
                        caps.append({'kind': 'roster_cap', 'url': next_url})
                    else:
                        roster_urls.add(next_url)
                        requests.append(next_url)
            # Queue pagination before personal pages so missing people become visible early.
            if requests:
                await crawler.add_requests(requests)
            requests = []
            for row in found:
                link = row['profile_url']
                if not link or urlparse(link).netloc != urlparse(ENTRY).netloc:
                    caps.append({'kind': 'unfollowed_profile_link', 'row': row})
                    continue
                if link not in profile_urls:
                    if len(profile_urls) >= 100:
                        caps.append({'kind': 'profile_cap', 'url': link})
                    else:
                        profile_urls.add(link)
                        requests.append(link)
            if requests:
                await crawler.add_requests(requests)
        else:
            body = context.soup.select_one('.v_news_content')
            item['profile_container_found'] = body is not None
            if body:
                (folder / 'body.html').write_text(str(body), encoding='utf-8')
                (folder / 'body-text.txt').write_text(body.get_text('\n', strip=True), encoding='utf-8')
                item['body_chars'] = len(body.get_text('\n', strip=True))
            for engine, extracted in extract_variants(html, loaded).items():
                (folder / f'{engine}.txt').write_text(extracted['text'], encoding='utf-8')
                item[engine] = {k: v for k, v in extracted.items() if k != 'text'}
        pages.append(item)
        save_progress()
        await context.push_data(item)
        print(f"{item['kind']} {len(pages)}: {item['title']} ({item['bytes']} bytes)", flush=True)

    @crawler.failed_request_handler
    async def failure(context, error):
        failures.append({'url': context.request.url, 'retry_count': context.request.retry_count, 'error': str(error)})
        save_progress()

    @crawler.on_skipped_request
    async def skip(url, reason):
        skipped.append({'url': str(url), 'reason': str(reason)})
        write_json(out / 'skipped.json', skipped)

    await crawler.run([ENTRY])
    fetched = {p['url']: p for p in pages if p['kind'] == 'profile'}
    unique = {}
    for row in observations:
        key = (row['name'], row['profile_url'])
        if key not in unique:
            unique[key] = {**row, 'roster_urls': [], 'acquisition_status': 'not_saved'}
        unique[key]['roster_urls'].append(row['roster_url'])
        if row['profile_url'] in fetched:
            unique[key]['acquisition_status'] = 'html_saved'
            unique[key]['profile_directory'] = fetched[row['profile_url']]['directory']
    write_json(out / 'records.json', list(unique.values()))
    result = {'entry': ENTRY, 'roster_pages': [p for p in pages if p['kind']=='roster'],
              'observations': len(observations), 'unique_name_url_pairs': len(unique),
              'unique_profile_urls': len(profile_urls), 'profiles_saved': len(fetched),
              'profiles_with_body_container': sum(p.get('profile_container_found',False) for p in fetched.values()),
              'failures': failures, 'skipped': skipped, 'caps': caps,
              'user_reference_count': 73,
              'unfetched_profile_urls': sorted(profile_urls-set(fetched)),
              'coverage_scope': 'Given official roster, its next-page chain and linked same-host profiles',
              'whole_college_completeness': 'unverified',
              'identity_and_fields': 'not independently adjudicated'}
    write_json(out / 'summary.json', result)
    lines = ['# 单学院名单与个人页获取试验', '', f'入口：{ENTRY}',
             f"名单页：{len(result['roster_pages'])}；名单观察：{len(observations)}；不同姓名+链接：{len(unique)}。",
             f"个人链接：{len(profile_urls)}；已保存个人页：{len(fetched)}；有正文容器：{result['profiles_with_body_container']}。",
             f"失败：{len(failures)}；跳过：{len(skipped)}；触及限制：{len(caps)}。", '',
             '分页由本次页面实际“下页”链接逐页跟进，未用73硬编码停止。',
             '取得的HTML和正文属于原始采集材料；身份、字段正确性和是否存在其他师资分支尚未独立核验。',
             '全院完整性未验证。', '', '| 名单页 | 行数 | 后续页 | 末页禁用标记 |', '|---|---:|---|---|']
    for page in result['roster_pages']:
        lines.append(f"| {page['url']} | {page['observations']} | {page['next_urls']} | {page['terminal_pager_observed']} |")
    (out / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
    print((out / 'report.md').read_text(encoding='utf-8'), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
