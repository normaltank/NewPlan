"""Saved-evidence assessment and immutable automatic dispositions for the workbench."""
import argparse
import hashlib
import json
import re
import uuid
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from functools import lru_cache
from urllib.parse import unquote, urlparse
from quality_fields import POLICY, compact, fields_from_text, profile_label_name, administrative_only, biography_identity_after_metadata
from image_triage import native_biography, triage_image, artwork_context, without_artwork_ocr, named_image_title
from roster_identity import associate
from material_delivery import apply_delivery
from roster_only_delivery import apply_roster_only


def read(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return default


@lru_cache(maxsize=20000)
def _file_digest(path, stamp):
    return hashlib.sha256(Path(path).read_bytes()).digest()

def content_digest(path):
    try:
        stat=path.stat()
    except FileNotFoundError:return b'missing'
    return _file_digest(str(path),(stat.st_mtime_ns,stat.st_ctime_ns,stat.st_size,stat.st_ino))

def saved_evidence_digest(path,cache,key):
    """Reuse a persisted content hash only while the file identity is unchanged."""
    try:stat=path.stat()
    except FileNotFoundError:return b'missing',False
    stamp=[stat.st_mtime_ns,stat.st_ctime_ns,stat.st_size,stat.st_ino]
    entry=cache.get(key,{})
    if isinstance(entry,dict) and entry.get('stamp')==stamp:
        try:
            value=bytes.fromhex(entry['sha256'])
            if len(value)==32:return value,False
        except (KeyError,ValueError,TypeError):pass
    value=content_digest(path)
    cache[key]={'stamp':stamp,'sha256':value.hex()}
    return value,True


def assessment_fingerprint(root,force=False):
    digest = hashlib.sha256()
    digest.update(content_digest(Path(__file__).with_name('roster_tables.py')))
    for name in ('image_profiles.py','grouped_roster.py','roster_sections.py'):digest.update(content_digest(Path(__file__).with_name(name)))
    for o in read(root/'observations.json',[]):
        if o.get('table_row_path'):
            path=(root/o['table_row_path']).resolve()
            if path.is_relative_to(root.resolve()):digest.update(content_digest(path))
        if o.get('person_image'):
            path=(root/o.get('person_body_path','')).resolve()
            if path.is_relative_to(root.resolve()):digest.update(content_digest(path))
            media=next((m for m in read(root/'media.json',[]) if m.get('directory')==o['person_image']),{})
            if media:
                path=(root/media['directory']/media['source_file']).resolve()
                if path.is_relative_to(root.resolve()):digest.update(content_digest(path))
    digest.update(content_digest(Path(__file__).with_name('person_names.py')))
    for source in (Path(__file__), Path(__file__).with_name('quality_fields.py'),Path(__file__).with_name('workbench_store.py'),Path(__file__).with_name('image_triage.py'),Path(__file__).with_name('roster_identity.py'),Path(__file__).with_name('material_delivery.py'),Path(__file__).with_name('roster_only_delivery.py')):
        digest.update(content_digest(source))
    for name in ('observations.json','pages.json','issues.json','media.json','documents.json','enrichment.json','roster-pages.json','pending-targets.json'):
        path = root/name
        digest.update(name.encode())
        digest.update(content_digest(path))
    # Roster associations consume saved HTML: changed originals invalidate them.
    roster_urls = {r.get('url') for r in read(root/'roster-pages.json', [])}
    cache_path=root/'evidence-digests.json'
    cache={} if force else read(cache_path,{});changed=False
    if not isinstance(cache,dict):cache={}
    for media in read(root/'media.json',[]):
        if not media.get('directory') or not media.get('source_file'):continue
        path=(root/media['directory']/media['source_file']).resolve()
        if not path.is_relative_to(root.resolve()):continue
        key=str(path.relative_to(root.resolve()))
        value,updated=saved_evidence_digest(path,cache,key)
        digest.update(key.encode());digest.update(value);changed=changed or updated
    for page in read(root/'pages.json', []):
        if page.get('directory'):
            path = root/page['directory']/'source.html'
            digest.update((page['directory']+'/source.html').encode())
            value,updated=saved_evidence_digest(path,cache,page['directory']+'/source.html')
            digest.update(value);changed=changed or updated
    if changed:
        temp=root/('evidence-digests-'+uuid.uuid4().hex+'.tmp')
        try:
            temp.write_text(json.dumps(cache,separators=(',',':')),encoding='utf8')
            replace_assessment(temp,cache_path)
        except OSError:
            # Cache failure must not turn a successfully read original into missing data.
            try:temp.unlink(missing_ok=True)
            except OSError:pass
    return digest.hexdigest()


def same_url(a,b):
    return (a or '').split('#')[0].replace('http://','https://',1)==(b or '').split('#')[0].replace('http://','https://',1)

def same_url_key(url):
    return (url or '').split('#')[0].replace('http://','https://',1)


def assess(cat, root):
    people = cat['people']
    page_conflicts={same_url_key(p['url']):p['personal_title_conflict'] for p in cat['pages'] if p.get('personal_title_conflict')}
    by_name = defaultdict(list)
    texts = {}
    original_texts = {}
    selections = {}
    email_names = defaultdict(set)
    docs = {d['path']:d for d in cat['documents']}
    images = {m['directory']:m for m in cat['media']}
    pages = {same_url_key(p['url']):p for p in cat['pages']}
    image_checks = {}
    fixed_pdf=set()
    for issue in cat['issues']:
        if issue['issue_kind']!='profile_pdf_failed':continue
        if any(d['url']==issue['url'] and d.get('text_chars') for d in cat['documents']):
            fixed_pdf.add(issue['id']);continue
        page=next((p for p in cat['pages'] if p['url']==issue.get('source_page')),None)
        if page:
            raw=(root/page['directory']/'source.html').read_text(encoding='utf-8',errors='replace')
            labels=re.findall(r"['\"]title['\"]\s*:\s*['\"]([^'\"]+\.pdf)['\"]",raw)
            if unquote(urlparse(issue['url']).path).split('/')[-1] in labels:
                fixed_pdf.add(issue['id'])
    for p in people:
        path = root/p['body_path'] if p.get('body_path') else None
        texts[p['id']] = path.read_text(encoding='utf-8') if path and path.is_file() else ''
        original_texts[p['id']] = texts[p['id']]
        media = [images[x] for x in p['media'] if x in images]
        artwork = artwork_context(root,pages.get(same_url_key(p.get('profile_url'))),images) if media else {}
        checks = [triage_image(m,root,p['name'],native_biography(root,p,texts[p['id']]),p.get('page_title',''),
                               artwork=artwork.get(m.get('source_url'))) for m in media]
        image_checks[p['id']] = checks
        texts[p['id']] = without_artwork_ocr(texts[p['id']],media,checks)
        name=profile_label_name(p['name'])
        if name!=p['name'] and compact(p['name']) in compact(p.get('page_title','')) and compact(name) in compact(texts[p['id']][:600]):
            p['name_normalization']={'observed_label':p['name'],'name':name,'rule':'profile_heading_suffix_with_personal_body',
                                     'evidence':texts[p['id']][:600],'body_path':p['body_path']}
            p['name']=name
        by_name[p['name']].append(p)
        heading=profile_label_name(re.split(r'[-_—|]',p.get('page_title',''),maxsplit=1)[0])
        f = fields_from_text(p['name'], texts[p['id']], p['observations'][0].get('branch','') if p['observations'] else '',
                             identity_bound=bool(p['profile_url'] and heading==p['name']))
        if p['profile_url'] and (heading==p['name'] or compact(native_biography(root,p,texts[p['id']])).startswith(compact(p['name']))):
            card_title=named_image_title(root,pages.get(same_url_key(p['profile_url'])),media,p['name'])
            if card_title and not f['title']['value']:
                f['title']=card_title
            elif card_title and f['title']['value']!=card_title['value']:
                f['anomalies'].append('图片信息卡与其他材料的职称不一致')
        conflict=page_conflicts.get(same_url_key(p.get('profile_url','')))
        if conflict:
            f['title']={'value':'','score':0,'rule':'personal_card_biography_conflict',
                        'evidence':'信息卡：'+conflict['card']['value']+'；本人简介：'+conflict['biography']['value'],
                        'candidates':conflict}
        # Email printed directly on the person's roster link belongs to that row.
        roster_mail=[]
        for observation in p['observations']:
            # Image observations carry a short preview; fields must come from
            # the verified full OCR text, never an address cut by the preview.
            if observation.get('source_kind')=='image_person_card':continue
            quote=observation.get('evidence','')
            if compact(p['name']) in compact(quote) and re.search(r'邮箱|[Ee]-?[Mm]ail',quote) and len(quote)<180:
                evidence=fields_from_text(p['name'],quote)
                roster_mail.extend({**e,'score':100,'rule':'named_roster_row'} for e in evidence['email_candidates'])
        if roster_mail:
            f['email_candidates']=roster_mail+f['email_candidates']
            f['email']={'value':'; '.join(dict.fromkeys(e['value'] for e in roster_mail)), 'score':100,
                        'evidence':'\n'.join(e['evidence'] for e in roster_mail),'rule':'named_roster_row'}
        selections[p['id']] = f
        for e in f['email_candidates']:
            email_names[e['value'].lower()].add(p['name'])
    items = {}
    # Same-name records only collapse when their original personal body/PDF agrees.
    duplicates = {}
    for group in by_name.values():
        seen = {}
        for p in sorted(group,key=lambda p:(-len(texts[p['id']]),p['id'])):
            text = texts[p['id']]
            key = hashlib.sha256(compact(text).encode()).hexdigest() if text else None
            if key and key in seen:
                duplicates[p['id']] = seen[key]
            elif key:
                seen[key] = p['id']
    section_cache={}
    for p in people:
        text = texts[p['id']]
        f = selections[p['id']]
        anomalies = list(f['anomalies'])
        for observation in p['observations']:
            if observation.get('source_kind')=='image_person_card':
                from image_profiles import verify_observation
                anomalies.extend(verify_observation(cat,root,observation))
        if administrative_only(text,f['title']['value']):
            anomalies.append('正文仅见行政或教辅岗位，教师任职关系需要核实')
        from roster_sections import administrative_roster_proof
        from quality_fields import teaching_evidence
        section_proof=administrative_roster_proof(cat,root,p,section_cache)
        if section_proof and not f['title']['value'] and not teaching_evidence(text):
            anomalies.append('仅列于行政教辅分组，尚无明确教学科研任职依据')
        source_kind = [o.get('source_kind') for o in p['observations']]
        row_bound = any(x in ('pdf_table_row','html_table_row') for x in source_kind)
        identity_ok = row_bound or compact(p['name']) in compact(p.get('page_title','')) or compact(text).startswith(compact(p['name'])) or ('姓名:'+compact(p['name'])) in compact(text[:220])
        header_identity=biography_identity_after_metadata(p['name'],text) if p['profile_url'] else None
        identity_ok=identity_ok or bool(header_identity)
        if not text:
            anomalies.append('尚未取得本人正文')
        if text and not identity_ok:
            anomalies.append('页面与姓名归属不明确')
        if text and len(compact(text))<25:
            anomalies.append('正文过短，可能遗漏')
        # A name-only overview remains unresolved, but does not by itself
        # contradict an independently identified personal page. Do not merge it.
        distinct = [x for x in by_name[p['name']] if x['id'] not in duplicates and (texts[x['id']] or x['profile_url'])]
        if len(distinct)>1:
            anomalies.append('同名不同材料，需要核对身份或新旧版本')
        if any(o.get('historical_roster') for o in p['observations']):
            anomalies.append('旧名单：当前任职关系需要核对')
        for e in f['email_candidates']:
            if len(email_names[e['value'].lower()])>=3:
                anomalies.append('邮箱出现在不同姓名材料中，可能为公共或合作邮箱')
                f['email']['value']='; '.join(x for x in f['email']['value'].split('; ') if x.lower()!=e['value'].lower())
        image_assessments = image_checks[p['id']]
        if any(m['review_required'] for m in image_assessments):
            anomalies.append('图片资料用途或文字识别需要核对')
        for d in p.get('pdfs',[]):
            if docs.get(d,{}).get('ocr_pages'):
                parsed=read(root/d/'pdf-text.json',{})
                if any(pg.get('low_confidence_lines',0)>max(1,len(pg.get('lines',[]))*.1) for pg in parsed.get('pages',[])):
                    anomalies.append('扫描 PDF 有低置信度识别')
        failures = [i for i in cat['issues'] if same_url(i.get('source_page') or i.get('url'),p.get('profile_url'))
                    and i['issue_kind'] in ('image_ocr_failed','image_limit','profile_pdf_failed','request_failed','processing_failed')
                    and i['id'] not in fixed_pdf
                    and 'spacer.gif' not in i.get('url','')]
        if failures:
            anomalies.append('本人材料仍有附件或页面读取失败')
        fields={'name':p['name'],'title':f['title']['value'],'email':f['email']['value'],
                'profile_url':p.get('profile_url',''),'biography':text,'missing':{}}
        for key in ('title','email','profile_url','biography'):
            if not fields[key]:
                fields['missing'][key]='not_stated_in_source' if text else ('access_failed' if any(i['issue_kind']=='request_failed' and same_url(i['url'],p.get('profile_url')) for i in cat['issues']) else 'not_read')
        title_conflict=page_conflicts.get(same_url_key(p.get('profile_url','')))
        if title_conflict:fields['missing']['title']='conflict'
        status='pending' if anomalies else 'auto_accepted'
        if p['id'] in duplicates:
            status='duplicate'
            anomalies=['同姓名且本人正文完全一致，已关联保留条目']
        items[p['id']]={'status':status,'actor':'自动规则 '+POLICY,'policy':POLICY,'fields':fields,
                       'name_normalization':p.get('name_normalization'),
                       'administrative_section':section_proof,
                       'selection':f,'anomalies':list(dict.fromkeys(anomalies)), 'image_assessments':image_assessments,
                       'reason':'；'.join(anomalies) if anomalies else '官网名单来源、本人正文归属及字段依据通过自动检查',
                       'evidence':'\n'.join([*p['sources'],p.get('profile_url',''),p.get('body_path','')]),
                       'body_sha256':hashlib.sha256(original_texts[p['id']].encode()).hexdigest(),
                       'canonical_id':duplicates.get(p['id']), 'checks':{}}
        if text != original_texts[p['id']]:
            items[p['id']]['delivery_text_sha256'] = hashlib.sha256(text.encode()).hexdigest()
            items[p['id']]['delivery_notes']=[{'code':'artwork_ocr_separated','message':'明确作品栏目中的书画 OCR 未并入交付简介；原图、原始正文与识别记录均保留'}]
        if title_conflict:
            items[p['id']].setdefault('delivery_notes',[]).append({'code':'title_conflict','message':'本人信息卡与简介职称不一致（'+title_conflict['card']['value']+' / '+title_conflict['biography']['value']+'），职称单独待核；其他已确认字段照常交付'})
    for issue in cat['issues']:
        kind=issue['issue_kind']
        reason=None
        if issue['id'] in fixed_pdf:
            reason='已取得该 PDF，或该失败地址只是附件显示名称误解析的伪链接；真实附件原件保留'
        elif kind=='profile_without_text':
            if any(same_url(p['profile_url'],issue['url']) and texts[p['id']] for p in people):
                reason='补读已取得个人页正文'
        elif kind=='source_not_faculty_roster':
            reason='已排除非名单页面；排除结果不表示学院没有师资'
        elif kind=='out_of_host_scope' and issue.get('url','').startswith('javascript:'):
            reason='导航占位链接，无可请求的个人页面'
        elif kind=='image_ocr_failed' and 'spacer.gif' in issue.get('url',''):
            reason='编辑器透明占位图片，不含简历正文'
        elif kind=='ocr_review_required':
            matching=[p for p in people if same_url(p['profile_url'],issue['url'])]
            assessments={m['directory']:m for p in matching for m in items[p['id']]['image_assessments']}
            referenced=issue.get('media',[]) or list(assessments)
            evaluated=[assessments[d] for d in referenced if d in assessments]
            complete=bool(evaluated) and len(evaluated)==len(referenced)
            resolved=complete and not any(m['review_required'] for m in evaluated)
            reason=('照片场景或零碎文字不影响本人材料，其他图片 OCR 质量检查通过；原图与文字均保留'
                    if resolved else '图片可能承载个人资料，或尚无法排除资料遗漏；请对照下方原图')
            items[issue['id']]={'status':'resolved' if resolved else 'pending','actor':'自动规则 '+POLICY,
                               'policy':POLICY,'reason':reason,'evidence':issue['url'],
                               'automatic':True,'image_assessments':evaluated}
            continue
        elif kind=='pdf_ocr_review_required':
            matching=[p for p in people if same_url(p['profile_url'],issue['url'])]
            if matching and all(not any('识别' in a or '读取失败' in a for a in items[p['id']]['anomalies']) for p in matching):
                reason='PDF OCR 质量检查通过；原件与文字均保留'
        elif kind=='name_evidence_rejected':
            if any(p['name']==issue.get('name') and issue['url'] in p['sources'] for p in people):
                reason='已从同一名单的真实姓名链接恢复该条目'
        elif kind=='non_person_directory_entry':
            if any(same_url(p['profile_url'],issue.get('document_url')) or any(o.get('source_kind')=='html_table_row' and o['source_url']==issue.get('document_url') for o in p['observations']) for p in people):
                reason='已从原名单恢复人员姓名或链接；正文是否已读以人员记录为准'
        elif kind=='person_link_rejected':
            if any(p['name']==issue.get('name') and issue['url'] in p['sources'] and p['profile_url'] and texts[p['id']] for p in people):
                reason='真实姓名链接已恢复，个人材料已读取'
        elif kind=='out_of_host_scope':
            if any(p.get('original_profile_url')==issue['url'] and p['profile_url']!=issue['url'] and texts[p['id']] for p in people):
                reason='已从 CMS 包装链接中恢复同域官方个人地址'
        elif kind=='document_without_supported_attachment':
            if any(p['profile_url']==issue['url'] or any(o.get('source_kind')=='html_table_row' and o['source_url']==issue['url'] for o in p['observations']) for p in people):
                reason='该地址已识别为个人页或 HTML 教师表格，改按对应格式处理；正文状态见人员记录'
        if reason:
            items[issue['id']]={'status':'resolved','actor':'自动规则 '+POLICY,'policy':POLICY,
                                'reason':reason,'evidence':issue['url'],'automatic':True}
    from roster_tables import apply_table_rows
    apply_table_rows(cat,root,items)
    apply_delivery(cat, root, items)
    associate(cat, root, items)
    apply_roster_only(cat, root, items)
    from grouped_roster import apply_source_exclusions
    apply_source_exclusions(cat,root,items)
    return {'policy':POLICY,'created':datetime.now(timezone.utc).isoformat(),'fingerprint':assessment_fingerprint(root),
            'items':items,'counts':dict(Counter(items[p['id']]['status'] for p in people)),
            'note':'规则分值用于证据排序，不是统计正确率；未发现异常不等于学院名单完整。'}


def replace_assessment(temp,destination):
    """Windows readers may briefly hold the old cache without delete sharing."""
    for attempt in range(5):
        try:
            temp.replace(destination)
            return
        except PermissionError:
            if attempt==4:
                # Only our unique temporary file is cleaned. Preserve the last
                # complete assessment and surface a persistent failure.
                try:temp.unlink(missing_ok=True)
                except OSError:pass
                raise
            time.sleep(.05*(2**attempt))


def build(store,key,force=False,summary_only=False):
    job=store.job(key)
    if job['state'] in ('running','queued') or not job['run_dir']:
        return None
    root=Path(job['run_dir'])
    if force:
        _file_digest.cache_clear()
        assessment_fingerprint(root,force=True)
    if summary_only and not force:
        snapshot=read(root/'review-summary.json',{})
        if snapshot and snapshot.get('fingerprint')==assessment_fingerprint(root):return snapshot
    previous=read(root/'auto-assessment.json',{})
    if not force and previous.get('fingerprint')==assessment_fingerprint(root):
        if not (root/'review-summary.json').is_file():
            write_review_summary(root,store.catalog(key,apply_auto=False),previous)
        return previous
    cat=store.catalog(key,apply_auto=False)
    value=assess(cat,root)
    serial=json.dumps(value,ensure_ascii=False,indent=2)
    digest=hashlib.sha256(serial.encode()).hexdigest()[:16]
    folder=root/'assessments';folder.mkdir(exist_ok=True)
    (folder/(digest+'.json')).write_text(serial,encoding='utf-8')
    temp=root/('auto-assessment-'+uuid.uuid4().hex+'.tmp');temp.write_text(serial,encoding='utf-8')
    replace_assessment(temp,root/'auto-assessment.json')
    write_review_summary(root,cat,value)
    return value

def write_review_summary(root,cat,assessment):
    """Small status index for the monitor; human decisions are overlaid at read time."""
    value={'fingerprint':assessment['fingerprint'],'policy':assessment.get('policy'),'counts':assessment.get('counts',{}),'items':{
        p['id']:{'kind':p['kind'],'status':assessment.get('items',{}).get(p['id'],{}).get('status','pending')}
        for p in cat['people']+cat['issues']}}
    temp=root/('review-summary-'+uuid.uuid4().hex+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False),encoding='utf8')
    replace_assessment(temp,root/'review-summary.json')


if __name__=='__main__':
    from workbench_store import Store,ROOT
    parser=argparse.ArgumentParser();parser.add_argument('--job',action='append');args=parser.parse_args()
    store=Store(ROOT/'runs/workbench/workbench.db')
    with store.db() as con:
        jobs=[dict(x) for x in con.execute('SELECT * FROM jobs ORDER BY created')]
    latest={json.loads(j['target'])['college']:j['id'] for j in jobs}
    for key in args.job or latest.values():
        result=build(store,key)
        if result: print(key,result['counts'])
