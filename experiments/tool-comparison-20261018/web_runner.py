"""Bounded live native/Jina reads. All outputs stay within this experiment."""
import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT=Path(__file__).resolve().parent

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('provider',choices=['native','jina','jina_body','jina_full','jina_html'])
    parser.add_argument('--ids',nargs='*')
    args=parser.parse_args()
    provider=args.provider
    samples=json.loads((ROOT/'samples.json').read_text(encoding='utf8'))
    samples += [dict(x,kind='document') for x in json.loads((ROOT/'documents.json').read_text(encoding='utf8')) if x.get('url')]
    if args.ids:samples=[x for x in samples if x['id'] in args.ids]
    dest=ROOT/'results'/provider
    dest.mkdir(parents=True,exist_ok=True)
    session=requests.Session()
    session.headers['User-Agent']='FacultyCompatibilityStudy/1.0 (+bounded public university page comparison)'
    for sample in samples:
        target=dest/(sample['id']+'.json')
        if target.exists(): continue
        url=sample['url']
        headers={}
        if provider.startswith('jina'):
            url='https://r.jina.ai/'+url
            headers={'Accept':'application/json','x-no-cache':'true','x-retain-links':'all','x-with-links-summary':'all','x-timeout':'45'}
            if provider=='jina_body':headers['x-target-selector']='body'
            if provider=='jina_full':headers['x-respond-with']='markdown'
            if provider=='jina_html':headers['x-respond-with']='html'
        started=time.monotonic()
        record={'id':sample['id'],'provider':provider,'url':sample['url'],'request_url':url,
                'request_headers':headers,'timestamp':datetime.now(timezone.utc).isoformat()}
        try:
            response=session.get(url,headers=headers,timeout=(15,65))
            record.update(http_status=response.status_code,response_headers=dict(response.headers),final_url=response.url)
            if provider=='native':
                suffix='.pdf' if 'pdf' in response.headers.get('Content-Type','') else '.html'
                raw=dest/(sample['id']+suffix)
                raw.write_bytes(response.content)
                record.update(raw_file=raw.name,sha256=hashlib.sha256(response.content).hexdigest(),bytes=len(response.content))
            else:
                try: record['response']=response.json()
                except ValueError:record['response_text']=response.text
            record['transport_ok']=response.ok
        except Exception as exc:
            record.update(transport_ok=False,error=f'{type(exc).__name__}: {exc}')
        record['elapsed_seconds']=round(time.monotonic()-started,3)
        target.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf8')
        print(json.dumps({'provider':provider,'id':sample['id'],'http':record.get('http_status'),'seconds':record['elapsed_seconds']},ensure_ascii=False),flush=True)
        if record.get('http_status') in (401,402,429):
            print('Provider access/quota limit: stopping this arm without bypass.',flush=True)
            break
        time.sleep(3.2 if provider.startswith('jina') else 1.1)

if __name__=='__main__':main()
