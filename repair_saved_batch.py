"""Replay saved pages and fetch only newly evidenced personal URLs; preserve originals."""
import asyncio
import hashlib
import json
import re
import shutil
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup
from api_pilot import Pilot, title_name, page_links
from quality_fields import compact, profile_card, TITLE
from quality_pipeline import build
from workbench_store import Store, ROOT, read_json, now


class NoModel:
    async def ask(self,*args,**kwargs):
        raise ValueError('This repair only replays evidenced structures, no unbounded model calls')


async def repair(store,key):
    cat=store.catalog(key,apply_auto=False);job=cat['job']
    if job['state'] in ('queued','running') or not job['run_dir']:return
    root=Path(job['run_dir']);target=job['target'];host=urlparse(target['url']).netloc
    if (root/'enrichment.json').exists():
        build(store,key);return
    patch={'pages':{},'extra_pages':[],'observations':[],'documents':[],'report':{'created':now(),'repairs':[],'fetch_failures':[]}}
    args=SimpleNamespace(**{k:target[k] for k in ('url','university','college')},max_pages=800,max_images=800,ocr=True,browser=False)
    pilot=Pilot(args,root,NoModel());pilot.profile_selector='.wp_articlecontent';pilot.profile_selectors=['.wp_articlecontent']
    pilot.media=cat['media'][:];pilot.media_cache={m['source_url']:m for m in pilot.media}
    for d in cat['documents']:
        path=root/d['path']/'text.txt'
        if path.exists():pilot.profile_pdf_cache[d['url']]={**d,'text':path.read_text(encoding='utf-8')}
    pages={pilot.canonical_url(p['url']):p for p in cat['pages']}
    observations=read_json(root/'observations.json',[])
    wanted={}
    folder=root/'quality-repair';folder.mkdir(exist_ok=True)
    for page in cat['pages']:
        raw=root/page['directory']/'source.html'
        if not raw.exists():continue
        soup=BeautifulSoup(raw.read_bytes(),'lxml')
        card=profile_card(soup)
        if card and page.get('body_chars'):
            text=(root/page['directory']/'body-text.txt').read_text(encoding='utf-8')
            if compact(card) not in compact(text):
                dest=folder/(page['directory'].replace('/','-')+'-body.txt')
                dest.write_text(card+'\n\n'+text,encoding='utf-8')
                patch['pages'][page['url']]={'body_path':dest.relative_to(root).as_posix(),'body_chars':len(card)+len(text)+2,'personal_card_included':True}
                patch['report']['repairs'].append({'kind':'personal_card','url':page['url']})
        body=soup.select_one('.wp_articlecontent')
        if body and page['kind']=='roster' and re.search(r'师资|导师|教师',page.get('branch','')+' '+page.get('title','')):
            for link in page_links(body,page['url']):
                name=title_name(link['label']);url=pilot.canonical_url(link['url'])
                if name and urlparse(url).netloc==host and not url.endswith(('main.htm','list.htm')):
                    if not any(o['name']==name and pilot.canonical_url(o.get('profile_url',''))==url and o['source_url']==page['url'] for o in observations):
                        patch['observations'].append({'name':name,'profile_url':url,'source_url':page['url'],'branch':page.get('branch',''),
                                                      'source_kind':'saved_roster_anchor','evidence':link['label']})
                    if url not in pages or not pages[url].get('body_chars'):wanted[url]=name
        # Explicit table header is a stronger ownership anchor than a model-generated quote.
        if body and page['kind']=='document' and re.search(r'教师|教练|师资|导师',page.get('title','')):
            for ti,table in enumerate(body.select('table')):
                rows=table.select('tr')
                if not rows:continue
                header=[compact(x.get_text()) for x in rows[0].select('td,th')]
                if '姓名' not in header or '职称' not in header:continue
                for ri,row in enumerate(rows[1:]):
                    cells=[x.get_text(' ',strip=True) for x in row.select('td,th')]
                    if len(cells)!=len(header):continue
                    name=title_name(cells[header.index('姓名')])
                    if not name:continue
                    text='\n'.join(k+'：'+v for k,v in zip(header,cells))
                    dest=folder/f'table-{page["directory"]}-{ti}-{ri}.txt';dest.write_text(text,encoding='utf-8')
                    patch['observations'].append({'name':name,'profile_url':'','source_url':page['url'],'branch':page.get('branch',''),
                        'source_kind':'html_table_row','evidence':text,'person_body_path':dest.relative_to(root).as_posix(),
                        'historical_roster':bool(re.search(r'201[0-8]',soup.get_text(' ',strip=True)[-13000:]))})
        if page['kind']=='document' and (name:=title_name(page.get('title',''))) and body:
            # A previously misclassified person title, still reachable from a roster.
            source=next((i['url'] for i in cat['issues'] if i.get('document_url')==page['url']),None)
            if source:
                patch['observations'].append({'name':name,'profile_url':page['url'],'source_url':source,'branch':page.get('branch',''),
                    'source_kind':'recovered_person_title','evidence':page['title']})
                wanted[page['url']]=name
    # Existing missing profiles are retried from saved HTML before making a network request.
    for p in cat['people']:
        url=pilot.canonical_url(p['profile_url'])
        if url and urlparse(url).netloc==host and not p['body_path'] and not url.endswith(('main.htm','list.htm')):
            wanted[url]=p['name']
    for index,(url,name) in enumerate(wanted.items()):
        if index>=50:
            patch['report']['fetch_failures'].append({'url':url,'reason':'bounded repair limit'});continue
        prior=pages.get(url)
        try:
            d=folder/hashlib.sha256(url.encode()).hexdigest()[:16];d.mkdir(exist_ok=True)
            if prior:
                data=(root/prior['directory']/'source.html').read_bytes()
            else:
                async with httpx.AsyncClient(trust_env=False,follow_redirects=False,timeout=40) as client:
                    if pilot.robot is None:
                        response=await client.get(target['url'].rstrip('/')+'/robots.txt')
                        if response.status_code not in (200,404,410):raise ValueError('robots unavailable')
                        pilot.robot=RobotFileParser();pilot.robot.parse(response.text.splitlines() if response.status_code==200 else [])
                    if not pilot.robot.can_fetch('*',url):raise ValueError('robots disallowed')
                    await asyncio.sleep(max(1,pilot.robot.crawl_delay('*') or 0))
                    response=await client.get(url);response.raise_for_status();data=response.content
            (d/'source.html').write_bytes(data)
            soup=BeautifulSoup(data,'lxml')
            if not soup.select_one('.wp_articlecontent'):raise ValueError('no known personal body container')
            page={**(prior or {}),'url':url,'loaded_url':url,'directory':d.relative_to(root).as_posix(),
                  'sha256':hashlib.sha256(data).hexdigest(),'kind':'profile','title':soup.title.get_text(strip=True) if soup.title else '',
                  'branch':'已发现名单链接补读','retrieved_at':now()}
            await pilot.profile(page,soup)
            if prior:patch['pages'][prior['url']]=page
            else:patch['extra_pages'].append(page)
            patch['report']['repairs'].append({'kind':'profile_body','url':url,'body_chars':page.get('body_chars',0),'name':name})
        except Exception as exc:
            patch['report']['fetch_failures'].append({'url':url,'name':name,'reason':str(exc)[:150]})
    patch['documents']=pilot.documents
    patch['media']=pilot.media[len(cat['media']):]
    patch['issues']=pilot.issues
    (root/'enrichment.json').write_text(json.dumps(patch,ensure_ascii=False,indent=2),encoding='utf-8')
    result=build(store,key)
    print(target['college'],len(patch['observations']),len(patch['report']['repairs']),result['counts'],flush=True)


async def main():
    store=Store(ROOT/'runs/workbench/workbench.db')
    with store.db() as con:jobs=[dict(x) for x in con.execute('SELECT * FROM jobs ORDER BY created')]
    latest={json.loads(j['target'])['college']:j['id'] for j in jobs}
    for key in latest.values():await repair(store,key)

if __name__=='__main__':asyncio.run(main())
