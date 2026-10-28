"""Evidence-bound model plans; no teacher identity inference or generated URLs."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time
from urllib.parse import parse_qsl, urlsplit

from bs4 import BeautifulSoup
from deepseek_api import DeepSeekJSON, DEFAULT_MODEL, ApiFailure
from ai_regions import prepare, apply_plan, render_evidence, SYSTEM, CHECK_SYSTEM, CONTRACT, sha
from audit import write_json, pagination_family, without_scheme, disabled_link


def empty_result(message):
    return {'complete': False, 'issues': [message], 'notes': [], 'links': {},
            'anchors': [], 'title': '', 'root_count': 0, 'pagination_urls': []}


def pager_numbers(soup, nodes, plans):
    """Read page counters from source markup, never from a model-supplied count."""
    containers = list(soup.select('.pb_sys_common,.wp_paging,#wp_pager'))
    for plan in plans:
        containers.extend(nodes[i] for i in plan.get('pagination_regions', []) if i in nodes)
    counters = set()
    for node in containers:
        text = node.get_text(' ', strip=True)
        matches = re.findall(r'(?<!\d)(\d+)\s*/\s*(\d+)(?!\d)', text)
        matches.extend(re.findall(r'第\s*\[?\s*(\d+)\s*\]?\s*页\s*[,，]?\s*共\s*\[?\s*(\d+)\s*\]?\s*页', text))
        matches.extend(re.findall(r'第\s*(\d+)\s*页\s*/\s*总共\s*(\d+)\s*页', text))
        matches.extend((current, total) for total, current in re.findall(r'分\s*(\d+)\s*页\s*[,，]?\s*当前第\s*(\d+)\s*页', text))
        current = node.select_one('.current')
        total = re.search(r'共\s*(\d+)\s*页', text)
        if current and current.get_text(strip=True).isdigit() and total:
            matches.append((current.get_text(strip=True), total[1]))
        if not matches:
            current, total = node.select_one('.curr_page'), node.select_one('.all_pages')
            if current and total and current.get_text(strip=True).isdigit() and total.get_text(strip=True).isdigit():
                matches = [(current.get_text(strip=True), total.get_text(strip=True))]
        counters.update((int(a), int(b)) for a, b in matches if 0 < int(a) <= int(b) <= 10000)
    return sorted(counters)


def bounded_query_pages(pages, url, counters):
    """Some CMSs keep generating ?page=N+1 even beyond their declared last page."""
    if len(counters) != 1:
        return pages
    _, total = counters[0]
    bounded = []
    for target in pages:
        parts = urlsplit(target)
        values = [v for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() == 'page']
        if parts.path == urlsplit(url).path and len(values) == 1 and values[0].isdigit():
            number = int(values[0])
            if number > total:
                continue
        bounded.append(target)
    return bounded


def qualification(soup, nodes, anchors, plans, url):
    parsed = [apply_plan(soup, nodes, anchors, p, url) for p in plans]
    a, b = parsed
    issues = a['issues'] + b['issues']
    if a['included_ids'] != b['included_ids']:
        issues.append('两次结构判断选择的实际链接不一致，名单范围待人工核准')
    if {without_scheme(u) for u in a['pagination_urls']} != {without_scheme(u) for u in b['pagination_urls']}:
        issues.append('两次分页判断不一致')
    # Generic positive contradiction: a whole document root cannot certify that
    # menus and footer were comprehensively separated.
    if any(nodes[i].name in {'html', 'body'} for p in plans for i in p.get('roster_regions', [])):
        issues.append('选中了整页而非明确的名单区域')
    if not a['links']:
        issues.append('名单零链接须人工确认，模型判断不能自动清空原表')
    counters = sorted(set(pager_numbers(soup, nodes, plans) +
                          [(item['current'], item['total']) for item in a['component_pagers']]))
    if len({total for _, total in counters}) > 1:
        issues.append('同页分页总数相互矛盾')
    if len({current for current, _ in counters}) > 1:
        issues.append('同页分页当前页相互矛盾')
    pager_nodes = list(soup.select('.pb_sys_common,.wp_paging,#wp_pager'))
    pager_nodes.extend(nodes[i] for p in plans for i in p.get('pagination_regions', []))
    unresolved_next = [a for node in pager_nodes for a in node.select('a[href]')
        if a.get_text(' ',strip=True) in {'下一页','下页','Next','next','末页','尾页'}
        and not disabled_link(a)
        and not (anchors[int(a['data-mb-id'])]['url'] or anchors[int(a['data-mb-id'])].get('page_url'))]
    if unresolved_next and not (counters and all(current == total for current,total in counters)):
        issues.append('下一页依赖脚本或空目标，尚未确认分页已结束')
    result = {'complete': not issues, 'issues': list(dict.fromkeys(issues)), 'notes': [],
              'links': {u: {'url': u, 'names': v['names'], 'occurrences': len(v['anchor_ids'])} for u, v in a['links'].items()},
              'anchors': [], 'title': soup.title.get_text(' ', strip=True) if soup.title else '',
              'root_count': len(a['selected_regions']), 'pagination_urls': bounded_query_pages(a['pagination_urls'], url, counters),
              'pager_counters': counters, 'component_pagers': a['component_pagers']}
    for aid, anchor in anchors.items():
        owner = next((j for j, rid in enumerate(a['selected_regions'], 1)
                      if nodes[aid] is nodes[rid] or any(parent is nodes[rid] for parent in nodes[aid].parents)), 0)
        included = aid in a['included_ids']
        reason = '' if included else a['excluded'].get(str(aid), '位于所选名单区域之外，或为空目标/不可点击锚点')
        result['anchors'].append({'name': anchor['text'], 'href': anchor['href'], 'url': anchor['url'],
                                  'source_url': url, 'root_index': owner, 'html': anchor['html'],
                                  'reason': reason, 'included': included})
    return result, parsed


def check_coverage(sources):
    by_family = defaultdict(list)
    for s in sources:
        components = s['parsed'].get('component_pagers', [])
        if components:
            for item in components:
                key = ('component', item['host'], item['path'], item['fragment'],
                       tuple(map(tuple, item['fixed_query'])), item['component'], item['page_size'])
                if s not in by_family[key]:
                    by_family[key].append(s)
        else:
            by_family[pagination_family(s['roster_url'])].append(s)
    for members in by_family.values():
        counters = [pair for s in members for pair in s['parsed'].get('pager_counters', [])]
        totals = {total for _, total in counters}
        issues = []
        if len(totals) > 1:
            issues.append('同一栏目各页声明的总页数不同，完整性未确认')
        elif totals:
            total = next(iter(totals))
            present = {current for s in members if s['parsed']['complete'] for current, _ in s['parsed'].get('pager_counters', [])}
            missing = sorted(set(range(1, total + 1)) - present)
            if missing:
                issues.append('分页未完整读取，缺少页码：' + ','.join(map(str, missing[:30])))
        if issues:
            members[0]['parsed']['complete'] = False
            members[0]['parsed']['issues'].extend(issues)
            members[0]['failure_kind'] = 'structure'


class ModelEngine:
    def __init__(self, out, cache, api_key, max_calls=200, on_progress=None, should_cancel=None, client=None):
        self.out, self.cache = Path(out), Path(cache)
        self.api = client or DeepSeekJSON(self.out/'api', api_key=api_key, max_calls=max_calls)
        self.cache_hits = 0
        self.on_progress, self.should_cancel = on_progress, should_cancel
        self.contract = sha((SYSTEM + CHECK_SYSTEM + CONTRACT + '\n'.join(
            (Path(__file__).parent/f).read_text('utf-8') for f in ('ai_regions.py','api_engine.py','audit.py'))).encode())

    async def __aenter__(self):
        await self.api.__aenter__()
        self.cache.mkdir(parents=True, exist_ok=True)
        return self

    async def __aexit__(self, *args):
        await self.api.__aexit__(*args)

    def stats(self):
        tokens = Counter()
        for call in self.api.calls:
            tokens.update({k:v for k,v in call.get('usage',{}).items() if isinstance(v,int)})
        return {'model': self.api.model, 'calls': len(self.api.calls), 'max_calls': self.api.max_calls,
                'cache_hits': self.cache_hits, 'tokens': dict(tokens), 'contract': self.contract}

    async def analyze(self, html, url, folder):
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        analysis = {'method':'deepseek', 'cache_hit':False, 'model':self.api.model,
                    'contract':self.contract, 'raw_html_sha256':sha(html.encode()),
                    'warning':'自动结构检查不等于独立人工验收或全院完整性保证'}
        try:
            soup, nodes, anchors, payload = prepare(html, url)
            fingerprint = sha(json.dumps({'payload':payload,'model':self.api.model,'contract':self.contract},sort_keys=True,ensure_ascii=False).encode())
            cached = self.cache/(fingerprint+'.json')
            plans = None
            if cached.exists():
                try:
                    entry = json.loads(cached.read_text('utf-8'))
                    if (entry.get('fingerprint') == fingerprint and entry.get('contract') == self.contract and
                            time.time()-entry.get('created',0) < 7*86400):
                        candidate, _ = qualification(soup, nodes, anchors, entry['plans'], url)
                        if candidate['complete']:
                            plans = entry['plans']
                            self.cache_hits += 1
                            analysis['cache_hit'] = True
                except (OSError, ValueError, KeyError, TypeError, IndexError):
                    pass
            if plans is None:
                if self.api.max_calls-len(self.api.calls) < 2:
                    raise ApiFailure('本批API调用额度不足以完成两次结构检查；保留原表，未完成核验')
                plans = []
                for label, system in [('locate', SYSTEM), ('check', CHECK_SYSTEM)]:
                    if self.should_cancel and self.should_cancel():
                        raise InterruptedError('任务已停止；原表和已取得证据保留')
                    if self.on_progress:
                        self.on_progress('model_started', {'url':url,'phase':label,'api':self.stats()})
                    plans.append(await self.api.ask(label, system, payload, max_tokens=5500))
            result, parses = qualification(soup, nodes, anchors, plans, url)
            needs_recheck = (any(p['scope_conflicts'] or p['coverage_conflicts'] for p in parses)
                             or parses[0]['included_ids'] != parses[1]['included_ids'])
            if needs_recheck:
                write_json(folder/'plans-initial.json', {'analysis': analysis, 'plans': plans, 'issues': result['issues']})
                render_evidence(folder/'links-initial.html', url, anchors, *parses)
                if self.api.max_calls - len(self.api.calls) >= 2:
                    revised = []
                    for index, (label, system) in enumerate([('recheck-locate', SYSTEM), ('recheck-check', CHECK_SYSTEM)]):
                        if self.should_cancel and self.should_cancel():
                            raise InterruptedError('任务已停止；原表和已取得证据保留')
                        if self.on_progress:
                            self.on_progress('model_started', {'url': url, 'phase': label, 'api': self.stats()})
                        review = {**payload, 'previous_selection': plans[index],
                                  'structural_feedback': (parses[index]['scope_conflicts'] +
                                   ['名单平行结构尚未覆盖：' + json.dumps(c, ensure_ascii=False)
                                    for c in parses[index]['coverage_conflicts']]) or
                                  ['独立结构核对未通过。重新检查名单与所有平行条目、导航、分页的边界；范围不明则返回uncertain。']}
                        instruction = ('\n本次是结构纠错。previous_selection是你自己的上次选择；structural_feedback来自程序实际DOM检查。'
                                       '依据完整HTML重新选择。若反馈含DOM父子路径，则该路径证明排除区域覆盖了名单，不能用文字理由否认这个包含关系。'
                                       '应缩小导航排除范围或重新选择名单；仍不能确定则返回uncertain。不得盲目删除排除规则或采用更多链接。')
                        revised.append(await self.api.ask(label, system + instruction, review, max_tokens=5500))
                    plans = revised
                    result, parses = qualification(soup, nodes, anchors, plans, url)
                    analysis['recheck'] = 'completed'
                else:
                    analysis['recheck'] = 'budget_insufficient'
            write_json(folder/'plans.json', {'fingerprint':fingerprint,'analysis':analysis,'plans':plans})
            write_json(folder/'anchors.json', list(anchors.values()))
            render_evidence(folder/'links.html', url, anchors, *parses)
            if result['complete'] and not analysis['cache_hit']:
                write_json(cached, {'fingerprint':fingerprint,'contract':self.contract,'model':self.api.model,
                                    'created':time.time(),'plans':plans})
            analysis['proof_path'] = (folder/'links.html').relative_to(self.out).as_posix()
        except InterruptedError:
            raise
        except Exception as exc:
            # Provider exceptions must not expose request headers or credentials.
            result = empty_result(str(exc) if isinstance(exc,(ApiFailure,ValueError)) else '结构检查失败：'+type(exc).__name__)
        result['analysis'] = analysis
        write_json(folder/'analysis.json', {'analysis':analysis,'issues':result['issues']})
        if self.on_progress:
            self.on_progress('model_finished', {'url':url,'api':self.stats()})
        return result

    async def read(self, fetcher, task, replay, queue):
        from audit import read_source
        source = await read_source(fetcher, task, {'plans':{}}, replay, queue, follow_pagination=True)
        if source.get('failure_kind') in {'access','evidence'}:
            return source
        meta = source['attempts'][-1]
        html = (self.out/meta['html_path']).read_bytes().decode('utf-8')
        source['parsed'] = await self.analyze(html, meta.get('final_url') or task['roster_url'], self.out/'model-evidence'/task['id'])
        # A JS roster can expose only empty placeholder anchors in static HTML.
        # Render zero-link pages once before leaving them for human review;
        # unchanged rendering must not trigger duplicate model calls or a pass.
        uncertain = any('不能确认名单范围' in x or '没有明确的名单区域' in x for x in source['parsed']['issues'])
        if (uncertain or not source['parsed']['links']) and not replay and fetcher.use_browser and meta.get('method') == 'HTTP':
            rendered, rendered_meta = await fetcher.browser_fetch(task)
            source['attempts'].append(rendered_meta)
            if not rendered_meta.get('error') and (rendered_meta.get('status') or 500)<400 and BeautifulSoup(rendered,'lxml').get_text(strip=True):
                try:
                    changed = prepare(rendered,rendered_meta.get('final_url') or task['roster_url'])[3] != prepare(html,meta.get('final_url') or task['roster_url'])[3]
                except ValueError:
                    changed = True  # analyze records an oversized page as pending.
                if changed:
                    source['parsed'] = await self.analyze(rendered,rendered_meta.get('final_url') or task['roster_url'],self.out/'model-evidence'/(task['id']+'-rendered'))
                else:
                    source['attempts'].append({**meta,'selected_after_identical_render':True})
            else:
                source['attempts'].append({**meta,'selected_after_browser_failure':True})
        source['failure_kind'] = None if source['parsed']['complete'] else 'structure'
        return source
