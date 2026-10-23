"""Read-only application checks and a final storage/documentation report."""
import hashlib
import json
import re
import shutil
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import unquote

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
base = json.loads((OUT / 'baseline.json').read_text(encoding='utf-8'))
report_path = OUT / 'verification.json'
report_path.write_bytes(b'{"status":"checking"}\n')
changed = [name for name, digest in base['source_hashes'].items()
           if not (ROOT / name).exists() or hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest]
assert sorted(changed) == ['.gitignore', 'benchmark.py'], changed

db = sqlite3.connect('file:' + str(ROOT / 'runs/workbench/workbench.db').replace('\\', '/') + '?mode=ro', uri=True)
counts = {table: db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] for table in base['table_counts']}
decision_hash = hashlib.sha256(json.dumps(db.execute('SELECT * FROM decisions').fetchall(), ensure_ascii=False).encode()).hexdigest()
integrity = db.execute('PRAGMA quick_check').fetchone()[0]
run_paths = [row[0] for row in db.execute('SELECT run_dir FROM jobs') if row[0]]
missing_run_paths = [p for p in run_paths if not Path(p).is_dir()]
db.close()
assert counts == base['table_counts']
assert decision_hash == base['review_decisions_sha256']
assert integrity == 'ok'
assert not missing_run_paths, missing_run_paths

fixtures = json.loads((OUT / 'fixture-provenance.json').read_text(encoding='utf-8'))
assert all(hashlib.sha256((ROOT / r['target']).read_bytes()).hexdigest() == r['sha256'] for r in fixtures)
roster = json.loads((OUT / 'replay-check/roster-result.json').read_text(encoding='utf-8'))
assert not roster['missing'] and not roster['extra'] and roster['duplicate_count'] == 0
test_log = (OUT / 'unit-tests.log').read_text(encoding='utf-8-sig')
assert re.search(r'Ran 196 tests in [\d.]+s', test_log) and re.search(r'^OK\s*$', test_log, re.M)

manifest = json.loads((OUT / 'cleanup-manifest.json').read_text(encoding='utf-8'))
assert all(not Path(r['path']).exists() for r in manifest['items'])
release_hashes_match = all(hashlib.sha256((ROOT.parent / r['path']).read_bytes()).hexdigest() == r['sha256']
                           for r in manifest['retained_release_packages'])
assert release_hashes_match
archive = json.loads((OUT / 'legacy-archive-verification.json').read_text(encoding='utf-8'))
assert archive['verified_all_sha256'] and not Path(archive['source']).exists()
assert hashlib.file_digest(Path(archive['archive']).open('rb'), 'sha256').hexdigest() == archive['archive_sha256']

current_docs = [ROOT / p for p in ['README.md','CONTEXT.md','AGENTS.md','AGENT_HANDOVER.md','WORKBENCH.md',
    'docs/README.md','docs/architecture.md','docs/operations.md','docs/review-and-delivery.md',
    'docs/history/README.md','experiments/README.md','fixtures/legacy-replay/README.md']]
current_docs.append(OUT / 'README.md')
broken, checked = [], 0
for file in current_docs:
    text = file.read_text(encoding='utf-8')
    for m in re.finditer(r'\[[^\]\n]*\]\((<[^>]+>|[^\s)]+)\)', text):
        target = m.group(1).strip('<>')
        if re.match(r'^[a-zA-Z][\w+.-]*:|^#', target):
            continue
        path, _, anchor = unquote(target).partition('#')
        resolved = file.parent / path
        checked += 1
        if not resolved.exists():
            broken.append({'file': str(file.relative_to(ROOT)), 'link': target})
        elif anchor and resolved.is_file() and resolved.suffix == '.md':
            headings = re.findall(r'^#+\s+(.+?)\s*$', resolved.read_text(encoding='utf-8'), re.M)
            slugs = [re.sub(r'[^\w\s\-]', '', h.lower()).replace(' ', '-') for h in headings]
            if anchor not in slugs:
                broken.append({'file': str(file.relative_to(ROOT)), 'link': target, 'reason': 'anchor'})
assert not broken, broken

disk_after = {drive: shutil.disk_usage(drive).free for drive in base['disk_free_before']}
result = {
    'checked_at': datetime.now(timezone(timedelta(hours=8))).isoformat(), 'status': 'passed',
    'source_baseline_files': len(base['source_hashes']), 'changed_source_or_config_files': changed,
    'copied_fixtures': len(fixtures), 'tests_passed': 196,
    'replay_roster_reference_count': roster['expected_count'], 'replay_missing': roster['missing'], 'replay_extra': roster['extra'],
    'database_counts': counts, 'database_counts_unchanged': True, 'decision_sha256_unchanged': True,
    'sqlite_quick_check': integrity, 'referenced_job_run_directories_present': len(run_paths),
    'release_packages_unchanged': len(manifest['retained_release_packages']), 'archived_legacy_files': archive['files'],
    'archive_bytes': archive['archive_bytes'], 'archive_verified_all_file_sha256': True,
    'rebuildable_logical_bytes_removed': manifest['logical_bytes'],
    'legacy_logical_bytes_removed': archive['source_bytes'],
    'disk_free_before': base['disk_free_before'], 'disk_free_after': disk_after,
    'disk_free_delta': {d: disk_after[d] - base['disk_free_before'][d] for d in disk_after},
    'current_docs_checked': len(current_docs), 'local_links_checked': checked, 'broken_links': broken,
    'paid_api_calls_this_task': 0, 'real_college_crawls_this_task': 0,
    'limits': ['Disk delta includes concurrent operating-system activity and hard-link effects.',
               'Replay verifies saved samples, not whole-college completeness.',
               'No deployment, Git commit, push, or repository migration performed.'],
}
report_path.write_bytes(json.dumps(result, ensure_ascii=False, indent=2).encode('utf-8'))
print(json.dumps(result, ensure_ascii=False), flush=True)
