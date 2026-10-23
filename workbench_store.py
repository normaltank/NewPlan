"""SQLite jobs and append-only, revision-checked review decisions; separate from MyPlan."""
import hashlib
import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse,parse_qs,urljoin
from batch_input import validate_target

ROOT = Path(__file__).resolve().parent


def now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (FileNotFoundError, ValueError, PermissionError):
        return default


def identity(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()[:20]


class Conflict(ValueError):
    pass


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as con:
            con.executescript('''
            CREATE TABLE IF NOT EXISTS batches(id TEXT PRIMARY KEY,name TEXT,created TEXT);
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,batch_id TEXT,target TEXT,state TEXT,
              created TEXT,started TEXT,finished TEXT,run_dir TEXT,error TEXT,parent_id TEXT);
            CREATE TABLE IF NOT EXISTS decisions(job_id TEXT,item_id TEXT,revision INTEGER,payload TEXT,
              PRIMARY KEY(job_id,item_id));
            CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,job_id TEXT,item_id TEXT,
              revision INTEGER,actor TEXT,created TEXT,payload TEXT);
            CREATE TABLE IF NOT EXISTS manual_people(job_id TEXT,id TEXT,payload TEXT,PRIMARY KEY(job_id,id));
            CREATE TABLE IF NOT EXISTS schedule_runs(day TEXT PRIMARY KEY,batch_id TEXT);
            CREATE TABLE IF NOT EXISTS batch_requests(request_id TEXT PRIMARY KEY,batch_id TEXT,payload_hash TEXT);
            ''')

    @contextmanager
    def db(self):
        con = sqlite3.connect(self.path, timeout=20)
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA journal_mode=WAL')
        try:
            with con:
                yield con
        finally:
            con.close()

    @staticmethod
    def validate_target(target):
        validate_target(target)

    def create_batch(self, name, targets, request_id=None):
        if not isinstance(targets,list):
            raise ValueError('学院数据必须为列表')
        if not 1 <= len(targets) <= 100:
            raise ValueError('每批 1–100 个学院')
        if not isinstance(name,str) or not name.strip():
            raise ValueError('请填写批次名称')
        for t in targets:
            self.validate_target(t)
        if request_id is not None and (not isinstance(request_id,str) or not 8<=len(request_id)<=128):
            raise ValueError('无效的提交标识')
        payload_hash=identity(name,targets)
        batch = uuid.uuid4().hex[:16]
        with self.db() as con:
            con.execute('BEGIN IMMEDIATE')
            if request_id:
                previous=con.execute('SELECT * FROM batch_requests WHERE request_id=?',(request_id,)).fetchone()
                if previous:
                    if previous['payload_hash']!=payload_hash:
                        raise Conflict('该提交已创建批次，请关闭后重新新建，或查看已创建的任务')
                    return previous['batch_id']
            con.execute('INSERT INTO batches VALUES(?,?,?)', (batch, name[:120], now()))
            for t in targets:
                self._insert_job(con, batch, t)
            if request_id:
                con.execute('INSERT INTO batch_requests VALUES(?,?,?)',(request_id,batch,payload_hash))
        return batch

    def batch_catalogs(self, key):
        with self.db() as con:
            batch=con.execute('SELECT * FROM batches WHERE id=?',(key,)).fetchone()
            if not batch:
                raise KeyError('采集批次不存在')
            keys=[r['id'] for r in con.execute('''SELECT j.id FROM jobs j WHERE j.batch_id=?
                AND NOT EXISTS (SELECT 1 FROM jobs child WHERE child.parent_id=j.id)
                ORDER BY j.created,j.id''',(key,))]
        return dict(batch),[self.catalog(job) for job in keys]

    def _insert_job(self, con, batch, target, parent=None):
        key = uuid.uuid4().hex[:16]
        con.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?)',
                    (key, batch, json.dumps(target, ensure_ascii=False), 'queued', now(), None, None, None, None, parent))
        return key

    def job(self, key):
        with self.db() as con:
            row = con.execute('SELECT * FROM jobs WHERE id=?', (key,)).fetchone()
        if not row:
            raise KeyError('采集任务不存在')
        result = dict(row)
        result['target'] = json.loads(result['target'])
        return result

    def update(self, key, **fields):
        if not set(fields) <= {'state', 'started', 'finished', 'run_dir', 'error'}:
            raise ValueError('Invalid update')
        with self.db() as con:
            con.execute('UPDATE jobs SET ' + ','.join(k + '=?' for k in fields) + ' WHERE id=?',
                        (*fields.values(), key))

    def claim(self):
        with self.db() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute("SELECT id FROM jobs WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
            if not row:
                return None
            con.execute("UPDATE jobs SET state='running',started=? WHERE id=?", (now(), row['id']))
        return self.job(row['id'])

    def interrupted(self):
        with self.db() as con:
            con.execute("UPDATE jobs SET state='interrupted',finished=?,error='工作进程中断；可创建新运行重采' WHERE state='running'", (now(),))

    def rerun(self, key, entries, actor, reason):
        job = self.job(key)
        if job['state'] in ('queued', 'running'):
            raise ValueError('正在采集的学院请等待本次结束')
        target = {**job['target'], 'entries': list(dict.fromkeys([*job['target'].get('entries', []), *entries]))}
        target.pop('resume_from',None);target.pop('prioritize',None)
        self.validate_target(target)
        if not actor.strip() or not reason.strip():
            raise ValueError('请填写复核人和补采原因')
        with self.db() as con:
            child = self._insert_job(con, job['batch_id'], target, key)
            con.execute('INSERT INTO audit(job_id,item_id,revision,actor,created,payload) VALUES(?,?,?,?,?,?)',
                        (key, '__rerun__', 0, actor, now(), json.dumps({'child': child, 'entries': entries, 'reason': reason}, ensure_ascii=False)))
        return child

    def continue_run(self,key,actor,max_pages=200,max_calls=20):
        job=self.job(key)
        if job['state'] in ('queued','running'):raise Conflict('请等待本轮结束后续采')
        if not isinstance(actor,str) or not actor.strip():raise ValueError('请填写操作人姓名')
        if type(max_pages)!=int or not 1<=max_pages<=1000 or type(max_calls)!=int or not 1<=max_calls<=100:
            raise ValueError('每轮页数为 1–1000，API 调用上限为 1–100')
        root=Path(job['run_dir']) if job['run_dir'] else None
        if root is None or not (root/'targets.json').is_file():raise ValueError('没有可续采的保存队列')
        target={**job['target'],'resume_from':str(root),'max_pages':max_pages,'max_calls':max_calls}
        target.pop('prioritize',None)
        with self.db() as con:
            con.execute('BEGIN IMMEDIATE')
            if con.execute('SELECT 1 FROM jobs WHERE parent_id=?',(key,)).fetchone():
                raise Conflict('此运行已有后续任务，请进入最新运行再续采')
            child=self._insert_job(con,job['batch_id'],target,key)
            con.execute('INSERT INTO audit(job_id,item_id,revision,actor,created,payload) VALUES(?,?,?,?,?,?)',
                        (key,'__continue__',0,actor,now(),json.dumps({'child':child,'max_pages':max_pages,'max_calls':max_calls},ensure_ascii=False)))
        return child

    def carry_unchanged_reviews(self,key):
        """Reuse decisions only when the person's saved identity/material is unchanged."""
        job=self.job(key)
        if not job['parent_id'] or not job['target'].get('resume_from'):return
        with self.db() as con:
            con.execute('INSERT OR IGNORE INTO manual_people SELECT ?,id,payload FROM manual_people WHERE job_id=?',(key,job['parent_id']))
        before=self.catalog(job['parent_id'],apply_auto=False);after=self.catalog(key,apply_auto=False)
        oldroot=Path(before['job']['run_dir']);newroot=Path(job['run_dir'])
        newer={p['id']:p for p in after['people']}
        eligible={i['id'] for i in after['issues']}&{i['id'] for i in before['issues']}
        def material(root,p):
            data={k:p.get(k) for k in ('name','profile_url','sources','observations','body_status','body_path','media','pdfs','page_title')}
            for field in ('raw_path','body_path'):
                path=root/p[field] if p.get(field) else None
                data[field]=hashlib.sha256(path.read_bytes()).hexdigest() if path and path.is_file() else None
            return data
        for p in before['people']:
            if p['id'] in newer and material(oldroot,p)==material(newroot,newer[p['id']]):eligible.add(p['id'])
        with self.db() as con:
            for row in con.execute('SELECT * FROM decisions WHERE job_id=?',(job['parent_id'],)).fetchall():
                if row['item_id'] not in eligible:continue
                payload=json.loads(row['payload'])
                payload['inherited_from']={'job_id':job['parent_id'],'revision':row['revision'],'rule':'unchanged_saved_material'}
                encoded=json.dumps(payload,ensure_ascii=False)
                inserted=con.execute('INSERT OR IGNORE INTO decisions VALUES(?,?,?,?)',(key,row['item_id'],1,encoded)).rowcount
                if inserted:con.execute('INSERT INTO audit(job_id,item_id,revision,actor,created,payload) VALUES(?,?,?,?,?,?)',
                                        (key,row['item_id'],1,payload.get('actor',''),now(),encoded))

    def catalog(self, key, apply_auto=True):
        job = self.job(key)
        root = Path(job['run_dir']) if job['run_dir'] else None
        observations = read_json(root / 'observations.json', []) if root else []
        pages = read_json(root / 'pages.json', []) if root else []
        enrichment = read_json(root / 'enrichment.json', {}) if root else {}
        observations = observations + enrichment.get('observations', [])
        pages = [{**p, **enrichment.get('pages', {}).get(p['url'], {})} for p in pages]
        pages.extend(enrichment.get('extra_pages', []))
        def canonical(u):
            nested=re.search(r'/folder/react/(https?://[^\s]+)',u)
            if nested and urlparse(nested[1]).netloc==urlparse(job['target']['url']).netloc:
                u=nested[1]
            return u.split('#')[0].replace('http://','https://',1)
        pages_by_url = {canonical(p['url']): p for p in pages}
        grouped = {}
        for o in observations:
            # Same name alone never merges different personal URLs.
            ident = identity('person', o['name'], o.get('profile_url') or o['source_url'])
            if ident not in grouped:
                profile_url=canonical(o.get('profile_url',''))
                if not profile_url:
                    bound={canonical(a['profile_url']) for a in enrichment.get('observations',[]) if a.get('profile_url')
                           and a['name']==o['name'] and a['source_url']==o['source_url'] and a.get('source_kind')=='saved_roster_anchor'}
                    if len(bound)==1:profile_url=next(iter(bound))
                page = pages_by_url.get(profile_url, {})
                grouped[ident] = {'id': ident, 'kind': 'person', 'name': o['name'], 'profile_url': profile_url,
                    'original_profile_url':o.get('profile_url',''),
                    'sources': [], 'observations': [], 'body_status': page.get('body_status', 'not_read'),
                    'body_path': o.get('person_body_path') or page.get('body_path') or ((page['directory'] + '/body-text.txt') if page.get('body_chars') else ''),
                    'raw_path': (page['directory'] + '/source.html') if page else ((pages_by_url[canonical(o['source_url'])]['directory']+'/source.html') if o.get('person_image') and canonical(o['source_url']) in pages_by_url else ''),
                    'media': o.get('person_media') or o.get('table_media') or page.get('ocr_media', []), 'pdfs':([o['attachment_path']] if o.get('attachment_path') else page.get('profile_pdfs',[])), 'emails': page.get('email_candidates', []),
                    'titles': page.get('title_candidates', []), 'page_title':page.get('title',''), 'flags': []}
            p = grouped[ident]
            if o['source_url'] not in p['sources']:
                p['sources'].append(o['source_url'])
            p['observations'].append(o)
        people = list(grouped.values())
        by_name = {}
        for p in people:
            by_name[p['name']] = by_name.get(p['name'], 0) + 1
        for p in people:
            if by_name[p['name']] > 1:
                p['flags'].append('同名多来源 / 身份待确认')
            if not p['body_path']:
                p['flags'].append('正文未取得')
            if p['media']:
                p['flags'].append('OCR 原图待核')
        issues = (read_json(root / 'issues.json', []) if root else []) + enrichment.get('issues',[])
        documents=(read_json(root / 'documents.json',[]) if root else []) + enrichment.get('documents',[])
        events=[]
        problems = []
        problem_ids=set()
        for issue in issues:
            if issue['kind']=='browser_render_attempt' or (issue['kind']=='plan_repair_attempt' and issue.get('fixed')):
                events.append(issue)
                continue
            if issue['kind']=='profile_pdf_failed':
                file=parse_qs(urlparse(issue['url']).query).get('file',[])
                if file and any(d['url']==urljoin(issue['url'],file[0]) and d.get('text_chars',0)>0 for d in documents):
                    events.append({**issue,'explanation':'PDF播放器HTML被误当附件请求；其指向的实际PDF已保存并读取，依据见documents.json'})
                    continue
            ident = identity('issue', issue)
            if ident not in problem_ids:
                problem_ids.add(ident)
                problems.append({'id': ident, 'kind': 'issue', **issue})
                problems[-1]['issue_kind'] = issue['kind']
                problems[-1]['kind'] = 'issue'
        if job['state'] not in ('running', 'queued') and not people:
            problems.append({'id': 'empty-result', 'kind': 'issue', 'issue_kind': 'no_candidates',
                             'url': job['target']['url'], 'detail': '没有获得人员不代表没有师资，需核对入口及官网说明。'})
        with self.db() as con:
            decisions = {r['item_id']: {'revision': r['revision'], **json.loads(r['payload'])}
                         for r in con.execute('SELECT * FROM decisions WHERE job_id=?', (key,))}
            people.extend(json.loads(r['payload']) for r in con.execute('SELECT payload FROM manual_people WHERE job_id=?', (key,)))
        for p in people + problems:
            p['review'] = decisions.get(p['id'], {'revision': 0, 'status': 'pending'})
        automated=read_json(root/'auto-assessment.json',{}) if root and apply_auto else {}
        if automated and job['state'] not in ('running','queued'):
            from quality_pipeline import assessment_fingerprint
            if automated.get('fingerprint')!=assessment_fingerprint(root):
                automated={}
        for p in people + problems:
            if p['id'] in automated.get('items',{}):
                p['automatic']=automated['items'][p['id']]
                if p['id'] not in decisions:
                    p['review']={'revision':0,**p['automatic']}
                if p['kind']=='person':
                    p['flags']=p['automatic'].get('anomalies',[])
                    p['titles']=[x['value'] for x in p['automatic'].get('selection',{}).get('title_candidates',[])]
                    p['emails']=[x['value'] for x in p['automatic'].get('selection',{}).get('email_candidates',[])]
        return {'job': job, 'people': people, 'issues': problems,
                'college_review': decisions.get('__college__', {'revision': 0, 'status': 'unverified'}),
                'rosters': (read_json(root / 'roster-pages.json', []) if root else []) + enrichment.get('rosters',[]),
                'discovery': read_json(root / 'discovery.json', {}) if root else {},
                'pages': [{k:v for k,v in p.items() if k!='links'} for p in pages],
                'media': (read_json(root / 'media.json', []) if root else []) + enrichment.get('media',[]),
                'documents': documents,'events':events,'automation':{k:v for k,v in automated.items() if k!='items'},
                'enrichment':enrichment.get('report',{}),
                'progress': read_json(root / 'progress.json', {}) if root else {},
                'summary': read_json(root / 'summary.json', {}) if root else {}}

    def listing(self):
        with self.db() as con:
            batches = [dict(r) for r in con.execute('SELECT * FROM batches ORDER BY created DESC')]
            rows = [dict(r) for r in con.execute('SELECT * FROM jobs ORDER BY created')]
            decisions={}
            for row in con.execute('SELECT * FROM decisions'):
                decisions.setdefault(row['job_id'],{})[row['item_id']]=json.loads(row['payload'])
            manual={}
            for row in con.execute('SELECT job_id,id FROM manual_people'):
                manual.setdefault(row['job_id'],set()).add(row['id'])
        jobs = []
        for job in rows:
            key=job['id'];job['target']=json.loads(job['target']);root=Path(job['run_dir']) if job['run_dir'] else None
            snapshot=read_json(root/'review-summary.json',{}) if root else {}
            statistics_source='live'
            if snapshot and job['state'] not in ('running','queued'):
                # The overview can show explicitly labelled last-check counts. Full
                # source/field validation remains on the review and export paths.
                # Even checking the fingerprint stats thousands of saved files.
                # Background assessment owns freshness; overview counts are snapshots.
                statistics_source='last_check'
                statuses=snapshot['items']
                for ident in manual.get(key,set()):statuses.setdefault(ident,{'kind':'person','status':'pending'})
                for ident,decision in decisions.get(key,{}).items():
                    if ident in statuses:statuses[ident]['status']=decision['status']
                people=[p for p in statuses.values() if p['kind']=='person'];problems=[p for p in statuses.values() if p['kind']=='issue']
                progress=read_json(root/'progress.json',{});summary=read_json(root/'summary.json',{})
                review_status=decisions.get(key,{}).get('__college__',{}).get('status','unverified')
            else:
                cat=self.catalog(key);people=[p['review'] for p in cat['people']];problems=[p['review'] for p in cat['issues']]
                progress=cat['progress'];summary=cat['summary'];review_status=cat['college_review']['status']
            jobs.append({**job,'progress':progress,'summary':summary,'people_count':len(people),'issue_count':len(problems),
                         'pending':sum(p['status'] in ('pending','needs_followup') for p in people+problems),
                         'accepted':sum(p['status'] in ('accepted','auto_accepted') for p in people),
                         'auto_accepted':sum(p['status']=='auto_accepted' for p in people),
                         'statistics_source':statistics_source,
                         'review_status':review_status,'review_url':'/review/'+key})
        return {'batches': batches, 'jobs': jobs}

    def decide(self, key, item_id, payload):
        with self.db() as con:
            con.execute('BEGIN IMMEDIATE')
            return self._decide(con, key, item_id, payload)

    def decide_many(self, key, payload):
        items=payload.get('items')
        status=payload.get('status')
        if not isinstance(items,list) or not 1<=len(items)<=5000:
            raise ValueError('请选择 1–5000 个复核条目')
        if any(not isinstance(i,dict) or not isinstance(i.get('id'),str) or not isinstance(i.get('revision'),int) for i in items):
            raise ValueError('条目及版本格式无效，请刷新')
        if len({i['id'] for i in items})!=len(items):
            raise ValueError('同一条目不能重复提交')
        if status not in ('accepted','excluded','resolved','needs_followup'):
            raise ValueError('无效的批量复核决定')
        bulk_id=uuid.uuid4().hex
        with self.db() as con:
            con.execute('BEGIN IMMEDIATE')
            cat=self.catalog(key)
            available={p['id']:p for p in cat['people']+cat['issues']}
            kinds={available[i['id']]['kind'] for i in items if i['id'] in available}
            if len(kinds)!=1 or any(i['id'] not in available for i in items):
                raise ValueError('请在同一标签中选择有效条目')
            results=[]
            for selected in items:
                item=available[selected['id']]
                if status=='accepted':
                    if item['kind']!='person' or item['review']['status'] in ('duplicate','excluded'):
                        raise ValueError('批量确认仅适用于未排除、未关联为重复的人员；恢复此类记录请单独核对')
                    if not isinstance(selected.get('fields'),dict):
                        raise ValueError('请先预览每人的字段及缺失原因')
                    if selected['fields']!=item['review'].get('fields',{}):
                        raise Conflict('人员字段或自动判断已变化，请刷新后重新预览')
                evidence='\n'.join(dict.fromkeys(filter(None,[str(payload.get('evidence','')).strip(),
                    *item.get('sources',[]),item.get('profile_url'),item.get('url'),item.get('source_page'),
                    item.get('body_path') or ('运行 '+key+' / 条目 '+item['id'])])))
                data={**item['review'],'actor':payload.get('actor',''),'reason':payload.get('reason',''),
                      'evidence':evidence,'status':status,'revision':selected['revision'],'bulk_id':bulk_id}
                if status=='accepted':
                    data.update(fields=selected['fields'],checks=payload.get('checks',{}))
                results.append({'id':item['id'],**self._decide(con,key,item['id'],data)})
        return {'bulk_id':bulk_id,'count':len(results),'items':results}

    def _decide(self, con, key, item_id, payload):
        cat = self.catalog(key)
        if cat['job']['state'] in ('running', 'queued'):
            raise Conflict('采集仍在进行，可查看证据；请在运行结束后提交复核')
        actor = str(payload.get('actor', '')).strip()
        reason = str(payload.get('reason', '')).strip()
        evidence = str(payload.get('evidence', '')).strip()
        if not actor or not reason or not evidence:
            raise ValueError('请填写复核人、决定依据和证据链接或原件位置')
        status = payload.get('status')
        if item_id == '__college__':
            if status not in ('verified', 'partial', 'no_faculty', 'unverified'):
                raise ValueError('无效的学院结论')
            if status in ('verified', 'no_faculty'):
                required = ('entry_checked', 'branches_checked', 'pagination_checked', 'rows_checked')
                if not all(payload.get('checks', {}).get(c) is True for c in required):
                    raise ValueError('请逐项完成入口、分支、分页和名单条目对账')
                if any(p['review']['status'] not in ('accepted', 'auto_accepted', 'duplicate', 'excluded') for p in cat['people']):
                    raise ValueError('仍有人员未复核')
                if any(p['review']['status'] != 'resolved' for p in cat['issues']):
                    raise ValueError('仍有采集问题未处理')
                if status == 'no_faculty' and any(p['review']['status'] in ('accepted','auto_accepted') for p in cat['people']):
                    raise ValueError('已有确认人员，不能同时确认无师资')
                if status == 'verified' and not any(p['review']['status'] in ('accepted','auto_accepted') for p in cat['people']):
                    raise ValueError('空人员结果请使用有依据的人工确认无师资')
        else:
            item = next((p for p in cat['people'] + cat['issues'] if p['id']==item_id), None)
            if not item:
                raise KeyError('复核条目不存在')
            allowed = ('accepted', 'excluded', 'needs_followup') if item['kind']=='person' else ('resolved', 'needs_followup')
            if status not in allowed:
                raise ValueError('无效的复核决定')
            if status == 'accepted':
                if not all(payload.get('checks', {}).get(c) is True for c in ('identity_checked', 'affiliation_checked', 'fields_checked')):
                    raise ValueError('确认人员前须核对身份、学院归属和所填字段')
                fields = payload.get('fields', {})
                if not str(fields.get('name', '')).strip():
                    raise ValueError('确认姓名不能为空')
                missing = fields.get('missing', {})
                valid_missing = ('not_published', 'not_stated_in_source', 'access_failed', 'not_read', 'uncertain', 'conflict')
                for field in ('title', 'email', 'profile_url', 'biography'):
                    if not fields.get(field) and missing.get(field) not in valid_missing:
                        raise ValueError(f'请记录 {field} 缺失的原因')
        expected = payload.get('revision', 0)
        saved = {k:v for k,v in payload.items() if k != 'revision'}
        saved.update(actor=actor, reason=reason, evidence=evidence, updated_at=now())
        if item_id=='__college__' and status in ('verified','no_faculty'):
            # Recheck under the write lock; a reviewer may have edited while validation ran.
            latest=self.catalog(key)
            if any(p['review']['status'] not in ('accepted','auto_accepted','duplicate','excluded') for p in latest['people']) or any(p['review']['status']!='resolved' for p in latest['issues']):
                raise Conflict('人员或问题状态已变化，请刷新后重新核对')
            accepted=any(p['review']['status'] in ('accepted','auto_accepted') for p in latest['people'])
            if (status=='no_faculty' and accepted) or (status=='verified' and not accepted):
                raise Conflict('人员结论已变化，请重新核对学院结论')
        row = con.execute('SELECT revision FROM decisions WHERE job_id=? AND item_id=?', (key, item_id)).fetchone()
        revision = row['revision'] if row else 0
        if revision != expected:
            raise Conflict('此条目已被其他人修改，请刷新后重新核对')
        revision += 1
        raw = json.dumps(saved, ensure_ascii=False)
        con.execute('INSERT OR REPLACE INTO decisions VALUES(?,?,?,?)', (key, item_id, revision, raw))
        con.execute('INSERT INTO audit(job_id,item_id,revision,actor,created,payload) VALUES(?,?,?,?,?,?)',
                    (key, item_id, revision, actor, now(), raw))
        # Any record revision invalidates a prior college-level final conclusion.
        if item_id != '__college__':
            college = con.execute("SELECT * FROM decisions WHERE job_id=? AND item_id='__college__'", (key,)).fetchone()
            if college:
                old = json.loads(college['payload'])
                if old['status'] in ('verified', 'no_faculty'):
                    old.update(status='unverified', reason='人员或问题复核已变化，学院结论需要重新确认', actor=actor, updated_at=now())
                    raw_college=json.dumps(old,ensure_ascii=False)
                    con.execute("UPDATE decisions SET revision=?,payload=? WHERE job_id=? AND item_id='__college__'", (college['revision']+1,raw_college,key))
                    con.execute('INSERT INTO audit(job_id,item_id,revision,actor,created,payload) VALUES(?,?,?,?,?,?)',
                                (key,'__college__',college['revision']+1,actor,now(),raw_college))
        return {'revision': revision, **saved}

    def add_person(self, key, data):
        cat = self.catalog(key)
        if cat['job']['state'] in ('running', 'queued'):
            raise ValueError('请等采集结束后补充人员')
        if not all(str(data.get(k, '')).strip() for k in ('name', 'source_url', 'actor', 'reason')):
            raise ValueError('姓名、官方证据链接、复核人和补充依据均必填')
        u=urlparse(data['source_url'])
        if u.scheme not in ('http','https') or not u.hostname or not (u.hostname.endswith('.edu.cn') or u.hostname.endswith('.edu')):
            raise ValueError('请提供官方证据链接')
        ident = 'manual-' + uuid.uuid4().hex[:16]
        person = {'id':ident,'kind':'person','name':data['name'],'profile_url':data.get('profile_url',''),
                  'sources':[data['source_url']],'observations':[],'body_status':'manual_pending',
                  'body_path':'','raw_path':'','media':[],'emails':[],'titles':[],'flags':['人工补充 / 尚待确认']}
        with self.db() as con:
            con.execute('INSERT INTO manual_people VALUES(?,?,?)',(key,ident,json.dumps(person,ensure_ascii=False)))
            con.execute('INSERT INTO audit(job_id,item_id,revision,actor,created,payload) VALUES(?,?,?,?,?,?)',
                        (key,ident,0,data['actor'],now(),json.dumps(data,ensure_ascii=False)))
            college=con.execute("SELECT * FROM decisions WHERE job_id=? AND item_id='__college__'",(key,)).fetchone()
            if college:
                old=json.loads(college['payload'])
                old.update(status='unverified',reason='新增人员待核，学院结论需要重新确认',actor=data['actor'],updated_at=now())
                raw=json.dumps(old,ensure_ascii=False)
                con.execute("UPDATE decisions SET revision=?,payload=? WHERE job_id=? AND item_id='__college__'",(college['revision']+1,raw,key))
                con.execute('INSERT INTO audit(job_id,item_id,revision,actor,created,payload) VALUES(?,?,?,?,?,?)',
                            (key,'__college__',college['revision']+1,data['actor'],now(),raw))
        return person

    def history(self,key):
        with self.db() as con:
            return [{**dict(r),'payload':json.loads(r['payload'])} for r in con.execute('SELECT * FROM audit WHERE job_id=? ORDER BY id DESC',(key,))]
