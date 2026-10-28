"""Persistent Excel batches, shared by CLI, local UI and unattended runners."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import uuid
from urllib.parse import urlsplit, urlunsplit

from openpyxl import load_workbook
from .fetch import valid_url


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stable_url(value):
    parts = urlsplit(valid_url(str(value).strip()))
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or '/', parts.query, ''))


def text(value):
    return '' if value is None else str(value).strip()


def identity(value):
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return text(value)


def preview(paths):
    """Read original two-sheet workbooks. Never fetch URLs or write state."""
    files = []
    for item in paths:
        path = Path(item)
        files.extend(sorted(path.glob('*.xlsx')) if path.is_dir() else [path])
    tasks, issues, inputs = {}, [], []
    for path in files:
        if path.name.startswith('~$'):
            continue
        source = {'file': path.name}
        try:
            sha = digest(path)
            inputs.append({'file': path.name, 'sha256': sha, 'path': str(path.resolve())})
            book = load_workbook(path, read_only=True, data_only=True)
            try:
                if not {'Sheet1', 'Sheet2'} <= set(book.sheetnames):
                    raise ValueError('需要 Sheet1 和 Sheet2')
                headers1 = [text(v) for v in next(book['Sheet1'].values)]
                headers2 = [text(v) for v in next(book['Sheet2'].values)]
                if headers1[:4] != ['ID', '学校', '学院', '师资URL'] or headers2[:2] != ['学院ID', '个人URL']:
                    raise ValueError('表头必须为 ID/学校/学院/师资URL 和 学院ID/个人URL')
                colleges = {}
                for row, values in enumerate(book['Sheet1'].values, 1):
                    if row == 1 or not any(v is not None for v in values): continue
                    ident, school, college, url = (list(values) + [None]*4)[:4]
                    rel = {'id': identity(ident), 'school': text(school), 'college': text(college), 'faculty_urls': [], 'sources': []}
                    location = dict(source, sheet='Sheet1', row=row, sha256=sha)
                    if not rel['id'] or not rel['school'] or not rel['college']:
                        issues.append(dict(location, reason='学院ID/学校/学院缺失')); continue
                    if url: rel['faculty_urls'].append(text(url))
                    rel['sources'].append(location)
                    prior = colleges.get(rel['id'])
                    if prior and (prior['school'], prior['college']) != (rel['school'], rel['college']):
                        prior['conflict'] = True
                        issues.append(dict(location, reason='学院ID关联冲突')); continue
                    if prior:
                        prior['faculty_urls'] = list(dict.fromkeys(prior['faculty_urls'] + rel['faculty_urls']))
                        prior['sources'].append(location)
                    else: colleges[rel['id']] = rel
                for row, values in enumerate(book['Sheet2'].values, 1):
                    if row == 1 or not any(v is not None for v in values): continue
                    ident, url = (list(values) + [None]*2)[:2]
                    location = dict(source, sheet='Sheet2', row=row, sha256=sha, college_id=identity(ident), input_url=text(url))
                    rel = colleges.get(identity(ident))
                    if not rel or rel.get('conflict'):
                        issues.append(dict(location, reason='学院关联缺失或冲突')); continue
                    try: url = stable_url(url)
                    except ValueError as error:
                        issues.append(dict(location, reason=str(error))); continue
                    key = hashlib.sha256((rel['school']+'\0'+url).encode()).hexdigest()
                    task = tasks.setdefault(key, {'id': key, 'school': rel['school'], 'url': url, 'relations': [], 'sources': []})
                    task['sources'].append(location)
                    if rel not in task['relations']: task['relations'].append(rel)
            finally: book.close()
        except (OSError, ValueError, KeyError, StopIteration) as error:
            issues.append(dict(source, reason=str(error)))
        except Exception as error:
            # A malformed workbook is isolated; other files remain importable.
            issues.append(dict(source, reason=f'{type(error).__name__}: {error}'))
    return {'inputs': inputs, 'tasks': list(tasks.values()), 'issues': issues, 'completeness': 'not_verified'}


class BatchService:
    def __init__(self, data_root):
        self.root = Path(data_root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS batches(id TEXT PRIMARY KEY, fingerprint TEXT UNIQUE, payload TEXT, paused INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS tasks(batch TEXT, id TEXT, payload TEXT, state TEXT DEFAULT 'pending', artifact TEXT, error TEXT, PRIMARY KEY(batch,id));''')

    def connect(self):
        db = sqlite3.connect(self.root/'batches.sqlite3', timeout=30)
        db.row_factory = sqlite3.Row
        return db

    def preview(self, paths):
        return preview(paths)

    def import_files(self, paths):
        value = preview(paths)
        fingerprint = hashlib.sha256(json.dumps(sorted((i['file'], i['sha256']) for i in value['inputs'])).encode()).hexdigest()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT id FROM batches WHERE fingerprint=?', (fingerprint,)).fetchone()
            if existing: return self.status(existing['id'])
            batch_id = uuid.uuid4().hex
            for item in value['inputs']:
                target = Path('imports') / batch_id / item['sha256'] / item['file']
                (self.root/target).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(item.pop('path'), self.root/target)
                item['stored_file'] = target.as_posix()
            db.execute('INSERT INTO batches(id,fingerprint,payload) VALUES(?,?,?)', (batch_id, fingerprint, json.dumps(value, ensure_ascii=False)))
            for task in value['tasks']:
                db.execute('INSERT INTO tasks(batch,id,payload) VALUES(?,?,?)', (batch_id,task['id'],json.dumps(task,ensure_ascii=False)))
        return self.status(batch_id)

    def status(self, batch_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM batches WHERE id=?', (batch_id,)).fetchone()
            if row is None: raise ValueError('未知批次')
            result = json.loads(row['payload'])
            result.update(id=batch_id, paused=bool(row['paused']), tasks=[], counts={})
            for taskrow in db.execute('SELECT * FROM tasks WHERE batch=? ORDER BY rowid', (batch_id,)):
                task = json.loads(taskrow['payload'])
                state = taskrow['state']
                task.update(state=state, artifact=taskrow['artifact'], error=taskrow['error'])
                result['tasks'].append(task)
                result['counts'][state] = result['counts'].get(state,0)+1
            result['state'] = 'paused' if result['paused'] else 'pending' if any(t['state'] in {'pending','running'} for t in result['tasks']) else 'completed_with_gaps' if result['issues'] or any(t['state'] != 'success' for t in result['tasks']) else 'completed'
            return result

    def list_batches(self):
        with self.connect() as db: ids = [r['id'] for r in db.execute('SELECT id FROM batches ORDER BY rowid')]
        return [self.status(ident) for ident in ids]

    def pause(self, batch_id):
        self.status(batch_id)
        with self.connect() as db: db.execute('UPDATE batches SET paused=1 WHERE id=?', (batch_id,))
        return self.status(batch_id)

    def resume(self, batch_id):
        self.status(batch_id)
        with self.connect() as db: db.execute('UPDATE batches SET paused=0 WHERE id=?', (batch_id,))
        return self.status(batch_id)
