"""Continue saved work into a new run; never rewrite previous evidence."""
import json
import re
import shutil
from pathlib import Path
from bs4 import BeautifulSoup
from benchmark import ROOT,write_json


def restore(pilot,source):
    from api_pilot import selected,title_name
    source=Path(source).resolve()
    if not source.is_relative_to((ROOT/'runs').resolve()) or not (source/'targets.json').is_file():
        raise ValueError('Resume source must be a saved OpenSource run')
    def old(name,default):
        path=source/(name+'.json')
        return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else default
    original=old('input',{})
    if any(original.get(key)!=getattr(pilot.args,key) for key in ('university','college','url')):
        raise ValueError('续采来源的大学、学院和首页必须一致')
    for child in source.iterdir():
        if child.is_dir() and (re.fullmatch(r'[a-f0-9]{16,20}',child.name) or child.name in ('media','documents')):
            shutil.copytree(child,pilot.out/child.name)
    if (source/'enrichment.json').is_file():shutil.copyfile(source/'enrichment.json',pilot.out/'enrichment.json')
    pilot.targets=old('targets',pilot.targets)
    pilot.pages=list({p['url']:p for p in old('pages',[])}.values())
    pilot.observations=old('observations',[])
    pilot.rosters=old('roster-pages',[])
    pilot.documents=old('documents',[]);pilot.media=old('media',[])
    pilot.media_cache={m['source_url']:m for m in pilot.media}
    pilot.plans=old('plans',{});pilot.discovery=old('discovery',{})
    pilot.branch_audit=old('branch-audit',[])
    template=pilot.plans.get('__profiles__',{}).get(pilot.host,pilot.plans.get('__profile__',{}))
    pilot.profile_selector=template.get('body_selector')
    pilot.profile_selectors=template.get('selectors') or ([pilot.profile_selector] if pilot.profile_selector else [])
    former=old('issues',[]);pilot.issues=former[:]
    write_json(pilot.out/'previous-issues.json',former)
    # Legacy limits dropped URLs before queueing them. Recover only from saved,
    # qualified roster rows using the same stored plan, without new API inference.
    pages={p['url']:p for p in pilot.pages};replayed=[]
    for roster in pilot.rosters:
        if roster.get('source_qualification')!='faculty_roster':continue
        page=pages.get(roster['url'],{});plan=pilot.plans.get(roster.get('branch'),{})
        path=pilot.out/page.get('directory','')/'source.html'
        if plan.get('page_kind')=='directory' and plan.get('row_selector') and path.is_file():
            soup=BeautifulSoup(path.read_text(encoding='utf8',errors='replace'),'lxml')
            rows=soup.select(plan['row_selector'])
            if rows and len(rows)>=roster.get('entries',0):
                pilot.observations=[o for o in pilot.observations if not(o['source_url']==roster['url'] and o.get('source_kind')=='directory_link')]
                for row in rows:
                    label=selected(row,plan.get('label_selector'));link=selected(row,plan.get('href_selector'))
                    if label is None:continue
                    name=title_name(label.get_text(' ',strip=True))
                    if not name:continue
                    from urllib.parse import urljoin
                    url=urljoin(page.get('loaded_url',page['url']),link.get('href','')) if link is not None and link.get('href') else ''
                    pilot.observe(name,url,roster['url'],roster['branch'],'directory_link',label.get_text(' ',strip=True))
                replayed.append(roster['url'])
        for observation in pilot.observations:
            if observation['source_url']==roster['url'] and observation.get('profile_url'):
                pilot.register(observation['profile_url'],'profile',observation.get('branch',''),
                               source_url=roster['url'],person_name=observation['name'],qualified=True)
        for url in roster.get('next',[]):pilot.register(url,'roster',roster.get('branch',''))
    pilot.observations=list({json.dumps(o,sort_keys=True,ensure_ascii=False):o for o in pilot.observations}.values())
    reclassified=[p['url'] for p in pilot.pages if p.get('kind')=='document' and pilot.targets.get(p['url'],{}).get('kind')=='profile']
    pilot.pages=[p for p in pilot.pages if p['url'] not in reclassified]
    # The original rejection remains in previous-issues.json; the current queue
    # now explicitly records that it is pending, not inaccessible or empty.
    pilot.issues=[i for i in pilot.issues if not(i['kind'] in {'out_of_host_scope','page_limit'} and i['url'] in pilot.targets)]
    initial=pilot.pending_urls()
    priority=getattr(pilot.args,'prioritize',[]) or []
    initial=[u for u in priority if u in initial]+[u for u in initial if u not in priority]
    pilot.scheduled=set(pilot.targets)
    write_json(pilot.out/'resume.json',{'source_run':str(source),'reused_pages':len(pilot.pages),
        'pending_urls':initial,'replayed_rosters':replayed,'reclassified_profiles':reclassified,'prioritized_urls':priority,
        'note':'Only unvisited pages are continued. Previous empty/failed pages are not retried automatically. Old evidence and human decisions remain in their original run.'})
    return initial
