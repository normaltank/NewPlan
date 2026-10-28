"""Standalone roster-link reconciliation. No imports from the main project.

Only roster URLs are requested. A target URL's availability never determines
whether it belongs in the result. Unknown or unreadable sources fail closed.
"""
from __future__ import annotations

from contextlib import AsyncExitStack
import argparse
import asyncio
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
import uuid
from urllib.parse import parse_qsl, urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup
from input_adapter import read_directory, tasks_from_rows
from runtime_paths import APP_ROOT, ASSETS, VERSION, browser_path, plans_path

ROOT = APP_ROOT


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def url_key(raw, base=None):
    """Resolve relative URLs without folding protocols, query or person fragments."""
    value = str(raw or '').strip()
    if not value or re.search(r'[\s<>]', value):
        return None
    if base:
        value = urljoin(base, value)
    try:
        p = urlsplit(value)
        if p.scheme.lower() not in ('http', 'https') or not p.hostname or p.username or p.password:
            return None
        port = p.port
    except ValueError:
        return None
    host = p.hostname.lower()
    if ':' in host:
        host = '[' + host + ']'
    if port and (p.scheme.lower(), port) not in [('http', 80), ('https', 443)]:
        host += ':' + str(port)
    return urlunsplit((p.scheme.lower(), host, p.path or '/', p.query, p.fragment))


def without_scheme(url):
    p = urlsplit(url)
    return p.netloc, p.path, p.query, p.fragment


def compact_name(label):
    return re.sub(r'\s+', '', label).strip('*＊')


def load_inputs(directory):
    """Keep every original row and source coordinate, including placeholder text."""
    rows, files, errors, _ = read_directory(directory)
    if errors:
        raise ValueError('\n'.join(errors))
    return tasks_from_rows(rows), files


def pagination_family(url):
    """Group observed list-page shapes while keeping columns and article IDs apart."""
    p = urlsplit(url)
    path = re.sub(r'/list\d*\.(htm|html)$', r'/list.\1', p.path)
    path = re.sub(r'/([^/]+)/\d+\.(htm|html)$', r'/\1.\2', path)
    path = re.sub(r'/index(?:_?\d+)?\.(?:s?html?|aspx)$', '/', path, flags=re.I)
    # These observed extensionless roster endpoints use _N; content_N is an article.
    path = re.sub(r'/(shizi|szdw)_\d+$', r'/\1', path)
    query = tuple(sorted((k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
                         if k.lower() not in ('page', 'pageno', 'pagenum')))
    return p.netloc.lower(), path, query


def disabled_link(node):
    return (node.has_attr('disabled') or node.get('aria-disabled') == 'true'
            or 'disabled' in node.get('class', []))


def component_query(url):
    """Read one observed CMS t/p/c triple; every other parameter stays fixed."""
    pairs = parse_qsl(urlsplit(url).query, keep_blank_values=True)
    if len({key for key, _ in pairs}) != len(pairs):
        return None
    fields = [(re.fullmatch(r'(a\d+)([tpc])', key), value) for key, value in pairs]
    fields = [(match, value) for match, value in fields if match]
    if len(fields) != 3 or len({match[1] for match, _ in fields}) != 1:
        return None
    values = {match[2]: value for match, value in fields}
    if set(values) != {'t', 'p', 'c'} or not all(value.isdigit() for value in values.values()):
        return None
    total, current, size = (int(values[key]) for key in ('t', 'p', 'c'))
    if not (0 < current <= total <= 10000 and size > 0):
        return None
    component = fields[0][0][1]
    fixed = sorted((key, value) for key, value in pairs if key not in {component + key for key in 'tpc'})
    return component, total, current, size, fixed


def component_pagers(containers, base):
    """Bind the observed p_pages controls to their current column and component."""
    source = urlsplit(base)
    source_query = component_query(base)
    fixed = source_query[4] if source_query else sorted(parse_qsl(source.query, keep_blank_values=True))
    evidence, issues, seen = [], [], set()
    for container in containers:
        regions = ([container] if 'p_pages' in container.get('class', []) else []) + container.select('.p_pages')
        for region in regions:
            if id(region) in seen:
                continue
            seen.add(id(region))
            candidates, first_urls = [], []
            for anchor in region.select('a[href]'):
                if disabled_link(anchor):
                    continue
                target = (url_key(anchor['href'], base) if anchor['href'].strip() not in {'', '#'} else None)
                target = target or anchor.get('data-mb-page-target') or fixed_paging_target(anchor, base)
                if not target:
                    continue
                parts, triple = urlsplit(target), component_query(target)
                if (parts.netloc.lower(), parts.path, parts.fragment) != (source.netloc.lower(), source.path, source.fragment):
                    continue
                label = anchor.get_text(' ', strip=True)
                if triple and triple[4] == fixed:
                    candidates.append((triple, label))
                elif not triple and sorted(parse_qsl(parts.query, keep_blank_values=True)) == fixed and label in {'1', '首页', '第一页'}:
                    first_urls.append(target)
            if not candidates:
                continue
            signatures = {(triple[0], triple[1], triple[3]) for triple, _ in candidates}
            current_nodes = region.select('.p_no_d')
            if len(signatures) != 1 or len(current_nodes) != 1 or not current_nodes[0].get_text(strip=True).isdigit():
                issues.append('组件分页的组件、总页数或当前页证据不唯一，完整性未确认')
                continue
            component, total, size = next(iter(signatures))
            current = int(current_nodes[0].get_text(strip=True))
            numbered = [(triple, label) for triple, label in candidates if label.isdigit()]
            if (not 0 < current <= total or not numbered or any(int(label) != triple[2] for triple, label in numbered)
                    or (source_query and source_query[:4] != (component, total, current, size))
                    or (not source_query and current != 1)):
                issues.append('组件分页的地址与当前页或页码声明矛盾，完整性未确认')
                continue
            evidence.append({'component': component, 'host': source.netloc.lower(), 'path': source.path,
                             'fragment': source.fragment, 'fixed_query': fixed, 'total': total,
                             'page_size': size, 'current': current, 'first_urls': first_urls,
                             'region_id': region.get('data-mb-id')})
    return evidence, list(dict.fromkeys(issues))


def component_page_matches(evidence, target):
    parts, triple = urlsplit(target), component_query(target)
    if (parts.netloc.lower(), parts.path, parts.fragment) != (evidence['host'], evidence['path'], evidence['fragment']):
        return False
    if triple:
        return (triple[0] == evidence['component'] and triple[1] == evidence['total']
                and triple[3] == evidence['page_size'] and triple[4] == evidence['fixed_query'])
    return any(without_scheme(target) == without_scheme(first) for first in evidence['first_urls'])


def fixed_paging_target(node, base):
    """Read the observed literal onclick redirect without evaluating JavaScript."""
    if node.get('href', '').strip() not in {'', '#'}:
        return None
    match = re.fullmatch(r"\s*(?:javascript:\s*)?(?:window\.)?location\.href\s*=\s*encodeURI\((['\"])([^'\"\\\r\n]+)\1\)\s*;?\s*",
                         node.get('onclick', ''))
    return url_key(match[2], base) if match else None


def lookup_plan(config, url):
    plans = config['plans']
    if url in plans:
        return plans[url]
    # Explicitly registered column plans can be reused on that column's pages.
    matches = [p for u, p in plans.items() if p and p.get('selector') and
               pagination_family(u) == pagination_family(url)]
    return matches[0] if matches and all(p['selector'] == matches[0]['selector'] for p in matches) else None


def pagination_links(soup, base, plan):
    urls, issues = [], []
    selector = plan.get('pagination_selector', '.pb_sys_common, .wp_paging, #wp_pager')
    for container in soup.select(selector):
        before = len(urls)
        for a in container.select('a[href]'):
            href = a['href'].strip()
            if disabled_link(a):
                continue
            target = (url_key(href, base) if href and href != '#' else None) or fixed_paging_target(a, base)
            if (not href or href == '#') and not target:
                continue
            if not target:
                # WebPlus renders inert first/previous/next/last buttons even
                # on single-page lists; they are not missing roster pages.
                if href.lower() not in ('javascript:void(0);', 'javascript:void(0)', 'javascript:;'):
                    issues.append('分页按钮没有可读取的地址，无法确认后续页面')
                continue
            if pagination_family(target) != pagination_family(base):
                issues.append('分页链接越出当前栏目，未自动访问：' + target)
            elif target not in urls:
                urls.append(target)
        total = container.select_one('.all_pages')
        if total and total.get_text(strip=True).isdigit() and int(total.get_text(strip=True)) > 1 and len(urls) == before:
            issues.append('页面声明有多页，但尚未取得可读取的分页地址')
    return urls, issues


def parse_roster(html, source_url, plan, scope_urls=None, follow_pagination=False):
    soup = BeautifulSoup(html, 'lxml')
    title = soup.title.get_text(' ', strip=True) if soup.title else ''
    issues, notes, anchors = [], [], []
    selector = plan.get('selector') if plan else None
    if not selector:
        return {'complete': False, 'issues': ['尚无经过核实的名单区域配置'], 'notes': [],
                'links': {}, 'anchors': [], 'title': title, 'root_count': 0}
    if plan.get('title_contains', '') not in title:
        issues.append('页面标题与已核实的名单类型不符')
    roots = soup.select(selector)
    if not roots:
        issues.append('未找到已配置的名单区域（可能访问失败、页面改版或需要动态加载）')
    base_tag = soup.select_one('base[href]')
    base = url_key(base_tag['href'], source_url) if base_tag else source_url
    base = base or source_url
    seen_nodes = set()
    pager_anchor_ids = {id(a) for c in soup.select(plan.get('pagination_selector', '.pb_sys_common, .wp_paging, #wp_pager')) for a in c.select('a[href]')}
    links = {}
    for root_index, root in enumerate(roots, 1):
        for anchor in root.select('a[href]'):
            if id(anchor) in seen_nodes:
                continue
            seen_nodes.add(id(anchor))
            href = anchor['href'].strip()
            label = anchor.get_text(' ', strip=True)
            label = label or anchor.get('aria-label', '').strip() or anchor.get('title', '').strip()
            label = label or ' '.join(img.get('alt', '').strip() for img in anchor.select('img[alt]')).strip()
            item = {'name': label, 'href': href, 'url': url_key(href, base), 'source_url': source_url,
                    'root_index': root_index, 'html': str(anchor), 'reason': '', 'included': False}
            if id(anchor) in pager_anchor_ids:
                item['reason'] = '分页控件链接，不计入名单条目'
            elif not href or href == '#':
                item['reason'] = '空目标或#占位，没有提供个人页地址'
            elif not item['url']:
                item['reason'] = '非HTTP链接，无法直接形成主页URL'
                if label and href.lower().startswith('javascript:'):
                    issues.append('名单含需执行脚本才能确定目标的链接')
            elif not label and not anchor.select('img, svg'):
                item['reason'] = '空锚点，没有可点击文字或图像'
            else:
                item['included'] = True
                if not label:
                    item['reason'] = '图片链接无姓名；依据已核实的名单区域保留'
                p = urlsplit(item['url'])
                if p.path in ('/', '/index.htm', '/index.html', '/main.htm', '/main.html'):
                    notes.append({'kind': '官网目标疑似首页', 'url': item['url'], 'name': label,
                                  'message': '按源链接保留；本任务不检查目标内容、不擅自更换地址'})
                current = links.setdefault(item['url'], {'url': item['url'], 'names': [], 'occurrences': 0})
                if label and label not in current['names']:
                    current['names'].append(label)
                current['occurrences'] += 1
            anchors.append(item)
    for item in links.values():
        if len({compact_name(x) for x in item['names'] if compact_name(x)}) > 1:
            notes.append({'kind': '同一目标对应不同姓名', 'url': item['url'], 'name': ' / '.join(item['names']),
                          'message': '本任务按链接对账，保留全部文字证据，不推断人员身份或修正官网'})
    if roots and not links:
        markers = plan.get('empty_confirmation_text', [])
        text = ' '.join(root.get_text(' ', strip=True) for root in roots)
        if markers and all(marker in text for marker in markers):
            notes.append({'kind': '来源正文没有链接', 'url': source_url, 'name': '',
                          'message': '已核实的正文标记仍存在，但正文没有可点击目标；此来源贡献0条链接，不把源页面自身冒充正文链接'})
        else:
            issues.append('名单区域没有有效目标链接，不能据此自动判空或清空输入表')
    pages, page_issues = pagination_links(soup, base, plan)
    if follow_pagination:
        issues.extend(page_issues)
    # Direct parser callers can still require an explicitly enumerated scope.
    allowed = {url_key(u) for u in (scope_urls or [source_url])}
    for a in soup.select('a[href]'):
        text = a.get_text('', strip=True)
        if (text in ('下一页', '下页', 'Next', 'next', '尾页', '末页') or 'next' in a.get('rel', [])):
            if a.get('href', '').strip() not in ('', '#') and not a.get('aria-disabled') == 'true':
                if not follow_pagination and url_key(a['href'], base) not in allowed:
                    issues.append('检测到未包含在输入范围内的分页入口，需补充师资URL后核验')
    return {'complete': not issues, 'issues': sorted(set(issues)), 'notes': notes, 'links': links,
            'anchors': anchors, 'title': title, 'root_count': len(roots), 'pagination_urls': pages}


def combine_sources(sources):
    """Union explicit roster pages while retaining all provenance and failures."""
    combined = {'complete': True, 'issues': [], 'notes': [], 'links': {}, 'anchors': [],
                'title': '', 'root_count': 0}
    for source in sources:
        parsed, url = source['parsed'], source['roster_url']
        combined['complete'] &= parsed['complete']
        combined['issues'].extend(url + '：' + issue for issue in parsed['issues'])
        combined['notes'].extend({**note, 'source_url': url} for note in parsed['notes'])
        for anchor in parsed['anchors']:
            combined['anchors'].append({**anchor, 'root_index': anchor['root_index'] + combined['root_count'] if anchor['root_index'] else 0,
                                        'source_url': url, 'html_path': source['attempts'][-1].get('html_path', '')})
        combined['root_count'] += parsed['root_count']
        for target, observation in parsed['links'].items():
            entry = combined['links'].setdefault(target, {'url': target, 'names': [], 'occurrences': 0, 'sources': []})
            entry['occurrences'] += observation['occurrences']
            entry['names'] = list(dict.fromkeys(entry['names'] + observation['names']))
            if url not in entry['sources']:
                entry['sources'].append(url)
    return combined


def reconcile(task, parsed):
    rows = task['rows']
    issues = list(parsed['issues'])
    if any(row['hyperlink_mismatch'] for row in rows):
        issues.append('Excel显示地址与实际超链接目标不一致，需确认以哪一个为准')
    complete = parsed['complete'] and not issues
    counts = Counter(row['url'] for row in rows if row['url'])
    stats = {'input_rows': len(rows), 'input_url_rows': sum(counts.values()), 'input_unique': len(counts),
             'input_placeholders': sum(not row['url'] for row in rows),
             'input_duplicates': sum(n - 1 for n in counts.values()),
             'source_occurrences': sum(v['occurrences'] for v in parsed['links'].values()) if complete else None,
             'source_unique': len(parsed['links']) if complete else None,
             'source_placeholders': sum(not a['included'] and a['root_index'] > 0 and not a.get('url') for a in parsed['anchors']) if complete else None,
             'matched': None, 'missing': None, 'extra': None, 'protocol_changes': None,
             'literal_missing': None, 'literal_extra': None, 'corrected': None}
    diffs = []
    if not complete:
        for row in rows:
            diffs.append({**row, 'action': '未判定，原样保留', 'new_url': row['value'], 'name': '',
                          'reason': '未取得完整可靠的名单，不能自动增删'})
        return {'complete': False, 'needs_human': True, 'reason': '；'.join(dict.fromkeys(issues)),
                'stats': stats, 'diffs': diffs, 'corrected_urls': [], 'verdict': '需要人工介入'}

    expected = set(parsed['links'])
    supplied = set(counts)
    missing = expected - supplied
    extra = supplied - expected
    literal_missing, literal_extra = len(missing), len(extra)
    # Explicit replacement with the source spelling, not an assertion that two
    # protocols resolve to the same document. Never GET either target to decide.
    expected_by_path, extra_by_path = defaultdict(list), defaultdict(list)
    for u in expected:
        expected_by_path[without_scheme(u)].append(u)
    for u in extra:
        extra_by_path[without_scheme(u)].append(u)
    replacements = {}
    for path, old in extra_by_path.items():
        new = expected_by_path.get(path, [])
        if len(new) == 1:
            replacements.update((url, new[0]) for url in old)
    missing -= set(replacements.values())
    extra -= set(replacements)
    seen, kept = set(), set()
    for row in rows:
        u = row['url']
        new = replacements.get(u, u)
        name = ' / '.join(parsed['links'].get(new, {}).get('names', []))
        if not u:
            action, reason, new = '移出非URL标记', '保留原行证据；不把“无详细页”或名单地址当作个人主页', ''
        elif u in seen:
            action, reason, new = '移出重复行', '同一输入链接已经有一行保留', ''
        elif new in kept:
            action, reason, new = '移出协议重复行', '同一目标地址仅http/https不同，已按官网写法保留一行', ''
        elif u in replacements:
            action, reason = '按源修正协议', '主机、路径、参数和锚点一致；协议改成源页面实际提供的写法，不推断可访问性'
        elif u in extra:
            action, reason, new = '移出范围外链接', '当前指定名单中未找到此地址；不推断此人是否属于学院', ''
        else:
            action, reason = '保留', '与指定名单提供的链接相符'
        if u:
            seen.add(u)
        if new:
            kept.add(new)
        diffs.append({**row, 'action': action, 'new_url': new, 'name': name, 'reason': reason,
                      'source_urls': parsed['links'].get(new, {}).get('sources', [])})
    for u in sorted(missing):
        diffs.append({'file': '', 'sheet': '', 'row': None, 'value': '', 'url': None,
                      'action': '补入缺少链接', 'new_url': u,
                      'name': ' / '.join(parsed['links'][u]['names']), 'reason': '当前指定名单存在，但输入表未收录',
                      'source_urls': parsed['links'][u].get('sources', [])})
    stats.update(matched=len(expected & supplied), missing=len(missing), extra=len(extra),
                 protocol_changes=len(replacements), literal_missing=literal_missing,
                 literal_extra=literal_extra, corrected=len(expected))
    changed = any(d['action'] != '保留' for d in diffs)
    return {'complete': True, 'needs_human': False, 'reason': '已逐项对账；目标页面可访问性不参与判定',
            'stats': stats, 'diffs': diffs, 'corrected_urls': list(parsed['links']),
            'verdict': '无需人工，已自动修正' if changed else '无需人工，原表吻合'}


class Fetcher:
    def __init__(self, out, browser=True):
        self.out = out
        self.use_browser = browser
        self.pw = self.browser = self.context = None
        self.client = None
        self.last_request = {}
        self.browser_hosts = set()
        self.blocked_hosts = {}

    async def __aenter__(self):
        self.client = httpx.AsyncClient(follow_redirects=True, timeout=25,
                                      headers={'User-Agent': 'Mozilla/5.0 (compatible; FacultyLinkAudit/1.0)'})
        return self

    async def __aexit__(self, *exc):
        await self.client.aclose()
        if self.browser:
            await self.browser.close()
        if self.pw:
            await self.pw.stop()

    def save(self, task_id, kind, html, meta, raw=None):
        folder = self.out / 'evidence' / task_id
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (kind + '.html')
        suffix = 2
        while path.exists():
            path = folder / (kind + '_' + str(suffix) + '.html')
            suffix += 1
        kind = path.stem
        # Preserve byte-identical HTML on Windows; newline translation would
        # invalidate the evidence digest during replay.
        path.write_bytes(html.encode('utf-8'))
        meta['html_sha256'] = sha(html.encode())
        meta['html_path'] = path.relative_to(self.out).as_posix()
        if raw is not None:
            (folder / (kind + '.bin')).write_bytes(raw)
            meta['raw_sha256'] = sha(raw)
        write_json(folder / (kind + '.json'), meta)

    async def pace(self, url):
        host = urlsplit(url).netloc
        delay = 3 - (time.monotonic() - self.last_request.get(host, 0))
        if delay > 0:
            await asyncio.sleep(delay)
        self.last_request[host] = time.monotonic()

    async def http(self, task):
        meta = {'requested_url': task['roster_url'], 'method': 'HTTP',
                'captured_at': datetime.now(timezone.utc).isoformat()}
        html = ''
        try:
            await self.pace(task['roster_url'])
            r = await self.client.get(task['roster_url'])
            html = str(BeautifulSoup(r.content, 'lxml'))
            meta.update(status=r.status_code, final_url=str(r.url), redirects=[str(x.url) for x in r.history])
            self.save(task['id'], 'http', html, meta, r.content)
        except Exception as e:
            meta['error'] = type(e).__name__ + ': ' + str(e)
            self.save(task['id'], 'http', html, meta)
        return html, meta

    async def browser_fetch(self, task):
        meta = {'requested_url': task['roster_url'], 'method': '独立浏览器',
                'captured_at': datetime.now(timezone.utc).isoformat()}
        html, page = '', None
        try:
            if self.pw is None:
                from playwright.async_api import async_playwright
                # Browser location must be set BEFORE spawning the Node driver;
                # the frozen driver otherwise assumes its own .local-browsers.
                executable = browser_path()
                self.pw = await async_playwright().start()
                self.browser = await self.pw.chromium.launch(headless=True, executable_path=executable)
                self.context = await self.browser.new_context()
            if self.browser is None:
                raise RuntimeError('独立浏览器不可用')
            await self.pace(task['roster_url'])
            page = await self.context.new_page()
            navigations = []
            def response_seen(response):
                if response.request.is_navigation_request() and response.frame == page.main_frame:
                    navigations.append({'status': response.status, 'url': response.url})
            page.on('response', response_seen)
            r = await page.goto(task['roster_url'], wait_until='domcontentloaded', timeout=35000)
            await page.wait_for_timeout(4000)
            html = await page.content()
            # The first response may be a JS loading/challenge page. Record the
            # response that produced the final document, not the initial status.
            if not BeautifulSoup(html, 'lxml').get_text(strip=True):
                await page.wait_for_timeout(6000)
                html = await page.content()
            meta.update(status=navigations[-1]['status'] if navigations else (r.status if r else None),
                        final_url=page.url, navigations=navigations)
        except Exception as e:
            meta['error'] = type(e).__name__ + ': ' + str(e)
        finally:
            self.save(task['id'], 'browser', html, meta)
            if page:
                await page.close()
        return html, meta


async def read_source(fetcher, task, config, replay, scope_urls, follow_pagination=False):
    plan = lookup_plan(config, task['roster_url'])
    attempts = []
    host = urlsplit(task['roster_url']).netloc
    if replay:
        old = replay.resolve() / 'evidence' / task['id']
        meta_path = old / ('browser.json' if (old / 'browser.json').exists() else 'http.json')
        if not hasattr(fetcher, 'replay_selected'):
            saved = replay.resolve() / 'results.json'
            records = json.loads(saved.read_text('utf-8')) if saved.exists() else []
            fetcher.replay_selected = {s['roster_url']: s['attempts'][-1].get('html_path')
                                      for r in records for s in r.get('sources', []) if s.get('attempts')}
        selected = fetcher.replay_selected.get(task['roster_url'])
        if selected:
            candidate = (replay.resolve() / selected).with_suffix('.json')
            if candidate.is_relative_to(replay.resolve()) and candidate.exists():
                meta_path = candidate
        if not meta_path.exists():
            html, meta = '', {'error': '回放缺少来源快照', 'error_kind': 'evidence',
                              'method': '保存页回放', 'final_url': task['roster_url'], 'requested_url': task['roster_url']}
        else:
            meta = json.loads(meta_path.read_text(encoding='utf-8'))
            snapshot_bytes = meta_path.with_suffix('.html').read_bytes()
            html = snapshot_bytes.decode('utf-8')
            if sha(snapshot_bytes) != meta.get('html_sha256') or meta.get('requested_url') != task['roster_url']:
                raise ValueError('回放快照校验失败：' + task['id'])
            meta['replayed_from'] = str(meta_path)
        fetcher.save(task['id'], 'replay', html, meta)
        attempts.append(meta.copy())
        parsed = parse_roster(html, meta.get('final_url', task['roster_url']), plan, scope_urls, follow_pagination)
    elif host in fetcher.blocked_hosts:
        html = ''
        meta = {'requested_url': task['roster_url'], 'final_url': task['roster_url'],
                'method': '站点暂停', 'captured_at': datetime.now(timezone.utc).isoformat(),
                'error': fetcher.blocked_hosts[host]}
        fetcher.save(task['id'], 'paused', html, meta)
        attempts.append(meta.copy())
        parsed = parse_roster(html, task['roster_url'], plan, scope_urls, follow_pagination)
    elif host in fetcher.browser_hosts and fetcher.use_browser:
        html, meta = await fetcher.browser_fetch(task)
        attempts.append(meta.copy())
        parsed = parse_roster(html, meta.get('final_url', task['roster_url']), plan, scope_urls, follow_pagination)
    else:
        html, meta = await fetcher.http(task)
        attempts.append(meta.copy())
        if meta.get('error'):
            html, meta = await fetcher.http(task)  # One retry for transient transport errors.
            attempts.append(meta.copy())
        parsed = parse_roster(html, meta.get('final_url', task['roster_url']), plan, scope_urls, follow_pagination)
        visible = BeautifulSoup(html, 'lxml').get_text(strip=True)
        needs_browser = bool(meta.get('error') or (meta.get('status') or 500) >= 400 or not visible or
                             (plan and plan.get('selector') and not parsed['complete']))
        if needs_browser and fetcher.use_browser:
            old_html, old_meta, old_parsed = html, meta, parsed
            browser_html, browser_meta = await fetcher.browser_fetch(task)
            attempts.append(browser_meta.copy())
            browser_parsed = parse_roster(browser_html, browser_meta.get('final_url', task['roster_url']), plan, scope_urls, follow_pagination)
            if (not browser_meta.get('error') and (browser_meta.get('status') or 500) < 400 and
                    BeautifulSoup(browser_html, 'lxml').get_text(strip=True)) or not visible or old_meta.get('error') or (old_meta.get('status') or 500) >= 400:
                html, meta, parsed = browser_html, browser_meta, browser_parsed
            else:
                html, meta, parsed = old_html, old_meta, old_parsed
                # Provenance references the selected successful attempt.
                attempts.append({**meta, 'selected_after_browser_failure': True})
            if (meta is browser_meta and not meta.get('error') and (meta.get('status') or 500) < 400
                    and ((old_meta.get('status') or 500) >= 400 or old_meta.get('error'))):
                fetcher.browser_hosts.add(host)
    visible_text = BeautifulSoup(html, 'lxml').get_text(' ', strip=True)
    if '网站防火墙' in visible_text and '黑名单' in visible_text:
        fetcher.blocked_hosts[host] = '网站防火墙明确提示当前IP被限制；已暂停本轮对该站的后续请求，请稍后重试或联系网站管理员'
        parsed['issues'].append(fetcher.blocked_hosts[host])
        parsed['complete'] = False
    inaccessible = bool(meta.get('error') or (meta.get('status') is not None and meta['status'] >= 400))
    if inaccessible:
        parsed['complete'] = False
        parsed['issues'].append('师资来源未正常取得：' + str(meta.get('error') or ('HTTP ' + str(meta['status']))))
    if not parsed['complete'] and not BeautifulSoup(html, 'lxml').get_text(strip=True):
        parsed['issues'].append('返回空文档，未取得教师名单')
        inaccessible = True
    return {'roster_url': task['roster_url'], 'parsed': parsed, 'attempts': attempts, 'plan': plan,
            'failure_kind': ('evidence' if meta.get('error_kind') == 'evidence' else
                             'access' if inaccessible else 'structure') if not parsed['complete'] else None}
async def run(args, on_progress=None, should_cancel=None):
    def progress(event, **data):
        if on_progress:
            on_progress(event, data)
    input_dir = args.input.resolve()
    out = args.output.resolve() if args.output else ROOT / 'outputs' / datetime.now().strftime('%Y%m%d-%H%M%S')
    if not out.is_relative_to(ROOT) or out == ROOT:
        raise ValueError('所有输出必须在SmallMission的独立子目录中')
    if out.exists():
        raise ValueError('输出目录已存在，请使用新目录，避免覆盖历史核验')
    tasks, files = load_inputs(input_dir)
    config_path = args.plans.resolve()
    config = json.loads(config_path.read_text(encoding='utf-8'))
    out.mkdir(parents=True)
    (out / 'inputs').mkdir()
    (out / 'code').mkdir()
    for name in ('audit.py', 'reporting.py', 'input_adapter.py', 'runtime_paths.py', 'requirements.txt', 'api_engine.py', 'ai_regions.py', 'deepseek_api.py'):
        shutil.copy2(ASSETS / name, out / 'code' / name)
    for f in files:
        shutil.copy2(input_dir / f['name'], out / 'inputs' / f['name'])
    write_json(out / 'source_plans.json', config)
    results = []
    mode = getattr(args, 'mode', 'rules')
    engine = None
    async with AsyncExitStack() as stack:
        fetcher = await stack.enter_async_context(Fetcher(out, browser=not args.no_browser))
        if mode == 'deepseek':
            from api_engine import ModelEngine
            engine = await stack.enter_async_context(ModelEngine(out, getattr(args, 'cache_dir', None) or ROOT/'data'/'model-cache',
                getattr(args, 'api_key', None), max_calls=getattr(args, 'max_api_calls', 200),
                on_progress=on_progress, should_cancel=should_cancel))
        for index, task in enumerate(tasks):
            if should_cancel and should_cancel():
                raise InterruptedError('已停止；已完成的来源证据保存在本次任务目录中，未生成完整交付表')
            progress('college_started', index=index, total=len(tasks), school=task['school'], college=task['college'])
            sources = []
            queue = list(task['roster_urls'])
            discovered_from = {}
            seen = set()
            for source_index, url in enumerate(queue, 1):
                key = without_scheme(url)
                if key in seen:
                    continue
                seen.add(key)
                if should_cancel and should_cancel():
                    raise InterruptedError('已停止；来源证据已保存，未生成完整交付表')
                progress('source_started', school=task['school'], college=task['college'],
                         source_index=source_index, source_total=len(queue))
                source_task = {**task, 'roster_url': url,
                               'id': sha('\n'.join((task['school'], task['college'], url)).encode())[:12]}
                source = (await engine.read(fetcher, source_task, args.replay, queue) if engine else
                          await read_source(fetcher, source_task, config, args.replay, queue, follow_pagination=True))
                source['discovered_from'] = discovered_from.get(url)
                sources.append(source)
                for page_url in source['parsed'].get('pagination_urls', []):
                    if without_scheme(page_url) not in {without_scheme(u) for u in queue}:
                        if len(queue) >= 200:
                            source['parsed']['complete'] = False
                            source['parsed']['issues'].append('同一学院分页超过200页，本次未完成全量核验')
                            source['failure_kind'] = 'structure'
                            break
                        # Reuse only this verified column's plan, never a sibling column.
                        if not lookup_plan(config, page_url):
                            config['plans'][page_url] = source['plan']
                        queue.append(page_url)
                        discovered_from[page_url] = url
            if engine:
                from api_engine import check_coverage
                check_coverage(sources)
            parsed = combine_sources(sources)
            attempts = [a for source in sources for a in source['attempts']]
            result = {**{k: v for k, v in task.items() if k != 'rows'}, **reconcile(task, parsed),
                      'provided_roster_urls': task['roster_urls'], 'roster_urls': [s['roster_url'] for s in sources],
                      'source': parsed, 'attempts': attempts, 'plan': sources[0]['plan'],
                      'sources': [{'roster_url': s['roster_url'], 'complete': s['parsed']['complete'],
                                   'issues': s['parsed']['issues'], 'failure_kind': s['failure_kind'],
                                   'attempts': s['attempts'], 'plan': s['plan'],
                                   'discovered_from': s.get('discovered_from'), 'analysis': s['parsed'].get('analysis')} for s in sources]}
            results.append(result)
            write_json(out / 'results.json', results)
            progress('college_finished', index=index + 1, total=len(tasks), result=result)
            if sys.stdout:
                print(json.dumps({'school': task['school'], 'college': task['college'],
                                  'verdict': result['verdict'], **result['stats']}, ensure_ascii=False), flush=True)
    # No writes are made to source workbooks, and verify that they remained unchanged.
    for f in files:
        if sha((input_dir / f['name']).read_bytes()) != f['sha256']:
            raise RuntimeError('输入文件在核验过程中发生变化，请重新运行：' + f['name'])
    versions = {}
    for name in ('httpx', 'beautifulsoup4', 'lxml', 'openpyxl', 'playwright', 'xlrd'):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    manifest = {'version': VERSION, 'run_id': uuid.uuid4().hex, 'finished_at': datetime.now(timezone.utc).isoformat(),
                'scope': '核验输入师资URL及同栏目的全部可识别分页；按学院合并去重，不扩展其他栏目、不访问个人页',
                'mode': '保存页回放' if args.replay else '实时核验',
                'inputs': files, 'source_plans_sha256': sha(config_path.read_bytes()),
                'code_sha256': {p.name: sha(p.read_bytes()) for p in (out / 'code').glob('*') if p.is_file()},
                'python': sys.version.split()[0], 'dependencies': versions, 'model_api_calls': 0, 'explicit_profile_fetches': 0,
                'needs_human': sum(r['needs_human'] for r in results), 'colleges': len(results),
                'configuration_note': '只在来源页面与已核实名单区域配置相符时完成对账；未知结构标明未完成，不宣称新站点零配置通用'}
    manifest['engine'] = mode
    manifest['summary_rule'] = 'url_set_v1'
    if engine:
        manifest['api'] = engine.stats()
        manifest['model_api_calls'] = manifest['api']['calls']
        manifest['configuration_note'] = 'API识别名单范围；真实链接与分页由程序检查。两次结构判断一致不等于独立人工验收。'
    write_json(out / 'manifest.json', manifest)
    progress('exporting', total=len(tasks))
    from reporting import export
    export(out, results, manifest)
    write_json(out / 'manifest.json', manifest)
    write_json(out / 'results.json', results)
    progress('done', total=len(tasks))
    if sys.stdout:
        print('OUTPUT=' + str(out), flush=True)
    return out, results, manifest


def main():
    parser = argparse.ArgumentParser(description='Mission B：指定师资页与教师URL表逐项核验')
    parser.add_argument('--input', type=Path, default=ROOT.parent)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--plans', type=Path, default=plans_path())
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--replay', type=Path, help='旧输出目录：不联网，使用当时保存的页面验证')
    parser.add_argument('--mode', choices=['rules','deepseek'], default='rules')
    parser.add_argument('--max-api-calls', type=int, default=200)
    parser.add_argument('--cache-dir', type=Path)
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == '__main__':
    main()
