"""Inventory explicit rebuildable directories; never delete files here."""
import hashlib
import json
import os
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
APP = ROOT / 'OpenSource'
targets = []

def add(path, reason):
    if path.is_dir():
        targets.append((path.resolve(), reason))

for name in ['dev-venv', 'worker-venv']:
    add(ROOT / '.runtime' / name, '旧 MyPlan 可重新安装的 Python 环境')
for base in [APP / 'Mission B/SmallMission', APP / 'Mission B/SmallMission/api_workbench']:
    for child in base.iterdir():
        if child.is_dir() and (child.name in {'.build-cache', '.build-venv', '.build-work', '.build-spec', '.portable-browser'} or child.name.startswith('.release-stage')):
            add(child, 'Mission B 可重建的打包中间目录；正式 ZIP 保留')
    for collection in ['outputs', 'validation']:
        parent = base / collection
        if parent.exists():
            for path, directories, files in os.walk(parent, followlinks=False):
                current = Path(path)
                if current.name.startswith('MissionB-Windows-x64-v'):
                    for name in ['.browsers', '_internal']:
                        add(current / name, '历史解压验证包中的浏览器或依赖副本；验证记录和正式 ZIP 保留')
                    directories[:] = [n for n in directories if n not in {'.browsers', '_internal'}]
for name in ['.browsers', '.venv']:
    add(APP / 'Mission B/SmallMission/.setup-runtime-20261015-180904' / name, '一次性安装验证的浏览器和依赖；verification.json 保留')
add(APP / 'experiments/local-tools-20261018/.uv-cache', '隔离试验的依赖下载缓存；虚拟环境、源码、锁文件和结果保留')

packages = []
for base in [APP / 'Mission B/SmallMission/release', APP / 'Mission B/SmallMission/api_workbench/release']:
    for p in sorted(base.glob('*.zip')):
        with zipfile.ZipFile(p) as z:
            bad = z.testzip()
            if bad:
                raise RuntimeError(f'Corrupt release: {p.name}: {bad}')
        packages.append({'path': str(p.relative_to(ROOT)), 'bytes': p.stat().st_size, 'sha256': hashlib.file_digest(p.open('rb'), 'sha256').hexdigest()})

items = []
for p, reason in targets:
    p.relative_to(ROOT)
    if p == ROOT:
        raise RuntimeError('Root cannot be removed')
    size = count = 0
    for path, dirs, files in os.walk(p, followlinks=False):
        for name in dirs + files:
            child = Path(path) / name
            if child.is_symlink() or child.is_junction():
                raise RuntimeError(f'Reparse point in deletion candidate: {child}')
        for name in files:
            size += (Path(path) / name).stat().st_size
            count += 1
    items.append({'path': str(p), 'relative': str(p.relative_to(ROOT)), 'reason': reason, 'bytes': size, 'files': count})
report = {'root': str(ROOT), 'items': items, 'retained_release_packages': packages, 'logical_bytes': sum(i['bytes'] for i in items)}
(OUT / 'cleanup-manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'targets': len(items), 'logical_gib': round(report['logical_bytes']/1024**3, 3), 'verified_release_zips': len(packages)}), flush=True)
