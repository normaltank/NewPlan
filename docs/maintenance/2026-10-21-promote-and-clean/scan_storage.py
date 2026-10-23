"""Read-only storage inventory; do not follow junctions or symbolic links."""
import collections
import datetime
import heapq
import json
import os
import pathlib
import shutil
import time

ROOT = pathlib.Path(r'D:\Agent Workspace\Intern\MyPlan').resolve()
OUT = pathlib.Path(__file__).resolve().parent
groups = collections.defaultdict(lambda: {'bytes': 0, 'files': 0})
largest = []
skipped = []
errors = []
started = time.monotonic()
last_progress = started

for top in sorted(ROOT.iterdir()):
    stack = [top]
    while stack:
        path = stack.pop()
        try:
            if path.is_symlink() or path.is_junction():
                skipped.append(str(path.relative_to(ROOT)))
                continue
            if path.is_dir():
                with os.scandir(path) as entries:
                    stack.extend(pathlib.Path(e.path) for e in entries)
                continue
            size = path.stat().st_size
            rel = path.relative_to(ROOT)
            for depth in range(1, min(len(rel.parts), 4) + 1):
                group = '/'.join(rel.parts[:depth])
                groups[group]['bytes'] += size
                groups[group]['files'] += 1
            item = (size, str(rel))
            if len(largest) < 40:
                heapq.heappush(largest, item)
            elif size > largest[0][0]:
                heapq.heapreplace(largest, item)
        except OSError as exc:
            errors.append({'path': str(path), 'error': type(exc).__name__})
        if time.monotonic() - last_progress > 15:
            print(json.dumps({'scanning': top.name, 'elapsed_seconds': round(time.monotonic()-started)}, ensure_ascii=False), flush=True)
            last_progress = time.monotonic()
    if top.is_dir():
        print(json.dumps({'directory': top.name, **groups[top.name]}, ensure_ascii=False), flush=True)

report = {'root': str(ROOT), 'time': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
          'logical_bytes_note': 'Logical file sizes, not allocated blocks; hard links may be counted repeatedly.',
          'groups': dict(groups), 'largest_files': sorted(largest, reverse=True),
          'skipped_reparse_points': skipped, 'errors': errors,
          'disk_free': {drive: shutil.disk_usage(drive).free for drive in ['C:/','D:/']}}
(OUT/'storage-before.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'complete': True, 'elapsed_seconds': round(time.monotonic()-started),'errors': len(errors)}, ensure_ascii=False),flush=True)
