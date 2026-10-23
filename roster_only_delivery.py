"""Deliver proven roster-only membership without inventing personal pages or CVs."""
import hashlib
import re
from collections import defaultdict
from bs4 import BeautifulSoup
from quality_fields import compact,fields_from_text,profile_label_name
from roster_identity import RosterEvidence,CONTENT,urlkey
from person_names import is_person_name

POLICY='roster-only-delivery-v1'

def apply_roster_only(cat,root,items):
    evidence=RosterEvidence(cat,root).evidence
    groups=defaultdict(list)
    for p in cat['people']:groups[p['name']].append(p)
    proven=defaultdict(list)
    for p in cat['people']:
        item=items[p['id']]
        if p['profile_url'] or item['fields']['biography'] or p['review'].get('revision') or item['status']=='duplicate':continue
        if not is_person_name(p['name']):continue
        # Do not introduce a second person beside an existing profile, or erase
        # ambiguous identity evidence that still needs comparison.
        if any(x['profile_url'] or items[x['id']]['fields']['biography'] for x in groups[p['name']]):continue
        if set(item['anomalies'])-{'尚未取得本人正文'}:continue
        if any(o.get('historical_roster') for o in p['observations']):continue
        proof=evidence(p)
        if not proof:continue
        soup=BeautifulSoup((root/proof['path']).read_text(encoding='utf8'),'html.parser')
        body=soup.select_one(CONTENT)
        if body is None:continue
        named_links=[a for a in body.select('a[href]') if profile_label_name(a.get_text(' ',strip=True))==p['name']
                     and a['href'].strip() and not a['href'].strip().startswith(('#','javascript:','mailto:'))]
        if named_links:continue
        # Only bind additional values when the saved line begins with this name.
        if proof.get('row_text'):
            f=fields_from_text(p['name'],proof['row_text'])
            if f['anomalies']:continue
            for field in ('title','email'):
                if f[field]['value']:
                    item['fields'][field]=f[field]['value']
                    item['selection'][field]={**f[field],'rule':'named_official_roster_row','roster_evidence':proof}
        for field in ('title','email','profile_url','biography'):
            if not item['fields'][field]:item['fields']['missing'][field]='not_stated_in_source'
            else:item['fields']['missing'].pop(field,None)
        message='仅名单信息：正式师资名单已确认身份；本次名单未列个人主页，已知字段可交付，未取得个人简介'
        note={'code':'roster_only','message':message,'roster_evidence':proof}
        item.update(status='auto_accepted',material_status='roster_only',anomalies=[],reason=message,
                    delivery_notes=[note],roster_only_evidence=proof)
        # Aliased roster pages with the same complete visible content are one
        # source, not two distinct identity claims. Name alone is insufficient.
        digest=hashlib.sha256(compact(body.get_text(' ',strip=True)).encode()).hexdigest()
        proof['content_sha256']=digest
        proven[(p['name'],digest)].append(p)
    digests=defaultdict(set)
    for name,digest in proven:digests[name].add(digest)
    for (name,digest),group in proven.items():
        if len(digests[name])>1:
            for p in group:
                item=items[p['id']]
                item.update(status='pending',anomalies=['同名不同名单，身份关联待核'],reason='姓名相同但名单内容不同，需核实是否同一人')
            continue
        primary=group[0]
        for p in group[1:]:
            item=items[p['id']]
            item.update(status='duplicate',canonical_id=primary['id'],reason='同一完整名单内容的重复观察，已关联保留条目')
            items[primary['id']].setdefault('roster_associations',[]).append({'person_id':p['id'],'policy':POLICY,'roster':item['roster_only_evidence']})
