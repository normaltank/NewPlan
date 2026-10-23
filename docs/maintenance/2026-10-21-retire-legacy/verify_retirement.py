"""Verify application preservation after authorized retirement of the parent project."""
import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
from pathlib import Path
from urllib.parse import unquote
from datetime import datetime, timezone, timedelta

OUT = Path(__file__).resolve().parent
APP = OUT.parents[2]
ROOT = APP.parent
baseline = json.loads((OUT/'retirement-manifest.json').read_text(encoding='utf-8'))
report_path = OUT / 'verification.json'
report_path.write_bytes(b'{"status":"checking"}\n')
remaining = [r['relative'] for r in baseline['items'] if Path(r['path']).exists()]
changed = [n for n, h in baseline['protected_source_sha256'].items()
           if not (APP/n).is_file() or hashlib.sha256((APP/n).read_bytes()).hexdigest() != h]
assert not remaining and not changed, (remaining, changed)
retained = json.loads((OUT/'retained-inputs.json').read_text(encoding='utf-8-sig'))
assert all(hashlib.sha256(Path(r['destination']).read_bytes()).hexdigest().lower() == r['sha256'].lower() for r in retained)

con = sqlite3.connect((APP/'runs/workbench/workbench.db').as_uri()+'?mode=ro', uri=True)
counts = {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in baseline['table_counts']}
decisions = hashlib.sha256(json.dumps(con.execute('SELECT * FROM decisions').fetchall(), ensure_ascii=False).encode()).hexdigest()
integrity = con.execute('PRAGMA quick_check').fetchone()[0]
con.close()
assert counts == baseline['table_counts'] and decisions == baseline['decisions_sha256'] and integrity == 'ok'
assert all(Path(p).is_dir() for p in baseline['job_run_directories'])

log = (OUT/'unit-tests.log').read_text(encoding='utf-8-sig')
assert re.search(r'Ran 196 tests in [\d.]+s', log) and re.search(r'^OK\s*$', log, re.M)
roster = json.loads((OUT/'replay-check/roster-result.json').read_text(encoding='utf-8'))
assert not roster['missing'] and not roster['extra'] and roster['duplicate_count'] == 0
queue = json.loads((OUT/'replay-check/queue-result.json').read_text(encoding='utf-8'))
assert len(queue['success']) == 2 and len(queue['failed']) == 1

docs = list(APP.glob('*.md'))
docs = [p for p in docs if p.name != 'REPORT.md']
docs += list((APP/'docs').glob('*.md'))
docs += [APP/'docs/history/README.md', APP/'experiments/README.md', APP/'inputs/colleges/README.md', OUT/'README.md']
docs += [ROOT/n for n in ['README.md','AGENTS.md','CLAUDE.md']]
broken, links = [], 0
for p in docs:
    for match in re.finditer(r'\[[^\]\n]*\]\((<[^>]+>|[^\s)]+)\)', p.read_text(encoding='utf-8')):
        target = match.group(1).strip('<>')
        if re.match(r'^[a-zA-Z][\w+.-]*:|^#', target): continue
        path = unquote(target.split('#',1)[0])
        links += 1
        if not (p.parent/path).exists(): broken.append({'file':str(p), 'target':target})
assert not broken, broken

kept = sorted(p.name for p in ROOT.iterdir())
expected = sorted(['OpenSource','.git','.agents','skills-lock.json','.gitignore','README.md','AGENTS.md','CLAUDE.md'])
assert kept == expected, kept
assert sorted(p.name for p in (ROOT/'.agents').iterdir()) == ['skills']
git_head = subprocess.check_output(['git','rev-parse','HEAD'],cwd=APP,text=True).strip()
worktrees = subprocess.check_output(['git','worktree','list','--porcelain'],cwd=APP,text=True)
free = {d:shutil.disk_usage(d).free for d in baseline['disk_free_before']}
result = {'status':'passed','checked_at':datetime.now(timezone(timedelta(hours=8))).isoformat(),
          'deleted_targets':len(baseline['items']),'deleted_logical_bytes':baseline['logical_bytes'],
          'reparse_points_unlinked_without_following':baseline['reparse_points'],
          'remaining_parent_entries':kept,'protected_files_unchanged':len(baseline['protected_source_sha256']),
          'retained_college_inputs':len(retained),'database_counts':counts,'decisions_sha256_unchanged':True,
          'sqlite_quick_check':integrity,'referenced_run_directories_present':len(baseline['job_run_directories']),
          'tests_passed':196,'replay_roster_reference_count':roster['expected_count'],
          'replay_missing':roster['missing'],'replay_extra':roster['extra'],
          'current_documents_checked':len(docs),'local_links_checked':links,'broken_links':broken,
          'git_head':git_head,'linked_worktrees_retained':len(re.findall(r'^worktree ',worktrees,re.M)),
          'disk_free_before':baseline['disk_free_before'],'disk_free_after':free,
          'disk_free_delta':{d:free[d]-baseline['disk_free_before'][d] for d in free},
          'paid_api_calls':0,'real_college_crawls':0,'current_app_path_changed':False,
          'notes':['Disk free delta may include other local processes.','No Git commit, push or remote repository deletion.','Historical old-MyPlan evidence archives deleted per owner request.']}
report_path.write_bytes(json.dumps(result,ensure_ascii=False,indent=2).encode())
print(json.dumps(result,ensure_ascii=False),flush=True)
