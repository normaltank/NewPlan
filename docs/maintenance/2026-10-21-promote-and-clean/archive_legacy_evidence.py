"""Preserve and verify retired server output files before any later removal."""
import hashlib
import json
import os
import time
import zipfile
import io
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
SOURCE = ROOT / 'server/outputs'
DEST = ROOT / 'OpenSource/.local-backups/2026-10-21-promotion/legacy-server-outputs.zip'
if DEST.exists():
    raise RuntimeError('Archive already exists; do not overwrite')
records = []
directories = []
last = time.monotonic()
paths = []
for path, dirs, names in os.walk(SOURCE, followlinks=False):
    current = Path(path)
    directories.append(str(current.relative_to(ROOT)).replace('\\', '/'))
    for name in dirs + names:
        p = current / name
        if p.is_symlink() or p.is_junction():
            raise RuntimeError(f'Reparse point: {p}')
    paths.extend(current / name for name in names)

def read_checked(p):
    before = p.stat()
    data = p.read_bytes()
    after = p.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError(f'Source changed during archive: {p}')
    return {'path': str(p.relative_to(ROOT)).replace('\\', '/'), 'size': after.st_size,
            'mtime_ns': after.st_mtime_ns, 'sha256': hashlib.sha256(data).hexdigest()}, data

class StreamingWriter:
    """Avoid a Windows file flush/seek for every small ZIP entry."""
    def __init__(self, fp): self.fp, self.position = fp, 0
    def write(self, data):
        count = self.fp.write(data)
        self.position += count
        return count
    def tell(self): return self.position
    def seek(self, *args): raise io.UnsupportedOperation('streaming archive')
    def flush(self): self.fp.flush()

with DEST.open('xb', buffering=8 * 1024 * 1024) as fp, ThreadPoolExecutor(max_workers=8) as pool:
    with zipfile.ZipFile(StreamingWriter(fp), 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=3, allowZip64=True) as z:
        pending = deque()
        source_iter = iter(paths)
        for p in list(paths[:24]): pending.append(pool.submit(read_checked, p))
        source_iter = iter(paths[24:])
        while pending:
            record, data = pending.popleft().result()
            z.writestr(record['path'], data)
            records.append(record)
            if (p := next(source_iter, None)) is not None:
                pending.append(pool.submit(read_checked, p))
            if time.monotonic() - last > 20:
                print(json.dumps({'phase': 'archiving', 'files': len(records), 'total': len(paths)}), flush=True)
                last = time.monotonic()
        z.writestr('ARCHIVE_MANIFEST.json', json.dumps({'root': str(ROOT), 'files': records, 'directories': directories}, ensure_ascii=False))
with zipfile.ZipFile(DEST) as z:
    for i, rec in enumerate(records):
        with z.open(rec['path']) as src:
            digest = hashlib.file_digest(src, 'sha256').hexdigest()
        if digest != rec['sha256']:
            raise RuntimeError(f'Archive hash mismatch: {rec["path"]}')
        if time.monotonic() - last > 20:
            print(json.dumps({'phase': 'verifying', 'files': i + 1}), flush=True)
            last = time.monotonic()
report = {'source': str(SOURCE), 'archive': str(DEST), 'source_bytes': sum(r['size'] for r in records),
          'files': len(records), 'archive_bytes': DEST.stat().st_size,
          'archive_sha256': hashlib.file_digest(DEST.open('rb'), 'sha256').hexdigest(), 'verified_all_sha256': True}
(OUT / 'legacy-archive-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False), flush=True)
