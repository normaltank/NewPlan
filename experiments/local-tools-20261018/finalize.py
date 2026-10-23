"""Freeze actual results, usage, versions and isolation evidence."""
import hashlib
import json
import re
from pathlib import Path
from common import ROOT, read, save, compact, norm
from prepare import baseline
from evaluate import main as evaluate

def main():
    evaluate()
    before = read(ROOT/'baseline-before.json')
    after = baseline()
    save(ROOT/'baseline-after.json',after)
    changed = [p for p,h in before['files'].items() if after['files'].get(p)!=h]
    isolation = {'checked_files':len(before['files']),'changed_files':changed,
                 'human_decisions_before':before['human_decisions'],'human_decisions_after':after['human_decisions'],
                 'human_decisions_unchanged':before['human_decisions_sha256']==after['human_decisions_sha256'],
                 'git_head_unchanged':before['git_head']==after['git_head'],
                 'no_production_restart_or_integration':True}
    save(ROOT/'isolation-check.json',isolation)
    meta = {}
    for env in ('fetch','graph'):
        versions={}
        for p in (ROOT/f'.venv-{env}/Lib/site-packages').glob('*.dist-info/METADATA'):
            text=p.read_text(encoding='utf8')
            name=re.search(r'^Name: (.+)$',text,re.M)
            version=re.search(r'^Version: (.+)$',text,re.M)
            if name and version:versions[name[1]]=version[1]
        meta[env]=versions
    save(ROOT/'versions.json',{'python':'3.12.10','packages':meta,
        'package_index':'https://pypi.tuna.tsinghua.edu.cn/simple',
        'reason':'Direct PyPI TLS handshake failed. Mirror used with TLS verification enabled; exact installed dependency versions frozen.',
        'scrapling_browser':'0.5 StealthyFetcher; solve_cloudflare=False, google_search=False, no external proxy or captcha service.',
        'browser_files':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'.browsers-fetch').glob('**/chrome.exe')},
        'tokenizer_files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'.tiktoken-cache').glob('*') if p.is_file()}})
    models=read(ROOT/'extraction-comparison.json')
    usage={'page_attempts':{arm:len(list((ROOT/'results'/arm).glob('p*.json'))) for arm in ('scrapy_http','scrapling_http','scrapling_browser')},
           'model_arms':{k:{'calls':v['api_calls'],'usage':v['usage']} for k,v in models.items()},
           'model_calls':sum(v['api_calls'] for v in models.values()),
           'model_tokens':sum(v['usage']['total_tokens'] for v in models.values()),
           'model':'deepseek-flash','model_endpoint':'https://api.deepseek.com',
           'new_paid_subscriptions':0,'jina_recheck_calls':len(list((ROOT/'results/jina_recheck').glob('*.json'))),
           'jina_authentication':'anonymous','jina_tokens':sum(read(p).get('response',{}).get('data',{}).get('usage',{}).get('tokens',0) for p in (ROOT/'results/jina_recheck').glob('*.json')),
           'notes':['Model usage from actual provider responses, not an account currency invoice.',
                    'Scrapy elapsed_seconds includes queue waiting; do not compare its per-page timing with synchronous arms.',
                    'First ScrapeGraphAI startup interrupted before model call while downloading tokenizer; later restart completed. Cold download time is not steady-state model latency.']}
    save(ROOT/'usage.json',usage)
    previous=read(ROOT.parent/'tool-comparison-20261018/usage.json')['jina_full']
    mean=previous['reported_output_tokens']/previous['saved_requests']
    save(ROOT/'jina-cost-estimate.json',{
        'source':'https://jina.ai/api-dashboard/pricing/','date':'2026-10-18',
        'standard_package_usd':50,'standard_package_tokens':1000000000,
        'usd_per_million_tokens':0.05,'sample_requests':previous['saved_requests'],
        'sample_tokens':previous['reported_output_tokens'],'mean_tokens_per_request':mean,
        'estimates':[{'requests':n,'tokens':mean*n,'usage_equivalent_usd':round(mean*n/1000000*.05,4)} for n in (10000,100000,1000000)],
        'anonymous_rpm':20,'anonymous_minimum_hours_for_100000':100000/20/60,
        'limitations':['Diagnostic sample mix, not a random estimate of all pages.',
                      'Usage-equivalent cost differs from prepaid package purchase amount.',
                      'Excludes retries, extra HTML calls, optional OCR, downstream model usage and tax.',
                      'Number of page requests is not number of teachers; updates add more requests.',
                      'Free key trial is labelled non-commercial on the public package page; not a basis for long-term production budgeting.']})
    rechecks=[]
    for p in (ROOT/'results/jina_recheck').glob('*.json'):
        row=read(p);body=row.get('response',{}).get('data',{}).get('content','')
        marker='dxp@seu.edu.cn' if row['id']=='p07' else 'A prior-based graph for salient object detection'
        rechecks.append({'id':row['id'],'url':row['url'],'status':row.get('status'),'marker':marker,'marker_retained':norm(marker) in norm(body)})
    save(ROOT/'jina-recheck-summary.json',rechecks)
    included=[]
    candidates=[]
    for entry in ROOT.iterdir():
        if entry.name.startswith('.') or entry.name=='__pycache__':continue
        candidates.extend(entry.rglob('*') if entry.is_dir() else [entry])
    for p in candidates:
        if not p.is_file():continue
        rel=p.relative_to(ROOT)
        if any(part.startswith('.') or part=='__pycache__' for part in rel.parts):continue
        if p.name in ('evidence-sha256.json',) or p.suffix=='.zip':continue
        if p.name.startswith('verification') and p.suffix=='.log':continue
        included.append(p)
    hits=[]
    for p in included:
        if p.suffix in ('.json','.py','.ps1','.log','.md','.txt','.lock'):
            text=p.read_text(encoding='utf8',errors='replace')
            if re.search(r'(?:sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{25,})',text):hits.append(str(p.relative_to(ROOT)))
    save(ROOT/'credential-scan.json',{'files_checked':len(included),'credential_matches':hits})
    save(ROOT/'evidence-sha256.json',{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in included})
    assert not changed and isolation['human_decisions_unchanged'] and isolation['git_head_unchanged']
    assert not hits
    print(json.dumps({'isolation':isolation,'usage':usage},ensure_ascii=False))

if __name__=='__main__':main()
