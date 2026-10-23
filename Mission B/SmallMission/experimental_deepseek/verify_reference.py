"""Separate, explicitly reviewed XPath recount for six structural cases.

These expressions are evidence-specific reference checks, never supplied to
DeepSeek or used by experiment.py. They do not certify other schools.
"""
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
from collections import Counter
import hashlib
import json
from lxml import html as LH

HERE = Path(__file__).resolve().parent
BASELINE = HERE.parent/'outputs'/'verified-support-v2.3-20261015'
RUN = HERE/'runs'/'snapshot-v1'


def cls(name):
    return "contains(concat(' ',normalize-space(@class),' '),' " + name + " ')"


RULES = {
    '延安大学': '//div['+cls('inner_s6')+']//div['+cls('list')+']/ul/li/a[@href]',
    '湖南大学': '//ul['+cls('name-list')+']/li/a[@href]',
    '沈阳航空航天大学': '//div['+cls('people-list')+']/ul/li/a[@href]',
    '山东理工大学': '//div[@id="teacher_list_block_list"]/ul/li/a[@href]',
    '西安财经大学': '//div['+cls('main_conR')+']//ul/li//a[@href]',
    '青海师范大学': '//table['+cls('MsoNormalTable')+']//td//a[@href]',
}


def normalize(href, base):
    if not href.strip() or href.strip()=='#':return None
    p=urlsplit(urljoin(base,href.strip()))
    if p.scheme not in ('http','https') or not p.hostname:return None
    return urlunsplit((p.scheme,p.netloc.lower(),p.path or '/',p.query,p.fragment))


def run():
    old=json.loads((BASELINE/'results.json').read_text('utf-8'))
    new={r['id']:r for r in json.loads((RUN/'results.json').read_text('utf-8'))}
    checks=[]
    for r in old:
        if r['school'] not in RULES:continue
        all_urls=set();sources=[]
        for source in r['sources']:
            meta=source['attempts'][-1]
            raw=(BASELINE/meta['html_path']).read_bytes()
            assert hashlib.sha256(raw).hexdigest()==meta['html_sha256']
            tree=LH.fromstring(raw.decode('utf-8'))
            anchors=tree.xpath(RULES[r['school']])
            urls=[normalize(a.get('href'),meta.get('final_url') or source['roster_url']) for a in anchors
                  if ''.join(a.itertext()).strip() or a.xpath('.//img|.//svg')]
            urls=[u for u in urls if u]
            all_urls.update(urls)
            sources.append({'url':source['roster_url'],'occurrences':len(urls),'unique':len(set(urls)),
                            'html_sha256':meta['html_sha256'],'xpath':RULES[r['school']],
                            'anchors':[{'label':''.join(a.itertext()).strip(),'href':a.get('href')} for a in anchors]})
        candidate=set(new[r['id']]['links'])
        checks.append({'school':r['school'],'college':r['college'],'reference_count':len(all_urls),
                       'candidate_count':len(candidate),'missing':sorted(all_urls-candidate),
                       'extra':sorted(candidate-all_urls),'passed':all_urls==candidate,'sources':sources})
    # Minimal no-model change on the same saved pages, to avoid attributing the
    # known pagination fix to AI when a DOM exclusion can do it as well.
    from bs4 import BeautifulSoup
    ablation=[]
    for r in old:
        if not r['complete']:continue
        actual=set()
        for s in r['sources']:
            meta=s['attempts'][-1]
            soup=BeautifulSoup((BASELINE/meta['html_path']).read_bytes(),'lxml')
            pager_nodes={id(a) for container in soup.select('.pb_sys_common,.wp_paging,#wp_pager') for a in container.select('a[href]')}
            for root in soup.select(s['plan']['selector']):
                for a in root.select('a[href]'):
                    if id(a) in pager_nodes or (not a.get_text(strip=True) and not a.select('img,svg')):continue
                    target=normalize(a['href'],meta.get('final_url') or s['roster_url'])
                    if target:actual.add(target)
        candidate=set(new[r['id']]['links'])
        ablation.append({'school':r['school'],'college':r['college'],'rules_plus_pager_exclusion':len(actual),
                         'model_candidate':len(candidate),'same_urls':actual==candidate})
    result={'independent_reference_colleges':len(checks),'independent_reference_pages':sum(len(c['sources']) for c in checks),
            'reference_checks':checks,'rules_ablation':ablation,
            'scope_note':'六学院保存页的人工选定条目结构与独立XPath重数；不是全部20学院的独立真值或实时完整性保证。',
            'reference_not_visible_to_model':True}
    (RUN/'reference-checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'reference':[{k:v for k,v in c.items() if k!='sources'} for c in checks],
                      'rules_ablation':ablation},ensure_ascii=False,indent=2))
    assert all(c['passed'] for c in checks), 'Reference mismatch requires investigation'


if __name__=='__main__':run()
