"""Measure known evidence retention; these are not final faculty accuracy rates."""
from collections import Counter
from common import ROOT, read, save, compact, norm, urlkey, content

def evidence(sample, row):
    expected = sample['expected']
    text = row.get('text','')
    body = compact(text)
    links = {urlkey(x['url']) for x in row.get('links',[])}
    checks = {}
    for field in ('name','email','title'):
        if expected.get(field):
            checks[field] = compact(expected[field]) in body
    if expected.get('biography_marker'):
        checks['biography_marker'] = norm(expected['biography_marker']) in norm(text)
    if expected.get('rows'):
        checks['roster_names'] = {'matched':sum(compact(x['name']) in body for x in expected['rows']), 'total':len(expected['rows'])}
        checks['roster_links'] = {'matched':sum(urlkey(x['url']) in links for x in expected['rows']), 'total':len(expected['rows'])}
    if expected.get('all_names'):
        checks['all_names'] = {'matched':sum(compact(x) in body for x in expected['all_names']), 'total':len(expected['all_names'])}
    if expected.get('pagination_urls'):
        checks['pagination_urls'] = {'matched':sum(urlkey(x) in links for x in expected['pagination_urls']), 'total':len(expected['pagination_urls'])}
    if expected.get('attachment_url'):
        checks['embedded_document'] = urlkey(expected['attachment_url']) in {urlkey(x) for x in row.get('embedded_documents',[])}
    return checks

def retrieval(samples):
    result = {}
    for arm in ('scrapy_http','scrapling_http','scrapling_browser','frozen_html'):
        details = []
        totals = {}
        for s in samples:
            p = ROOT/'results'/arm/f"{s['id']}.json"
            if arm == 'frozen_html':
                row = content((ROOT/s['frozen_html']).read_text(encoding='utf8'),s['url'])
                row['status'] = 'snapshot'
            elif p.exists():
                row = read(p)
            else:
                continue
            checks = evidence(s,row)
            for key, val in checks.items():
                group = 'professor_links' if key=='roster_links' and s['id']=='p18' else key
                totals.setdefault(group,{'matched':0,'total':0})
                totals[group]['matched'] += val['matched'] if isinstance(val,dict) else int(val)
                totals[group]['total'] += val['total'] if isinstance(val,dict) else 1
            details.append({'id':s['id'],'url':s['url'],'status':row.get('status'),'error':row.get('error'),'checks':checks})
        result[arm] = {'records':len(details),'totals':totals,'details':details}
    save(ROOT/'retrieval-comparison.json',result)
    return result

def extraction(samples):
    results = {}
    for arm in ('scrapegraph','direct_ds'):
        details = []
        for s in samples:
            path = ROOT/'results'/arm/f"{s['id']}.json"
            if not path.exists():continue
            row = read(path)
            out = row.get('output') or {}
            if isinstance(out,str):
                out = {'unparsed':out}
            people = out.get('teachers',[]) if isinstance(out,dict) else []
            expected = s['expected']
            checks = {}
            if s['kind']=='profile':
                matching = [p for p in people if compact(p.get('name',''))==compact(expected['name'])]
                checks['name'] = len(matching)==1
                checks['unexpected_people'] = [p.get('name') for p in people if compact(p.get('name',''))!=compact(expected['name'])]
                person = matching[0] if matching else {}
                for key in ('email','title'):
                    if expected.get(key):checks[key] = compact(person.get(key))==compact(expected[key])
                if expected.get('biography_marker'):
                    checks['biography_marker'] = norm(expected['biography_marker']) in norm(person.get('biography',''))
                checks['biography_chars'] = len(person.get('biography') or '')
            elif s['kind']=='roster':
                names = set(compact(p.get('name','')) for p in people)
                ref_names = set(compact(x) for x in expected.get('all_names',[])) or set(compact(p['name']) for p in expected['rows'])
                checks['names_matched'] = len(names & ref_names)
                checks['names_expected'] = len(ref_names)
                checks['unexpected_names'] = sorted(names-ref_names)
                checks['missing_names'] = sorted(ref_names-names)
                matched_links = 0
                for expected_person in expected['rows']:
                    candidates = [p for p in people if compact(p.get('name',''))==compact(expected_person['name'])]
                    if any(p.get('homepage') and urlkey(p['homepage'])==urlkey(expected_person['url']) for p in candidates):matched_links+=1
                checks['links_matched'] = matched_links
                checks['links_expected'] = len(expected['rows'])
                counts = Counter(compact(p.get('name','')) for p in people)
                checks['duplicate_names'] = [k for k,v in counts.items() if v>1]
            if expected.get('attachment_url'):
                checks['embedded_document'] = urlkey(expected['attachment_url']) in {urlkey(x) for x in out.get('attachment_urls',[])}
                checks['unexpected_people'] = [p.get('name') for p in people]
            details.append({'id':s['id'],'url':s['url'],'success':row.get('success'),'error':row.get('error'),'checks':checks})
        api_rows = [read(p) for p in (ROOT/'api'/arm).glob('**/*-response.json')]
        usage = {key:sum(x.get('usage',{}).get(key,0) for x in api_rows) for key in ('prompt_tokens','completion_tokens','total_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens')}
        results[arm] = {'records':len(details),'api_calls':len(list((ROOT/'api'/arm).glob('**/*-request.json'))),
                        'usage':usage,'details':details}
    save(ROOT/'extraction-comparison.json',results)
    return results

def main():
    samples=read(ROOT/'samples.json')
    a = retrieval(samples)
    b = extraction(samples)
    print({arm:row['totals'] for arm,row in a.items()})
    print({arm:{'records':row['records'],'api_calls':row['api_calls'],'usage':row['usage'],'details':row['details']} for arm,row in b.items()})

if __name__=='__main__':main()
