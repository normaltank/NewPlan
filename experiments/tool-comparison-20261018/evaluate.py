"""Evidence retention checks, never an estimate of college completeness/accuracy."""
import html
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit, unquote, parse_qs

from bs4 import BeautifulSoup
from markdown_it import MarkdownIt

ROOT=Path(__file__).resolve().parent
MD=MarkdownIt('commonmark',{'html':True})

def read(p):return json.loads(p.read_text(encoding='utf8'))
def save(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8')
def compact(s):return re.sub(r'\s+','',unicodedata.normalize('NFKC',str(s))).lower()
def norm(s):return re.sub(r'[^\w\u3400-\u9fff]+','',compact(s))
def urlkey(url,base=''):
    u=urlsplit(urljoin(base,html.unescape(url)))
    return unquote(urlunsplit(('',u.netloc.lower(),u.path.rstrip('/'),u.query,'')))
def from_html(value,base):
    soup=BeautifulSoup(value,'html.parser')
    for tag in soup.select('script,style,noscript'):tag.decompose()
    links=[{'text':a.get_text('',strip=True),'url':urljoin(base,a['href'])} for a in soup.select('a[href]')]
    return soup.get_text('\n',strip=True),links
def from_md(value,base):return from_html(MD.render(value or ''),base)

def link_urls(value):
    if isinstance(value,str):return [value] if re.match(r'^(https?://|/|\.\.?/|mailto:)',value) else []
    if isinstance(value,list):return [url for item in value for url in link_urls(item)]
    if isinstance(value,dict):return [url for item in value.values() for url in link_urls(item)]
    return []

def embedded_documents(value,base):
    """Extract explicit embedded document URLs; never treat a resource as a person."""
    soup=BeautifulSoup(value,'html.parser');found=set()
    for node in soup.select('[src], [data], [pdfsrc]'):
        for attr in ('src','data','pdfsrc'):
            raw=node.get(attr,'')
            if not raw:continue
            url=urljoin(base,html.unescape(raw))
            if urlsplit(url).path.lower().endswith('.pdf'):found.add(url)
            for key,values in parse_qs(urlsplit(url).query).items():
                if key not in ('file','url','src'):continue
                for item in values:
                    if urlsplit(item).path.lower().endswith('.pdf'):found.add(urljoin(base,item))
    return sorted(found)

def payload(record):
    res=record.get('response',{})
    if 'structuredContent' in res:return res['structuredContent']
    for block in res.get('content',[]):
        if block.get('type')=='text':
            try:return json.loads(block['text'])
            except (ValueError,TypeError):pass
    return res

def provider_text(provider,sample):
    sid=sample['id'];url=sample['url'];folder=ROOT/'sources'/sid
    if provider in ('native_previous','deepseek_previous'):
        path=folder/('native.txt' if provider=='native_previous' else 'deepseek.json')
        if not path.exists():return None
        if provider=='native_previous':return {'text':path.read_text(encoding='utf8'),'links':[], 'status':'saved_previous_body'}
        text,links=from_md(read(path)['content'],url)
        return {'text':text,'links':links,'status':'saved_previous_response'}
    path=ROOT/'results'/provider/(sid+'.json')
    if not path.exists():return None
    record=read(path)
    if provider=='native':
        raw=ROOT/'results/native'/record.get('raw_file','')
        text,links=from_html(raw.read_bytes(),url) if raw.is_file() and raw.suffix=='.html' else ('',[])
        return {'text':text,'links':links,'status':record.get('http_status'),'seconds':record['elapsed_seconds'],
                'embedded_document_urls':embedded_documents(raw.read_bytes(),url) if raw.is_file() and raw.suffix=='.html' else []}
    data=payload(record)
    if provider.startswith('jina'):data=data.get('data',{})
    content=data.get('html','') if provider=='jina_html' else data.get('markdown',data.get('content',''))
    text,links=from_html(content,url) if provider=='jina_html' else from_md(content,url)
    all_links=link_urls(data.get('links',[]))
    for link in all_links:links.append({'text':'','url':urljoin(url,link)})
    rawhtml=data.get('rawHtml','') or (content if provider=='jina_html' else '')
    rawtext,rawlinks=from_html(rawhtml,url)
    meta=data.get('metadata',{})
    return {'text':text,'links':links,'raw_text':rawtext,'raw_links':rawlinks,
            'status':meta.get('statusCode',data.get('httpStatus',record.get('http_status'))),
            'seconds':record.get('elapsed_seconds'),'credits':meta.get('creditsUsed'),
            'embedded_document_urls':embedded_documents(rawhtml,url),
            'usage':data.get('usage'),'error':data.get('error')}

def refs():
    samples=read(ROOT/'samples.json')
    p18=next(x for x in samples if x['id']=='p18')
    soup=BeautifulSoup((ROOT/'sources/p18/original.html').read_text(encoding='utf8'),'html.parser')
    body=soup.select_one('#vsb_content_4')
    p18['expected']['rows']=[{'name':a.get_text('',strip=True),'url':urljoin(p18['url'],a['href'])} for a in body.select('a[href]')]
    p18['expected']['all_names']=['马继龙','凡素华','王洪涛','李慧泉','陈水生','张宏','张淑萍','张颖','邵思常','范少华','罗春华','金凤','陶栋梁','盛良全','崔玉民','郝扶影','金晓艳','刘昭第','乔瑞','宋崇富','武海','黄德乾','管清梅','苗慧','吴福芳','金仁成','董秋静','王洪刚','牛贵宏','许巧玲','白翠冰','康红卫','张甲甲','徐华杰']
    for sample in samples:
        if sample['kind']=='roster':
            for row in sample['expected']['rows']:
                row['name']=compact(re.sub(r'^硕士生导师[—－-]*','',row['name']))
            if '/sssds' in sample['url']:
                original=ROOT/'sources'/sample['id']/'original.html'
                soup=BeautifulSoup(original.read_text(encoding='utf8'),'html.parser')
                urls={urljoin(sample['url'],a['href']) for a in soup.select('a[href]')}
                sample['expected']['pagination_urls']=sorted(u for u in urls if '/hxycl/szdw/sssds' in u and u!=sample['url'])
        if sample['id']=='p24':
            sample['expected']['attachment_url']=read(ROOT/'documents.json')[0]['url']
    save(ROOT/'reference-checks.json',samples)
    return samples

def doc_reference():
    raw=read(ROOT/'sources/d01/native.json')['text']
    parts=re.split(r'(?m)(?=^[\u3400-\u9fff]{2,4}\s+[男女]\s+\d{4}[.．])',raw)
    rows=[]
    titles=r'(主任医师[，,、]\s*教授|副主任医师[，,、]\s*教授|副主任护师|主任护师|副主任医师|主任医师|副教授|副研究员|教授|研究员)'
    for part in parts:
        m=re.match(r'^([\u3400-\u9fff]{2,4})\s+[男女]\s+\d{4}[.．]\d{1,2}\s*'+titles,part)
        if not m:continue
        token=compact(part)
        emails=re.findall(r'[A-Za-z0-9_.+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}',token)
        rows.append({'name':m[1],'title':m[2],'email':emails[-1] if emails else None,
                     'incomplete_email':'yho0704@163.' if m[1]=='严海鸥' else None})
    assert len(rows)==61, len(rows)
    save(ROOT/'document-reference.json',{'rows':rows,'scope':'All 3 PDF pages visually viewed; row fields parsed independently from native PDF text, differences require source review.'})
    return rows

def evaluate():
    samples=refs();results=[]
    for sample in samples:
        expected=sample['expected'];row={'id':sample['id'],'kind':sample['kind'],'url':sample['url'],'name':expected.get('name'),'group':sample['group'],'providers':{}}
        for provider in ['native','native_previous','deepseek_previous','firecrawl','jina','jina_body','jina_full','jina_html']:
            data=provider_text(provider,sample)
            if data is None:continue
            text=data['text'];stripped=compact(text);checks={k:v for k,v in data.items() if k not in ('text','links','raw_text','raw_links')}
            checks['characters']=len(text)
            for field in ('name','email','title','biography_marker'):
                value=expected.get(field)
                if value:
                    checks[field+'_retained']=norm(value) in norm(text) if field=='biography_marker' else compact(value) in stripped
                    if data.get('raw_text'):checks[field+'_in_raw_html']=compact(value) in compact(data['raw_text'])
            if sample['kind']=='roster':
                rows=expected.get('rows',[])
                names=expected.get('all_names') or [r['name'] for r in rows]
                linkset={urlkey(l['url'],sample['url']) for l in data['links']}
                checks.update(expected_names=len(names),names_retained=sum(compact(n) in stripped for n in names),
                    names_recoverable_after_format_cleanup=sum(norm(n) in norm(text) for n in names),
                    expected_profile_links=len(rows),profile_links_retained=sum(urlkey(r['url']) in linkset for r in rows),
                    missing_names=[n for n in names if compact(n) not in stripped],
                    missing_links=[r for r in rows if urlkey(r['url']) not in linkset])
                if expected.get('pagination_urls'):
                    checks['expected_pagination_urls']=len(expected['pagination_urls'])
                    checks['retained_pagination_urls']=sum(urlkey(x) in linkset for x in expected['pagination_urls'])
            if expected.get('attachment_url'):
                checks['attachment_link_retained']=any(urlkey(x['url'])==urlkey(expected['attachment_url']) for x in data['links'])
                checks['attachment_link_in_raw_html']=any(urlkey(x['url'])==urlkey(expected['attachment_url']) for x in data.get('raw_links',[]))
                checks['attachment_discoverable_from_embed']=urlkey(expected['attachment_url']) in {urlkey(x) for x in data.get('embedded_document_urls',[])}
            counts=Counter(norm(line) for line in text.splitlines() if len(norm(line))>=80)
            checks['repeated_long_passages']=[{'excerpt':x[:100],'count':n} for x,n in counts.items() if n>1][:5]
            row['providers'][provider]=checks
        results.append(row)
    save(ROOT/'web-comparison.json',{'scope':'Evidence retention only, not extraction precision, identity correctness or whole-college completeness. Previous native/DS arms are historical, current native controls source drift.', 'pages':results})
    for row in results:
        print(row['id'],row['name'] or row['kind'],json.dumps({p:{k:v for k,v in d.items() if k in ('email_retained','biography_marker_retained','names_retained','profile_links_retained','attachment_link_retained','status')} for p,d in row['providers'].items()},ensure_ascii=False))
    doc_reference()

if __name__=='__main__':evaluate()
