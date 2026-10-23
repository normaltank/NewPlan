"""Exploratory collection of four observed FYNU faculty branches; no production writes."""
import asyncio
import hashlib
import json
import re
import shutil
import time
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from crawl4ai import JsonCssExtractionStrategy
from benchmark import ROOT, extract_variants, new_run, write_json
from fynu_probe import ENTRY, make_crawler, save_page

DISCOVERY = ROOT / 'runs/20261014-090543-916063-fynu-discovery'
PROFILE_PROBE = ROOT / 'runs/20261014-090631-383496-fynu-discovery'
PDF_SOURCE = ROOT / 'runs/20261014-fynu-pdf'
SEEDS = {
    'https://www.fynu.edu.cn/hxycl/szdw/jstd.htm': '教授团队',
    'https://www.fynu.edu.cn/hxycl/szdw/sssds.htm': '硕士生导师',
    'https://www.fynu.edu.cn/hxycl/szdw/bstd.htm': '博士团队',
    'https://www.fynu.edu.cn/hxycl/szdw/jsdw.htm': '教师队伍',
}
AGGREGATE = 'https://www.fynu.edu.cn/hxycl/info/1049/7692.htm'
PERSON = re.compile(r'^[\u4e00-\u9fff·]{2,8}$')


def normal_name(value):
    value = re.sub(r'^硕士生导师[—－\-：:\s]*', '', value)
    return re.sub(r'\s+', '', value).strip()


def profile_body(soup):
    for selector in ['.v_news_content', 'div#vsb_content', 'div#vsb_content_4']:
        body = soup.select_one(selector)
        if body:
            return body, selector
    return None, None


async def main():
    started = time.perf_counter()
    out = new_run('fynu-collection')
    print(f'RUN_DIR={out}', flush=True)
    code = out / 'code'
    code.mkdir()
    for name in ['fynu_collect.py','fynu_probe.py','benchmark.py','requirements.lock']:
        shutil.copyfile(ROOT/name, code/name)
    cache = {}
    for directory in [DISCOVERY, PROFILE_PROBE]:
        for page in json.loads((directory/'pages.json').read_text(encoding='utf-8')):
            cache[page['url']] = (directory, page)
    for url in [ENTRY, 'https://www.fynu.edu.cn/hxycl/xy/fzyg.htm']:
        old, page = cache[url]
        shutil.copytree(old/page['directory'], out/page['directory'])
    shutil.copytree(PDF_SOURCE, out/'doctor-pdf')
    text = (PDF_SOURCE/'pdf-text.txt').read_text(encoding='utf-8')
    lines = text.splitlines()
    name_text = ''.join(line for line in lines if '博士名单' not in line and not line.startswith('*'))
    pdf_names = [normal_name(part) for part in name_text.split('、') if part.strip()]
    if len(pdf_names) != 113 or not all(PERSON.fullmatch(name) for name in pdf_names):
        raise ValueError('PDF text segmentation differs from the visually reviewed 113-name reference')

    observations = [{'name': name, 'label':name, 'profile_url': '', 'source_url':AGGREGATE,
                     'branch':'博士总名单PDF', 'source_kind':'pdf_name', 'ordinal':i+1,
                     'source_location':f'PDF page 1, name {i+1}',
                     'reference_date':'2025-09', 'degree':'博士'} for i,name in enumerate(pdf_names)]
    targets = {url:{'kind':'roster','branch':branch} for url,branch in SEEDS.items()}
    pending = deque(SEEDS)
    scheduled = set()
    processed = set()
    pages, failures, skipped, unresolved, roster_pages = [], [], [], [], []

    def register(url, kind, branch):
        if not url.startswith(('http://','https://')) or urlparse(url).netloc != 'www.fynu.edu.cn':
            unresolved.append({'kind':'external_or_unsupported_link','url':url,'branch':branch})
            return
        if url not in targets:
            if len(targets) >= 300:
                unresolved.append({'kind':'request_cap','url':url})
                return
            targets[url] = {'kind':kind,'branch':branch}
            pending.append(url)

    def persist():
        # Atomic replacement allows status readers to inspect files while collection continues.
        for name, data in [('pages',pages),('observations',observations),('failures',failures),
                           ('roster-pages',roster_pages),('unresolved',unresolved)]:
            temporary = out/f'{name}.json.tmp'
            write_json(temporary,data)
            temporary.replace(out/f'{name}.json')

    def consume(item, soup):
        url = item['url']
        target = targets[url]
        item.update(target)
        folder = out/item['directory']
        body, selector = profile_body(soup)
        if body:
            (folder/'body.html').write_text(str(body),encoding='utf-8')
            (folder/'body-text.txt').write_text(body.get_text('\n',strip=True),encoding='utf-8')
            item['body_selector'] = selector
            item['body_chars'] = len(body.get_text('\n',strip=True))
            item['body_images'] = [urljoin(item['loaded_url'],a['src']) for a in body.select('img[src]')]
        if target['kind']=='roster':
            if target['branch']=='教授团队':
                if not body:
                    unresolved.append({'kind':'missing_rich_roster_body','url':url})
                else:
                    links = {normal_name(a.get_text('',strip=False)):urljoin(url,a['href'])
                             for a in body.select('a[href]')}
                    ordinal = 0
                    for paragraph in body.find_all('p',recursive=False):
                        raw = paragraph.get_text('',strip=False).strip()
                        if '教授名单' in raw:
                            continue
                        for token in re.split(r'\s{2,}',raw):
                            if not token.strip():
                                continue
                            label = re.sub(r'\s+','',token)
                            name = re.sub(r'（[^）]*）','',label)
                            if not PERSON.fullmatch(name):
                                unresolved.append({'kind':'unparsed_rich_roster_token','url':url,'text':token})
                                continue
                            ordinal += 1
                            link = links.get(name,'')
                            observations.append({'name':name,'label':label,'profile_url':link,'source_url':url,
                                                 'branch':target['branch'],'source_kind':'rich_roster','ordinal':ordinal,
                                                 'title_from_roster':'正高级实验师' if '正高级实验师' in label else '教授'})
                            if link:
                                register(link,'profile',target['branch'])
                    roster_pages.append({'url':url,'branch':target['branch'],'entries':ordinal,'next':[],
                                         'reference_total':None,'terminal':'single rich-text roster'})
            else:
                schema={'name':'FYNU article directory','baseSelector':'div.new_list3 dl dd',
                        'fields':[{'name':'label','selector':'a.fl','type':'text'},
                                  {'name':'href','selector':'a.fl','type':'attribute','attribute':'href'}]}
                rows=JsonCssExtractionStrategy(schema).extract(url,str(soup))
                for ordinal,row in enumerate(rows,1):
                    label=row.get('label','')
                    link=urljoin(item['loaded_url'],row.get('href',''))
                    if '博士名单' in label:
                        register(link,'aggregate',target['branch'])
                    else:
                        name=normal_name(label)
                        if not PERSON.fullmatch(name):
                            unresolved.append({'kind':'unclassified_directory_entry','url':url,'label':label,'link':link})
                        else:
                            observations.append({'name':name,'label':label,'profile_url':link,'source_url':url,
                                                 'branch':target['branch'],'source_kind':'directory_link','ordinal':ordinal})
                            register(link,'profile',target['branch'])
                pager = soup.select_one('.container_right .headStyle3d6zvt2iek')
                # VSBuilder's pager class varies; restrict fallback to table carrying its page controls.
                if not pager:
                    pager = next((t for t in soup.select('.container_right table') if t.select('a.Next,span.PrevDisabled,span.NextDisabled')),None)
                pager_text = pager.get_text(' ',strip=True) if pager else ''
                next_links=[urljoin(item['loaded_url'],a['href']) for a in soup.select('.container_right a.Next[href]')
                            if a.get_text(strip=True)=='下页']
                for next_url in next_links:
                    register(next_url,'roster',target['branch'])
                total=re.search(r'共\s*(\d+)\s*条',pager_text)
                roster_pages.append({'url':url,'branch':target['branch'],'entries':len(rows),'next':next_links,
                                     'pager_text':pager_text,'reference_total':int(total[1]) if total else None,
                                     'terminal':bool(pager and not next_links)})
        elif target['kind']=='profile':
            if not body:
                unresolved.append({'kind':'profile_body_missing','url':url})
            text=body.get_text(' ',strip=True) if body else ''
            item['email_candidates'] = sorted(set(re.findall(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}',text)))
            item['title_candidates'] = sorted(set(re.findall(r'正高级实验师|高级实验师|副教授|教授|讲师|助教|研究员|副研究员|实验师',text[:500])))
            item['candidate_scope']='Heuristic candidates from saved personal body; not adjudicated fields'
            for engine,result in extract_variants(str(soup),item['loaded_url']).items():
                (folder/f'{engine}.txt').write_text(result['text'],encoding='utf-8')
                item[engine]={k:v for k,v in result.items() if k!='text'}
        elif target['kind']=='aggregate':
            item['attached_pdf']='doctor-pdf/doctor-roster.pdf'
        pages.append(item)
        processed.add(url)
        persist()

    # Reuse immutable probe bytes, retaining their original retrieval times and hashes.
    network=[]
    while pending:
        url=pending.popleft()
        if url in processed:
            continue
        if url in cache:
            old,item=cache[url]
            item=dict(item)
            item['reused_from']=str(old)
            shutil.copytree(old/item['directory'],out/item['directory'])
            consume(item,BeautifulSoup((out/item['directory']/'source.html').read_bytes(),'lxml'))
        else:
            network.append(url)
            scheduled.add(url)

    crawler=await make_crawler(out,300)

    @crawler.pre_navigation_hook
    async def pace(context):
        await asyncio.sleep(2)

    @crawler.router.default_handler
    async def handle(context):
        item=await save_page(context,out)
        consume(item,context.soup)
        requests=[]
        while pending:
            link=pending.popleft()
            if link not in processed and link not in scheduled:
                scheduled.add(link)
                requests.append(link)
        if requests:
            await crawler.add_requests(requests)
        print(f"{item['kind']} {len(pages)}: {item['title']} / body {item.get('body_chars',0)}",flush=True)

    @crawler.failed_request_handler
    async def failure(context,error):
        failures.append({'url':context.request.url,'retry_count':context.request.retry_count,'error':str(error)})
        persist()

    @crawler.on_skipped_request
    async def skip(url,reason):
        skipped.append({'url':str(url),'reason':str(reason)})
        write_json(out/'skipped.json',skipped)

    await crawler.run(network)
    summary={'pages':len(pages),'profiles':sum(p['kind']=='profile' for p in pages),
             'roster_pages':len(roster_pages),'observations':len(observations),
             'distinct_normalized_names':len({o['name'] for o in observations}),
             'failures':failures,'skipped':skipped,'unresolved':unresolved,
             'targets_not_saved':sorted(set(targets)-processed),
             'seconds':round(time.perf_counter()-started,2),
             'scope':'Four homepage faculty branches, linked pagination/profiles, and doctor PDF',
             'whole_college_completeness':'unverified','llm_extraction_calls':0}
    write_json(out/'summary.json',summary)
    write_json(out/'targets.json',targets)
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':
    asyncio.run(main())
