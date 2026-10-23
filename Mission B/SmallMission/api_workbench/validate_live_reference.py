"""Independent source-DOM recount. These reference selectors are never sent to API."""
import hashlib
import json
from pathlib import Path
from urllib.parse import urljoin,urlsplit,urlunsplit
from lxml import html

ROOT=Path(__file__).resolve().parent
RUN=ROOT/'validation'/'live-v1'
RULES={
 '清华大学':"//dl[contains(concat(' ',normalize-space(@class),' '),' deptList ')]/dd/a[@href]",
 '北京理工大学':"//div[contains(concat(' ',normalize-space(@class),' '),' wraplist4 ')]/ul/li/a[@href]"
}

def main():
    records=json.loads((RUN/'results.json').read_text('utf8'));checks=[]
    for r in records:
        if r['school'] not in RULES:
            checks.append({'school':r['school'],'status':'未取得网页，不建立真值','reason':r['source']['issues']});continue
        meta=r['attempts'][-1];raw=(RUN/meta['html_path']).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==meta['html_sha256']
        tree=html.fromstring(raw.decode('utf8'));nodes=tree.xpath(RULES[r['school']]);reference=[]
        for a in nodes:
            p=urlsplit(urljoin(meta['final_url'],a.get('href')))
            assert p.scheme in ('http','https')
            reference.append({'text':''.join(a.itertext()).strip(),'url':urlunsplit((p.scheme,p.netloc.lower(),p.path or '/',p.query,p.fragment))})
        expected={a['url'] for a in reference};actual=set(r['source']['links'])
        checks.append({'school':r['school'],'status':'通过' if expected==actual else '不一致','source':meta['final_url'],
            'xpath':RULES[r['school']],'html_sha256':meta['html_sha256'],'reference_occurrences':len(reference),
            'reference_unique':len(expected),'actual_unique':len(actual),'missing':sorted(expected-actual),
            'extra':sorted(actual-expected),'anchors':reference})
    result={'scope':'指定名单页，独立人工检查区域后用XPath重数；不是全院身份核验',
        'reference_visible_to_model':False,'checks':checks}
    (RUN/'independent-reference.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps([{k:v for k,v in c.items() if k not in ('anchors','reason')} for c in checks],ensure_ascii=False))
    assert all(c.get('missing')==c.get('extra')==[] for c in checks if 'missing' in c)

if __name__=='__main__':main()
