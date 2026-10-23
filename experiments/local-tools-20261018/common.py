import hashlib
import html
import json
import re
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit, unquote, parse_qs

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
USER_AGENT = 'FacultyCompatibilityStudy/1.0 (bounded public university page comparison)'

def read(p):
    return json.loads(p.read_text(encoding='utf8'))

def save(p, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding='utf8')

def compact(s):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', str(s))).lower()

def norm(s):
    return re.sub(r'[^\w\u3400-\u9fff]+', '', compact(s))

def urlkey(url, base=''):
    u = urlsplit(urljoin(base, html.unescape(url)))
    return unquote(urlunsplit(('', u.netloc.lower(), u.path.rstrip('/'), u.query, '')))

def content(raw, url):
    soup = BeautifulSoup(raw, 'html.parser')
    attachments = set()
    for node in soup.select('[src], [data], [pdfsrc]'):
        for attr in ('src', 'data', 'pdfsrc'):
            value = node.get(attr, '')
            if not value:
                continue
            u = urljoin(url, html.unescape(value))
            if urlsplit(u).path.lower().endswith('.pdf'):
                attachments.add(u)
            for key, values in parse_qs(urlsplit(u).query).items():
                if key in ('file', 'url', 'src'):
                    attachments.update(urljoin(url, x) for x in values if urlsplit(x).path.lower().endswith('.pdf'))
    for node in soup.select('script,style,noscript'):
        node.decompose()
    links = [{'name': a.get_text('', strip=True), 'url': urljoin(url, a['href'])} for a in soup.select('a[href]')]
    return {'text': soup.get_text('\n', strip=True), 'links': links, 'embedded_documents': sorted(attachments)}

def record(arm, sample, started, *, raw=None, status=None, final_url=None, error=None, encoding=None, extra=None):
    folder = ROOT/'results'/arm
    row = {'id':sample['id'], 'url':sample['url'], 'arm':arm,
           'timestamp':datetime.now(timezone.utc).isoformat(), 'elapsed_seconds': round(time.monotonic()-started,3),
           'status':status, 'final_url':final_url, 'error':error, 'encoding':encoding}
    if raw is not None:
        if isinstance(raw, str):
            raw = raw.encode('utf8')
            encoding = 'utf8'
        folder.mkdir(parents=True, exist_ok=True)
        path = folder/f"{sample['id']}.html"
        path.write_bytes(raw)
        row.update(raw_file=path.name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        row.update(content(raw.decode(encoding or 'utf8', errors='replace'), final_url or sample['url']))
    if extra:
        row.update(extra)
    save(folder/f"{sample['id']}.json", row)
    print(json.dumps({'arm':arm,'id':sample['id'],'status':status,'error':error,'seconds':row['elapsed_seconds']},ensure_ascii=False),flush=True)
    return row
