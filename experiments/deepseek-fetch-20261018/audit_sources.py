"""Independent narrow source-row checks; not whole-college certification."""
import json
from pathlib import Path
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from fetch_client import save

ROOT=Path(__file__).resolve().parent

def read(path):
    return json.loads(path.read_text(encoding='utf8'))

def run_path(case):
    pointer=ROOT/'runs'/case/('continued-pointer.json' if case=='seu' else 'capture-pointer.json')
    return Path(read(pointer)['run_dir'])

def main():
    report={'whole_college_completeness':'unverified','checks':[]}
    run=run_path('ntu')
    doc=next(run.glob('documents/*/pdf-text.json'))
    text=read(doc)['text']
    # This specific three-page PDF has a name, sex and YYYY.MM in each row.
    names=re.findall(r'^([\u3400-\u9fff]{2,4})\s+[男女]\s+\d{4}[.．]\d{1,2}',text,re.M)
    observed={o['name'] for o in read(run/'observations.json')}
    report['checks'].append({'case':'ntu','method':'independent PDF line/sex/date pattern',
        'source':str(doc),'rows':len(names),'distinct_names':len(set(names)),
        'source_names_missing_from_observations':sorted(set(names)-observed),
        'observations_not_in_pdf_rows':sorted(observed-set(names)),
        'limit':'Text-layer row coverage only; no claim about undiscovered college branches.'})
    run=run_path('seu')
    page=next(p for p in read(run/'pages.json') if p['url']=='https://wjx.seu.edu.cn/xyds/list.htm')
    soup=BeautifulSoup((run/page['directory']/'source.html').read_text(encoding='utf8',errors='replace'),'html.parser')
    anchors=soup.select('.col_news_list.listcon li.news a[href]')
    labels=[''.join(a.get_text().split()) for a in anchors]
    observed={o['name'] for o in read(run/'observations.json') if o['source_url']==page['url']}
    observed_normalized={''.join(name.split()) for name in observed}
    report['checks'].append({'case':'seu','method':'saved official grouped-list anchors, independent DOM selection',
        'url':page['url'],'source':str(run/page['directory']/'source.html'),
        'link_rows':len(labels),'distinct_link_labels':len(set(labels)),
        'source_labels_missing_from_observations':sorted(set(labels)-observed_normalized),
        'observations_outside_selected_anchor_region':sorted(name for name in observed if ''.join(name.split()) not in set(labels)),
        'whitespace_only_label_differences':sorted(name for name in observed if name not in set(labels) and ''.join(name.split()) in set(labels)),
        'limit':'Other faculty branches and final identity decisions require separate checks.'})
    run=run_path('fynu')
    pages={p['url']:p for p in read(run/'pages.json')}
    rosters=[r for r in read(run/'roster-pages.json') if '/szdw/sssds' in r['url']]
    row_count=0
    checks=[]
    for roster in rosters:
        p=pages[roster['url']]
        soup=BeautifulSoup((run/p['directory']/'source.html').read_text(encoding='utf8',errors='replace'),'html.parser')
        anchors=soup.select('dd[id^="line_"] a.fl[href]')
        observed={o['profile_url'] for o in read(run/'observations.json') if o['source_url']==p['url']}
        links={urljoin(p['url'],a['href']) for a in anchors}
        row_count+=len(anchors)
        checks.append({'url':p['url'],'rows':len(anchors),'missing_links':sorted(links-observed)})
    report['checks'].append({'case':'fynu','method':'independent dated directory rows over all six masters pages',
        'pages':checks,'rows':row_count,'official_declared_total':next((r.get('declared_total') for r in rosters if r.get('declared_total')),None),
        'limit':'Checks the masters branch only, not every teacher category or its current affiliation.'})
    save(ROOT/'source-audit.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
