"""Bounded evidence for preloaded, same-document native client pagination.

Supported structure: ID-bearing sibling containers of repeated direct entries,
one hidden preload, one visible list, and one pb_sys_common data-page pager.
Anything outside this observed structure remains pending; no script is parsed.
"""
import asyncio
from collections import Counter
import json
import re
import time
from urllib.parse import urldefrag

from audit import disabled_link, url_key, write_json

PAGING_ISSUE = '下一页依赖脚本或空目标，尚未确认分页已结束'
MAX_PAGES = 30
MAX_SECONDS = 45


def selected_preloads(nodes, plans, url):
    """Describe only full repeated-entry containers covered by both selections."""
    result = []
    pagers = [n for n in nodes.values() if 'pb_sys_common' in n.get('class', [])]
    if len(pagers) != 1:
        return result
    pager = pagers[0]
    for node in nodes.values():
        if (node.name == 'a' and node.get_text(' ',strip=True) in {'下页','下一页','Next','next','尾页','末页'}
                and not disabled_link(node) and not url_key(node.get('href',''),url)
                and pager not in node.parents):
            return result
    # The issue is shared by all unresolved next controls. Do not release it
    # when another selected pager has a separate unresolved control.
    for plan in plans:
        for ident in plan.get('pagination_regions', []):
            if nodes[ident] is not pager and pager not in nodes[ident].parents and nodes[ident] not in pager.parents:
                return result
    for node in nodes.values():
        children = node.find_all(recursive=False)
        if not node.get('id') or len(children) < 2:
            continue
        classes = set(children[0].get('class', []))
        for child in children[1:]:
            classes.intersection_update(child.get('class', []))
        if not classes:
            continue
        if not all(all(any(child is nodes[r] or nodes[r] in child.parents
                           for r in plan['roster_regions'])
                       and not any(child is nodes[e['id']] or nodes[e['id']] in child.parents
                                   or child in nodes[e['id']].parents
                                   for e in plan.get('exclude_regions', []))
                       for child in children) for plan in plans):
            continue
        entries = []
        for child in children:
            anchors = ([child] if child.name == 'a' else []) + child.select('a[href]')
            entries.append({'text': child.get_text(' ', strip=True),
                            'urls': [url_key(a.get('href', ''), url) for a in anchors
                                     if url_key(a.get('href', ''), url)]})
        if all(item['text'] for item in entries):
            result.append({'id': node['id'], 'classes': sorted(classes), 'entries': entries})
    return result


def multiset(entries):
    return Counter(json.dumps(item, sort_keys=True, ensure_ascii=False) for item in entries)


# This is our fixed DOM inspection program, never source-page script text.
SNAPSHOT = r'''scope => {
 const visible=e=>!!(e && e.getClientRects().length && getComputedStyle(e).visibility!=='hidden');
 const entries=e=>[...e.children].map(c=>({text:c.innerText.trim().replace(/\s+/g,' ') || c.textContent.trim().replace(/\s+/g,' '),
   urls:[...(c.matches('a[href]')?[c]:[]),...c.querySelectorAll('a[href]')].map(a=>a.href).filter(u=>/^https?:\/\//i.test(u))}));
 const events=e=>[e,...e.querySelectorAll('*')].some(n=>[...n.attributes].some(a=>/^on/i.test(a.name)));
 const source=document.getElementById(scope.id);
 if(!source || visible(source))throw Error('隐藏预载结构已改变');
 const lists=[...source.parentElement.children].filter(e=>e!==source && e.id && visible(e) && e.children.length &&
   [...e.children].every(c=>scope.classes.every(k=>c.classList.contains(k))));
 if(lists.length!==1)throw Error('可见名单容器不唯一');
 const list=lists[0];
 if([...list.children].some(e=>!visible(e)))throw Error('可见名单内存在隐藏条目');
 if([...list.querySelectorAll('a[href]')].some(a=>/^https?:/i.test(a.href)&&!visible(a)))
   throw Error('可见名单内存在隐藏HTTP链接');
 const pagers=[...document.querySelectorAll('.pb_sys_common')].filter(visible);
 if(pagers.length!==1)throw Error('客户端分页容器不唯一');
 const pager=pagers[0];
 if(events(pager) || [...(function*(e){while(e){yield e;e=e.parentElement}})(pager.parentElement)]
   .some(e=>[...e.attributes].some(a=>/^on/i.test(a.name))))throw Error('分页控件含额外内联事件');
 const current=[...pager.querySelectorAll('.p_no_d')].map(e=>e.textContent.trim());
 if(current.length!==1 || !/^\d+$/.test(current[0]))throw Error('当前页不唯一');
 const links=[...pager.querySelectorAll('a')];
 if(links.some(a=>!/^javascript:(;|void\(0\);?)$/i.test(a.getAttribute('href')||'') || !/^\d+$/.test(a.dataset.page||'')))
   throw Error('分页含未知脚本或非原生data-page目标');
 const next=[...pager.querySelectorAll('a')].filter(a=>['下页','下一页','Next','next'].includes(a.textContent.trim()));
 const last=[...pager.querySelectorAll('a')].filter(a=>['尾页','末页'].includes(a.textContent.trim()));
 const disabled=label=>[...pager.querySelectorAll('span')].filter(e=>label.includes(e.textContent.trim()) &&
   !e.querySelector('a') && (e.classList.contains('p_fun_d') || e.getAttribute('aria-disabled')==='true')).length===1;
 const declared=[...pager.querySelectorAll('*')].map(e=>e.textContent.trim()).filter(t=>/^\d+\s*\/\s*\d+$/.test(t));
 return {source:entries(source),entries:entries(list),list_id:list.id,current:+current[0],
   next:next.map(a=>+a.dataset.page),last:last.map(a=>+a.dataset.page),
   terminal:disabled(['下页','下一页','Next','next'])&&disabled(['尾页','末页']),
   targets:links.map(a=>+a.dataset.page),declared:[...new Set(declared)],url:location.href};
}'''


async def observe(fetcher, task, scopes, expected_urls, should_cancel=None, reference_sha256=None):
    """Observe a finite client pager, saving every page and all rejected traffic."""
    proof = {'complete': False, 'pages': [], 'blocked_requests': [], 'issues': [],
             'requested_url': task['roster_url'], 'max_pages': MAX_PAGES, 'max_seconds': MAX_SECONDS,
             'selected_html_sha256':reference_sha256, 'selected_urls':sorted(expected_urls)}
    page, context = None, None
    started = time.monotonic()
    def cancelled():
        if should_cancel and should_cancel():
            raise InterruptedError('任务已停止；原表和已取得证据保留')
    try:
        async with asyncio.timeout(MAX_SECONDS):
            cancelled()
            await fetcher.start_browser()
            # Isolated context: a pager must never open a teacher/new tab or issue a
            # document/XHR/fetch request before the check discovers the side effect.
            context = await fetcher.browser.new_context(service_workers='block')
            initial = True
            async def guard(route):
                nonlocal initial
                req = route.request
                if req.url in expected_urls or req.resource_type in {'document','xhr','fetch'}:
                    if initial and req.resource_type == 'document' and req.url == task['roster_url']:
                        initial = False
                        await route.continue_()
                    else:
                        proof['blocked_requests'].append({'url':req.url,'type':req.resource_type})
                        await route.abort()
                else:
                    await route.continue_()
            await context.route('**/*', guard)
            page = await context.new_page()
            response = await page.goto(task['roster_url'], wait_until='domcontentloaded', timeout=15000)
            if not response or response.status >= 400:
                raise ValueError('客户端分页来源访问失败')
            await page.wait_for_timeout(350)
            initial_meta = {'method':'客户端分页观察','requested_url':task['roster_url'],
                            'final_url':page.url,'status':response.status}
            fetcher.save(task['id'], 'client-initial', await page.content(), initial_meta)
            proof['initial'] = initial_meta
            matches = []
            for scope in scopes:
                try:
                    state = await page.evaluate(SNAPSHOT, scope)
                    if multiset(state['source']) == multiset(scope['entries']):
                        matches.append((scope, state))
                except Exception:
                    continue
            if len(matches) != 1:
                raise ValueError('模型选择与隐藏预载、可见名单结构无法唯一关联')
            scope, state = matches[0]
            proof['scope'] = scope
            total = state['last'][0] if len(state['last']) == 1 else None
            if state['current'] != 1 or not total or total < 2 or total > MAX_PAGES:
                raise ValueError('分页首末页或上限无法确认')
            combined, seen, list_id = [], set(), state['list_id']
            for number in range(1, total + 1):
                cancelled()
                if time.monotonic() - started > MAX_SECONDS:
                    raise ValueError('客户端分页达到时间上限')
                html = await page.content()
                meta = {'method':'客户端分页观察','requested_url':task['roster_url'], 'final_url':page.url,
                        'page':number,'status':response.status}
                fetcher.save(task['id'], 'client-page-'+str(number), html, meta)
                proof['pages'].append({**state, **meta})
                if proof['blocked_requests']:
                    raise ValueError('客户端分页产生额外document/xhr/fetch请求，已拦截')
                if (urldefrag(page.url)[0] != urldefrag(task['roster_url'])[0] or state['current'] != number
                        or state['list_id'] != list_id or multiset(state['source']) != multiset(scope['entries'])):
                    raise ValueError('客户端分页范围、页码或预载内容变化')
                if state['declared'] and any(tuple(map(int, s.split('/'))) != (number,total) for s in state['declared']):
                    raise ValueError('客户端分页声明相互矛盾')
                signature = json.dumps(state['entries'],sort_keys=True,ensure_ascii=False)
                if not state['entries'] or signature in seen or any(n < 1 or n > total for n in state['targets']):
                    raise ValueError('客户端分页空页、循环或页码越界')
                seen.add(signature)
                combined.extend(state['entries'])
                if number == total:
                    if not state['terminal'] or state['next'] or state['last']:
                        raise ValueError('客户端分页缺少明确末页终止证据')
                    break
                if state['next'] != [number + 1] or state['last'] != [total]:
                    raise ValueError('客户端分页下一页或尾页不一致')
                cancelled()
                await page.locator('.pb_sys_common a').filter(has_text=re.compile(r'^(下页|下一页|Next|next)$')).click(timeout=2000)
                await page.wait_for_timeout(250)
                state = await page.evaluate(SNAPSHOT, scope)
            if multiset(combined) != multiset(scope['entries']):
                raise ValueError('实际各页与所选预载的条目多重集不一致')
            urls = {u for entry in combined for u in entry['urls']}
            if urls != set(expected_urls):
                raise ValueError('实际分页URL集合与两路名单选择不一致')
            proof.update(complete=True, total=total, entry_count=len(combined), urls=sorted(urls))
    except InterruptedError:
        proof['issues'].append('任务已停止；客户端分页未完成')
        raise
    except TimeoutError:
        proof['issues'].append('客户端分页达到时间上限')
    except Exception as exc:
        proof['issues'].append(str(exc) if isinstance(exc,ValueError) else '客户端分页观察失败：'+type(exc).__name__)
    finally:
        proof['elapsed_seconds'] = round(time.monotonic()-started,3)
        write_json(fetcher.out/'evidence'/task['id']/'client-pagination.json', proof)
        if context:
            await context.close()
    return proof
