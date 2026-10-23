"""Validate and preview three/four-column input before creating acquisition jobs."""
import csv
import io
import re
from urllib.parse import urlparse


HEADERS = ({'大学','学校','university'}, {'学院','学院名','college'},
           {'学院链接','学院网址','官网链接','url'}, {'师资链接','师资列表链接','entries'})


def plain_url(value):
    value = value.strip().strip('`')
    match = re.fullmatch(r'\[[^\]]*\]\((https?://[^\s]+)\)', value)
    return (match[1] if match else value).strip('<>')


def validate_target(target):
    if not isinstance(target, dict):
        raise ValueError('每行应包含大学、学院和学院链接')
    for key in ('university','college','url'):
        if not isinstance(target.get(key), str) or not target[key].strip():
            raise ValueError('大学、学院和学院链接不能为空')
    url = urlparse(target['url'])
    if url.scheme not in ('https','http') or not url.hostname or url.username or url.password or url.port:
        raise ValueError('学院链接必须为标准 HTTP(S) 官网链接')
    if not (url.hostname.endswith('.edu.cn') or url.hostname.endswith('.edu')):
        raise ValueError('试采工作台只接受 edu.cn / edu 官网')
    entries=target.get('entries',[])
    if not isinstance(entries,list) or len(entries)>32 or any(not isinstance(v,str) or not v.strip() for v in entries):
        raise ValueError('师资链接应为最多 32 个有效链接的列表')
    for entry in entries:
        other=urlparse(entry)
        if other.scheme not in ('https','http') or other.netloc.lower()!=url.netloc.lower() or other.username or other.password:
            raise ValueError('师资链接目前须与学院链接属于同一域名')


def preview_input(text=None, targets=None):
    errors=[]; candidates=[]; skipped=0
    if text is not None:
        if not isinstance(text,str) or len(text)>200_000:
            raise ValueError('粘贴内容需为文本且不超过 20 万字符')
        lines=[(n,line) for n,line in enumerate(text.lstrip('\ufeff').splitlines(),1) if line.strip()]
        if len(lines)>500:
            raise ValueError('粘贴内容超过 500 行，请分批输入')
        for n,line in lines:
            if re.fullmatch(r'\s*\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)+\|?\s*',line):
                continue
            try:
                if '\t' in line:
                    cells=next(csv.reader([line],delimiter='\t',strict=True))
                elif line.strip().startswith('|'):
                    cells=line.strip().strip('|').split('|')
                elif ',' in line:
                    cells=next(csv.reader([line],strict=True))
                else:
                    cells=re.split(r'\s+',line.strip())
                cells=[c.strip() for c in cells]
                if len(cells) in (3,4) and all(c.lower() in HEADERS[i] for i,c in enumerate(cells)):
                    continue
                if len(cells) not in (3,4):
                    raise ValueError(f'需要 3 或 4 列，当前为 {len(cells)} 列；建议从 Excel 复制，用制表符分隔')
                entry=cells[3] if len(cells)==4 else ''
                candidates.append((n,{'university':cells[0],'college':cells[1],'url':plain_url(cells[2]),
                                      'entries':[plain_url(v) for v in re.split('[;；]',entry) if v.strip()]}))
            except (ValueError,csv.Error) as error:
                errors.append({'row':n,'message':str(error)})
    else:
        if not isinstance(targets,list) or len(targets)>500:
            raise ValueError('学院数据应为列表，最多 500 行')
        candidates=list(enumerate(targets,1))
    normalized=[];seen={}
    for n,target in candidates:
        try:
            validate_target(target)
            clean={k:target[k].strip() for k in ('university','college','url')}
            clean['entries']=list(dict.fromkeys(v.strip() for v in target.get('entries',[])))
            key=(clean['university'],clean['college'],clean['url'].rstrip('/'))
            if key in seen:
                existing=normalized[seen[key]]
                existing['entries']=list(dict.fromkeys(existing['entries']+clean['entries']))
                validate_target(existing)
                skipped+=1
            else:
                seen[key]=len(normalized);normalized.append(clean)
        except (ValueError,TypeError) as error:
            errors.append({'row':n,'message':str(error)})
    if not normalized and not errors:
        errors.append({'row':0,'message':'请至少输入一个学院'})
    if len(normalized)>100:
        errors.append({'row':0,'message':'每批最多 100 个学院，请拆分批次'})
    return {'targets':normalized,'errors':errors,'duplicates_merged':skipped,
            'count':len(normalized),'without_entries':sum(not t['entries'] for t in normalized)}
