"""Snapshot current-project invariants and inventory only explicitly retired paths."""
import hashlib
import json
import os
import shutil
import sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta

OUT = Path(__file__).resolve().parent
APP = OUT.parents[2]
ROOT = APP.parent
OUT.mkdir(parents=True, exist_ok=True)
old_names = ['_archive', '.claude', '.github', '.planning', '.playwright-mcp', '.pytest_cache', '.ruff_cache',
             '.runtime', 'Archived', 'Claude outputs', 'docs', 'Opus', 'scratch', 'scripts', 'server', 'Sheets', 'tests',
             '教师列表.xlsx', '启动自动巡检接单.bat', '双击启动局域网服务.bat', '重启本地服务.bat',
             'AGENT_HANDOVER.md', 'CHANGELOG.md', 'CONSTITUTION.md', 'CONTEXT.md', 'harvest_script.js',
             'pyproject.toml', 'requirements-dev.lock', 'requirements-dev.txt', 'requirements.lock', 'requirements.txt',
             '.agents/plugins']
targets = [(ROOT / name, '旧 MyPlan 业务代码、环境、资料或工具') for name in old_names]
for name in ['documentation-before.zip', 'legacy-server-outputs.zip', 'working-tree-before.patch']:
    targets.append((APP / '.local-backups/2026-10-21-promotion' / name, '用户明确授权删除旧 MyPlan 归档'))

items = []
for target, reason in targets:
    if not target.exists():
        raise RuntimeError(f'Expected legacy target missing: {target}')
    target = target.resolve()
    target.relative_to(ROOT)
    if target in [ROOT, APP, ROOT / '.git', ROOT / '.agents']:
        raise RuntimeError('Protected root')
    files, byte_count, links = 0, 0, []
    stack = [target]
    while stack:
        p = stack.pop()
        if p.is_symlink() or p.is_junction():
            links.append(str(p))
        elif p.is_dir():
            stack.extend(p.iterdir())
        else:
            files += 1
            byte_count += p.stat().st_size
    items.append({'path': str(target), 'relative': str(target.relative_to(ROOT)), 'reason': reason,
                  'files': files, 'bytes': byte_count, 'reparse_points': links, 'directory': target.is_dir()})

source_files = list(APP.glob('*.py')) + list(APP.glob('*.ps1')) + list(APP.glob('*.bat')) + [APP / 'requirements.txt', APP / 'requirements.lock']
source_files += list((APP / 'workbench-static').glob('*'))
source_files += [p for p in (APP / 'fixtures').rglob('*') if p.is_file()]
source_files += [p for p in (APP / '.secrets').glob('*') if p.is_file()]
source_files += list((APP / '.codex').glob('*.toml'))
digests = {str(p.relative_to(APP)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}
db = sqlite3.connect('file:' + str(APP / 'runs/workbench/workbench.db').replace('\\', '/') + '?mode=ro', uri=True)
tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
counts = {t: db.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}
decisions_hash = hashlib.sha256(json.dumps(db.execute('SELECT * FROM decisions').fetchall(), ensure_ascii=False).encode()).hexdigest()
run_paths = [r[0] for r in db.execute('SELECT run_dir FROM jobs') if r[0]]
db.close()

report = {'root': str(ROOT), 'app': str(APP), 'items': items,
          'logical_bytes': sum(i['bytes'] for i in items), 'reparse_points': sum(len(i['reparse_points']) for i in items),
          'protected_source_sha256': digests, 'table_counts': counts, 'decisions_sha256': decisions_hash,
          'job_run_directories': run_paths,
          'disk_free_before': {d: shutil.disk_usage(d).free for d in ['C:/','D:/']},
          'recorded_at': datetime.now(timezone(timedelta(hours=8))).isoformat()}
(OUT / 'retirement-manifest.json').write_bytes(json.dumps(report, ensure_ascii=False, indent=2).encode())
print(json.dumps({'targets': len(items), 'logical_gib': round(report['logical_bytes']/1024**3, 3),
                  'links_to_unlink_without_following': report['reparse_points'], 'protected_files': len(digests)}, ensure_ascii=False), flush=True)
