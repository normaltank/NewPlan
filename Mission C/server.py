"""Headless scan/worker entry; the persistent BatchService queue owns all work."""
import argparse
import hashlib
import json
from pathlib import Path
import signal
import threading

from mission_c.batch import BatchService


def scan(service, directory, options):
    directory = directory.resolve()
    if not directory.is_dir():
        raise ValueError('输入目录不存在')
    # Same OS lock as batch workers; concurrent scanners must not import aliases twice.
    with service.worker_lock('input-scan'):
        batches = service.list_batches()
        known = {item['sha256']: batch for batch in batches for item in batch['inputs']}
        report = {'imported': [], 'unchanged': [], 'errors': []}
        for path in sorted(directory.iterdir()):
            if not path.is_file() or path.suffix.lower() != '.xlsx' or path.name.startswith('~$'):
                continue
            try:
                sha = hashlib.sha256(path.read_bytes()).hexdigest()
                batch = known.get(sha)
                if batch is None:
                    batch = service.import_files([path])
                    known[sha] = batch
                    report['imported'].append(batch)
                else:
                    report['unchanged'].append({'file': path.name, 'sha256': sha, 'id': batch['id'], 'issues': batch['issues'], 'state': batch['state'], 'counts': batch['counts'], 'quality_counts': batch['quality_counts']})
                if options and not batch['queued'] and any(t['state'] in {'pending', 'running'} for t in batch['tasks']):
                    if len(batch['inputs']) != 1:
                        report['unchanged'][-1]['not_queued_reason'] = '已有多文件批次；请核对整个批次后用 batch.py enqueue 显式排队'
                        continue
                    batch = service.enqueue(batch['id'], **options)
                    known[sha] = batch
                    for index, item in enumerate(report['imported']):
                        if item['id'] == batch['id']:
                            report['imported'][index] = batch
            except (OSError, ValueError) as error:
                report['errors'].append({'file': path.name, 'error': str(error)})
        return report


def work_once(service):
    report = {'processed': [], 'busy': [], 'errors': []}
    for batch in service.list_batches():
        if not batch['queued'] or batch['paused']:
            continue
        try:
            report['processed'].append(service.run(batch['id']))
        except ValueError as error:
            if str(error) == '批次正在由另一进程执行':
                report['busy'].append(batch['id'])
            else:
                report['errors'].append({'id': batch['id'], 'error': str(error)})
        except OSError as error:
            report['errors'].append({'id': batch['id'], 'error': str(error)})
    return report


def options_parser(parser):
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--cache-manifest', type=Path)
    group.add_argument('--live', action='store_true')
    parser.add_argument('--fetch-mode', choices=['off', 'fallback', 'supplement'], default='off')
    parser.add_argument('--model-mode', choices=['off', 'assist'], default='off')
    parser.add_argument('--allow-paid', action='store_true')
    parser.add_argument('--paid-max-calls', type=int, default=0)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Mission C 无界面扫描与持久队列执行')
    parser.add_argument('--data-root', type=Path, default=Path(__file__).resolve().parent / 'data')
    sub = parser.add_subparsers(dest='command', required=True)
    scanning = sub.add_parser('scan', help='导入新增/变化内容；默认不运行')
    scanning.add_argument('directory', type=Path)
    options_parser(scanning)
    scanning.add_argument('--run', action='store_true', help='扫描后执行已有显式队列')
    worker = sub.add_parser('worker', help='执行共用持久队列')
    worker.add_argument('--once', action='store_true')
    worker.add_argument('--interval', type=float, default=5, help='空闲轮询秒数，默认5')
    watch = sub.add_parser('watch', help='持续扫描输入目录并执行共用队列')
    watch.add_argument('directory', type=Path)
    options_parser(watch)
    watch.add_argument('--interval', type=float, default=5)
    args = parser.parse_args(argv)
    if args.command in {'worker', 'watch'} and args.interval <= 0:
        parser.error('interval 必须大于0')
    if args.command in {'scan', 'watch'}:
        if args.paid_max_calls < 0:
            parser.error('付费预算不能为负数')
        if not (args.cache_manifest or args.live) and (args.fetch_mode != 'off' or args.model_mode != 'off' or args.allow_paid or args.paid_max_calls):
            parser.error('运行选项需要缓存清单或显式 --live')
    try:
        service = BatchService(args.data_root)
        stop = threading.Event()
        if args.command == 'watch' or args.command == 'worker' and not args.once:
            for signum in (signal.SIGINT, signal.SIGTERM):
                signal.signal(signum, lambda *_: stop.set())
        exit_code = 0
        while not stop.is_set():
            if args.command in {'scan', 'watch'}:
                options = {key: getattr(args, key) for key in ('cache_manifest', 'live', 'fetch_mode', 'model_mode', 'allow_paid', 'paid_max_calls')} if args.cache_manifest or args.live else None
                result = scan(service, args.directory, options)
                if args.command == 'watch' or args.run:
                    result['worker'] = work_once(service)
            else:
                result = work_once(service)
            print(json.dumps(result, ensure_ascii=False), flush=True)
            worker_report = result.get('worker', result)
            bad_run = any(any(batch['counts'].get(state, 0) for state in ('failed', 'program_error', 'artifact_missing')) for batch in worker_report.get('processed', []) + result.get('unchanged', []))
            exit_code = max(exit_code, int(bool(result.get('errors') or worker_report.get('errors') or bad_run or any(batch['issues'] for batch in result.get('imported', []) + result.get('unchanged', [])))))
            if args.command == 'scan' or args.command == 'worker' and args.once:
                break
            stop.wait(args.interval)
        return exit_code
    except (OSError, ValueError) as error:
        parser.exit(2, f'{error}\n')


if __name__ == '__main__':
    raise SystemExit(main())

