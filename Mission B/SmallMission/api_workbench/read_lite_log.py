"""Maintenance-only: restore recorded evidence without making any network calls."""
import argparse
import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import zlib


def restore(log_path, destination, job_id=None):
    records = [json.loads(line) for line in log_path.read_text(encoding='utf-8').splitlines() if line.strip()]
    ids = [r['job_id'] for r in records if r['event'] == 'run_started']
    if not ids:
        raise ValueError('日志中没有已启动的核验；请查看输入或启动错误记录')
    job_id = job_id or ids[-1]
    if job_id not in ids:
        raise ValueError('日志中没有此任务')
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    selected = [r for r in records if r.get('job_id') == job_id or r['event'] == 'startup']
    for record in selected:
        if record['event'] != 'evidence':
            continue
        relative = PurePosixPath(record['path'])
        path = (destination / 'evidence' / relative).resolve()
        if relative.is_absolute() or '\\' in str(relative) or ':' in str(relative) or not path.is_relative_to(destination / 'evidence'):
            raise ValueError('日志证据路径无效')
        raw = zlib.decompress(base64.b64decode(record['content'], validate=True))
        if hashlib.sha256(raw).hexdigest() != record['sha256']:
            raise ValueError('日志证据校验失败')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    (destination / 'run.json').write_text(json.dumps([r for r in selected if r['event'] != 'evidence'], ensure_ascii=False, indent=2), encoding='utf-8')
    return job_id


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--job-id')
    args = parser.parse_args()
    print(restore(args.log, args.destination, args.job_id))
