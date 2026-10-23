"""Separate unread materials from deliverability; select dated personal versions.

All choices use saved evidence. No network requests, URL rewriting, or human
decisions are made here. Material dates are never inferred from URL/crawl dates.
"""
import hashlib
import re
from person_names import is_person_name
from collections import defaultdict
from datetime import date, datetime
from difflib import SequenceMatcher
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from quality_fields import compact, fields_from_text
from roster_identity import RosterEvidence, urlkey

POLICY = 'material-delivery-v1'
IDENTITY_ANOMALY = '同名不同材料，需要核对身份或新旧版本'
READ_FAILURES = {'request_failed','browser_render_failed','processing_failed','profile_structure_mismatch','profile_without_text'}
ATTACHMENT_FAILURES = {'image_ocr_failed','image_limit','profile_pdf_failed'}
UNVISITED = {'out_of_host_scope','page_limit'}


def article_key(url):
    parsed = urlparse(url or '')
    match = re.fullmatch(r'/(?:_s\d+/|_t\d+/)?\d{4}/\d{4}/c\d+a(\d+)/page\.(?:htm|psp)', parsed.path)
    return (parsed.hostname, match[1]) if match else None


def page_date(root, page):
    if not page or not page.get('directory'):
        return None
    path = root/page['directory']/'source.html'
    if not path.is_file():
        return None
    raw = path.read_bytes(); soup = BeautifulSoup(raw.decode('utf8', errors='replace'), 'html.parser')
    choices = []
    for node in soup.select('.arti_update,.publish_date,.publish-time,.pubtime,.news-time,.in-det > .in-det-bt > p,.title > .tit_attr,time[datetime],meta[property="article:published_time"],meta[property="article:modified_time"],meta[name="pubdate"],meta[name="publishdate"]'):
        if node.find_parent(class_=re.compile(r'wp_articlecontent|v_news_content|article-content|entry-content')):
            continue
        value = node.get('content') or node.get('datetime') or node.get_text(' ', strip=True)
        if 'tit_attr' in node.get('class',[]) and not re.match(r'发布(?:日期|时间)[:：]|更新(?:日期|时间)[:：]',compact(value)):continue
        if len(value) > 160:
            continue
        for m in re.finditer(r'(?<!\d)(20\d{2}|19\d{2})\s*[年./-]\s*(\d{1,2})\s*[月./-]\s*(\d{1,2})(?!\d)', value):
            try:
                day = date(*map(int, m.groups()))
            except ValueError:
                continue
            captured = (page.get('retrieved_at') or '')[:10]
            limit = date.fromisoformat(captured) if re.fullmatch(r'\d{4}-\d{2}-\d{2}', captured) else date.today()
            if day > limit:
                continue
            updated = bool(re.search(r'更新|修改|modified', value+' '+str(node.get('property','')), re.I))
            choices.append({'date': day.isoformat(), 'kind': 'updated' if updated else 'published',
                            'quote': value, 'path': str(path.relative_to(root)), 'sha256': hashlib.sha256(raw).hexdigest()})
    pool = [c for c in choices if c['kind']=='updated'] or choices
    if len({c['date'] for c in pool}) != 1:
        return None
    return pool[0]


def apply_delivery(cat, root, items):
    people = {p['id']:p for p in cat['people']}
    pages = {urlkey(p['url']):p for p in cat['pages']}
    roster = RosterEvidence(cat, root)
    qualified = {}
    def proof(p):
        if p['id'] not in qualified:
            qualified[p['id']] = roster.evidence(p, profile_link=True) if p['profile_url'] else None
        return qualified[p['id']]
    def mails(p):
        return {e.strip().lower() for e in items[p['id']]['fields']['email'].split(';') if e.strip()}
    owners = defaultdict(set)
    for p in people.values():
        for mail in mails(p):
            owners[mail].add(p['name'])
    groups = defaultdict(list)
    for p in people.values():
        if p['profile_url'] and items[p['id']]['status'] != 'duplicate':
            groups[p['name']].append(p)
    for name, group in groups.items():
        if len(group) < 2 or any(p['review'].get('revision') for p in group):
            continue
        parent = {p['id']:p['id'] for p in group}; matches = []
        def find(key):
            while parent[key] != key:
                key = parent[key]
            return key
        for i, left in enumerate(group):
            if not proof(left):
                continue
            for right in group[i+1:]:
                if not proof(right):
                    continue
                rule = None; value = None
                lk = article_key(left['profile_url']); rk = article_key(right['profile_url'])
                shared = sorted(e for e in mails(left)&mails(right) if len(owners[e]) == 1)
                a = compact(items[left['id']]['fields']['biography'])[:1200]
                b = compact(items[right['id']]['fields']['biography'])[:1200]
                if lk and lk == rk:
                    rule = 'same_official_cms_article'; value = list(lk)
                elif shared:
                    rule = 'same_personal_email'; value = shared
                elif name in a[:400] and name in b[:400]:
                    match = SequenceMatcher(None,a,b,autojunk=False).find_longest_match()
                    if match.size >= 100:
                        rule = 'shared_personal_biography'; value = a[match.a:match.a+match.size]
                if rule:
                    parent[find(right['id'])] = find(left['id'])
                    matches.append({'left':left['id'],'right':right['id'],'rule':rule,'value':value})
        components = defaultdict(list)
        for p in group:
            components[find(p['id'])].append(p)
        for component in components.values():
            if len(component) < 2:
                continue
            ids = {p['id'] for p in component}
            dates = {p['id']:page_date(root,pages.get(urlkey(p['profile_url']))) for p in component}
            bodies = {compact(items[p['id']]['fields']['biography']) for p in component} - {''}
            aliases = len({article_key(p['profile_url']) for p in component}) == 1 and article_key(component[0]['profile_url'])
            if aliases and len(bodies) <= 1:
                chosen = sorted(component,key=lambda p:(-len(items[p['id']]['fields']['biography']), '/_' in p['profile_url'], p['id']))[0]
                rule = 'same_article_alias'; message = '同一官方文章的不同模板链接，已自动关联，原链接均保留'
            elif all(dates.values()) and len({d['date'] for d in dates.values()}) > 1:
                latest = max(d['date'] for d in dates.values())
                newest = [p for p in component if dates[p['id']]['date'] == latest]
                if len(newest) != 1 or not items[newest[0]['id']]['fields']['biography']:
                    continue
                chosen = newest[0]; rule = 'latest_dated_material'
                message = '存在同名不同材料，已自动选择最新版材料（网页标注日期：'+latest+'）'
            else:
                # Date ties and missing dates do not establish which CV is new.
                reason = '各材料日期相同，无法判断新旧' if all(dates.values()) else '部分材料没有可核实的网页日期，无法自动判断新旧'
                for p in component:
                    items[p['id']]['version_review'] = {'reason':reason,'dates':dates}
                continue
            selected = items[chosen['id']]
            identity = [m for m in matches if m['left'] in ids and m['right'] in ids]
            versions = {'policy':POLICY,'rule':rule,'message':message,'selected_id':chosen['id'],
                        'identity_evidence':identity,'materials':[{'person_id':p['id'],'url':p['profile_url'],
                          'date':dates[p['id']],'body_path':p.get('body_path',''),'body_sha256':items[p['id']]['body_sha256']} for p in component]}
            selected['material_versions'] = versions
            selected.setdefault('delivery_notes',[]).append({'code':rule,'message':message})
            selected['anomalies'] = [a for a in selected['anomalies'] if a != IDENTITY_ANOMALY]
            selected['status'] = 'pending' if selected['anomalies'] else 'auto_accepted'
            for p in component:
                if p['id'] == chosen['id']:
                    continue
                items[p['id']].update(status='duplicate',canonical_id=chosen['id'],anomalies=[],reason=message,material_versions=versions)
                # Flatten prior exact-body duplicates, avoiding stale chains.
                for other in items.values():
                    if other.get('canonical_id') == p['id']:
                        other['canonical_id'] = chosen['id']
    deferred = defaultdict(list)
    for p in people.values():
        item = items[p['id']]
        if item['status'] == 'duplicate' or p['review'].get('revision'):
            continue
        if not is_person_name(p['name']) or not proof(p):
            continue
        card_only=pages.get(urlkey(p['profile_url']),{}).get('body_status')=='card_only'
        non_blocking={'尚未取得本人正文','本人材料仍有附件或页面读取失败'}
        if card_only:non_blocking.add('正文过短，可能遗漏')
        blockers = [a for a in item['anomalies'] if a not in non_blocking]
        if blockers:
            continue
        text = item['fields']['biography']
        failures = [i for i in cat['issues'] if urlkey(i.get('source_page') or i.get('url')) == urlkey(p['profile_url'])
                    and i['issue_kind'] in READ_FAILURES|ATTACHMENT_FAILURES|UNVISITED
                    and items.get(i['id'],{}).get('status') != 'resolved']
        queued=bool(p['profile_url'] and p['profile_url'] in cat.get('summary',{}).get('pending_urls',[]))
        if not failures and not queued and not card_only:
            continue
        if card_only:
            code='profile_card_only';message='仅取得本人标题或信息卡；名单身份与已知字段可交付，尚未取得个人简介'
            item['fields']['biography']='';text=''
        elif not text and any(i['issue_kind']=='out_of_host_scope' for i in failures):
            code = 'profile_not_visited'; message = '跨站页面未采集；正式名单已确认身份，未读取字段待补采，不代表官网没有正文'
        elif not text and (queued or any(i['issue_kind']=='page_limit' for i in failures)):
            code = 'profile_queued'; message = '主页尚未采集，已列入待续采队列；正式名单中的已知字段可交付'
        elif not text and any(i['issue_kind']=='request_failed' and urlkey(i['url']) == urlkey(p['profile_url']) for i in failures):
            code = 'profile_access_failed'; message = '主页访问失败；官方师资名单已确认身份，已知字段可交付，简介等未读取字段待补采'
        elif not text:
            code = 'profile_content_unread'; message = '本次读取未提取到正文；已知字段可交付，未读取字段待补采，不代表官网没有正文'
        else:
            code = 'attachment_access_failed'; message = '部分附件读取失败；已取得的本人正文和字段可交付，缺失附件仍待补采'
        if not text and proof(p).get('row_text'):
            row = fields_from_text(p['name'], compact(proof(p)['row_text']))
            if not row['anomalies']:
                for field in ('title','email'):
                    if not item['fields'][field] and row[field]['value']:
                        # Do not import any shared/public roster email.
                        if field == 'email' and any(len(owners[e.strip().lower()]) > 1 for e in row[field]['value'].split(';')):
                            continue
                        item['fields'][field] = row[field]['value']
                        item['fields']['missing'].pop(field,None)
                        item['selection'][field] = {**row[field],'rule':'qualified_roster_person_row','source':proof(p)}
        note = {'code':code,'message':message,'url':p['profile_url'],'issue_ids':[i['id'] for i in failures],'roster_evidence':proof(p)}
        for field in ('title','email','biography'):
            if not item['fields'][field]:
                item['fields']['missing'][field] = 'access_failed' if code=='profile_access_failed' else 'not_read'
        item.setdefault('delivery_notes',[]).append(note)
        item['material_status'] = code
        item['status'] = 'auto_accepted'; item['anomalies'] = []
        item['reason'] = message
        for issue in failures:
            deferred[issue['id']].append(p['id'])
    for key, person_ids in deferred.items():
        items[key] = {'status':'deferred','actor':'自动规则 '+POLICY,'policy':POLICY,'automatic':True,
                      'reason':'未取得材料已单独登记待补采，不阻挡已确认人员交付；未标为读取成功',
                      'person_ids':person_ids,'evidence':'\n'.join(people[x]['profile_url'] for x in person_ids)}
    # Failed alternative URLs for the same CMS article are one follow-up, not
    # another human identity decision. Failure is retained, never called success.
    for p in people.values():
        item = items[p['id']]
        if item['status'] != 'duplicate' or item.get('material_versions',{}).get('rule') != 'same_article_alias':
            continue
        canonical = items.get(item.get('canonical_id'),{})
        if canonical.get('status') != 'auto_accepted':
            continue
        for issue in cat['issues']:
            if issue['issue_kind'] in READ_FAILURES and urlkey(issue.get('url')) == urlkey(p['profile_url']):
                items[issue['id']] = {'status':'deferred','actor':'自动规则 '+POLICY,'policy':POLICY,'automatic':True,
                                     'reason':'同一教师的备用模板链接访问失败，已关联到保留记录；不影响已确认信息交付',
                                     'person_ids':[item['canonical_id']],'evidence':p['profile_url']}
    for item in items.values():
        if item.get('material_versions') and item['status'] == 'auto_accepted' and not item.get('material_status'):
            item['reason'] = item['material_versions']['message']
