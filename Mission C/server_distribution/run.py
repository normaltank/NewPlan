"""Portable server CLI; all collection and budgets remain in mission_c."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT if (ROOT / 'mission_c').is_dir() else ROOT.parent))

from mission_c.assisted import atomic_json
from mission_c.batch import BatchService, preview
from mission_c.private_deployment import PrivateDeployment


def configuration(path):
    try:
        value = json.loads(path.read_text(encoding='utf-8-sig'))
        if set(value) != {'input_dir', 'data_dir', 'output_dir', 'interval_seconds'}:
            raise ValueError()
        interval = value['interval_seconds']
        if isinstance(interval, bool) or not isinstance(interval, (int, float)) or not math.isfinite(interval) or interval <= 0:
            raise ValueError()
        result = {'interval_seconds': interval}
        for field in ('input_dir', 'data_dir', 'output_dir'):
            if not isinstance(value[field], str) or not value[field].strip():
                raise ValueError()
            result[field] = (path.parent / value[field]).resolve()
        return result
    except (OSError, ValueError, TypeError):
        raise ValueError('config.json 无效；请检查三个目录和正数扫描间隔') from None


def input_files(config):
    directory = config['input_dir']
    if not directory.is_dir():
        raise ValueError('输入目录不存在；请创建 config.json 指定的输入目录')
    return sorted(p for p in directory.iterdir() if p.is_file() and p.suffix.lower() == '.xlsx' and not p.name.startswith('~$'))


def summary(batch):
    result = {key: batch[key] for key in ('id', 'state', 'counts', 'quality_counts', 'issues', 'queued')}
    result['assistance_errors'] = [dict(url=t['url'], **e) for t in batch['tasks'] for e in t['assistance_errors']]
    result['task_errors'] = [dict(url=t['url'], state=t['state'], error=t['error']) for t in batch['tasks'] if t['error'] or t['state'] == 'artifact_missing']
    return result


def private_queue(batch):
    options = batch['run_options'] or {}
    return (options.get('paid_budget_scope') == batch['id'] and options.get('live') is True
            and options.get('fetch_mode') == 'supplement' and options.get('model_mode') == 'assist'
            and options.get('allow_paid') is True and options.get('paid_max_calls') == 2 * len(batch['tasks'])
            and options.get('cache_manifest') is None)


def import_intent(service, sha):
    return service.root / 'server-import-intents' / (sha + '.json')


def recoverable_import(service, batch):
    """Only our never-started imports may receive their first private scope."""
    if (len(batch['inputs']) != 1 or not batch['tasks'] or batch['queued'] or batch['run_options'] is not None
            or any(t['state'] != 'pending' or t['artifact'] or t['error'] for t in batch['tasks'])):
        return None
    item = batch['inputs'][0]
    try:
        intent = json.loads(import_intent(service, item['sha256']).read_text(encoding='utf-8'))
        if (set(intent) != {'version', 'file', 'sha256', 'batch_id', 'phase'} or intent['version'] != 1
                or intent['file'] != item['file'] or intent['sha256'] != item['sha256']
                or intent['batch_id'] not in (None, batch['id']) or intent['phase'] != 'importing'):
            return None
        urls = {t['url'] for t in batch['tasks']}
        for path in (service.root / 'paid-attempts').glob('*.json'):
            if path.name.startswith(('fetch-', 'model-', 'budget-')):
                attempt = json.loads(path.read_text(encoding='utf-8'))
                if not isinstance(attempt, dict) or attempt.get('url') in urls or attempt.get('scope') == batch['id']:
                    return None
        return intent
    except (OSError, ValueError, TypeError, KeyError):
        return None


def enqueue_import(service, batch, intent):
    marker = import_intent(service, intent['sha256'])
    intent = dict(intent, batch_id=batch['id'])
    atomic_json(marker, intent)
    batch = service.enqueue(batch['id'], first_only=True, private_budget=True, live=True, fetch_mode='supplement',
                            model_mode='assist', allow_paid=True, paid_max_calls=2 * len(batch['tasks']))
    atomic_json(marker, dict(intent, phase='queued'))
    return batch


def scan(service, config):
    report = {'imported': [], 'recovered': [], 'unchanged': [], 'blocked': [], 'errors': []}
    with service.worker_lock('input-scan'):
        batches = service.list_batches()
        for index, batch in enumerate(batches):
            intent = recoverable_import(service, batch)
            if intent:
                try:
                    batches[index] = enqueue_import(service, batch, intent)
                    report['recovered'].append(batch['id'])
                except (OSError, ValueError):
                    report['errors'].append({'id': batch['id'], 'error': '本入口导入意图恢复失败；保留记录，下轮重查'})
        known = {i['sha256']: b for b in batches for i in b['inputs']}
        for path in input_files(config):
            try:
                sha = hashlib.sha256(path.read_bytes()).hexdigest()
                batch = known.get(sha)
                if batch is None:
                    marker = import_intent(service, sha)
                    intent = {'version': 1, 'file': path.name, 'sha256': sha, 'batch_id': None, 'phase': 'importing'}
                    if marker.exists():
                        if json.loads(marker.read_text(encoding='utf-8')) != intent:
                            raise ValueError('导入意图与输入不匹配；不覆盖历史记录')
                    else:
                        marker.parent.mkdir(exist_ok=True)
                        atomic_json(marker, intent)
                    batch = service.import_files([path])
                    if len(batch['inputs']) != 1 or batch['inputs'][0]['sha256'] != sha or batch['inputs'][0]['file'] != path.name:
                        raise ValueError('输入在导入时改变；不自动排队')
                    if batch['tasks']:
                        batch = enqueue_import(service, batch, intent)
                    known[sha] = batch
                    report['imported'].append(batch['id'])
                else:
                    report['unchanged'].append(batch['id'])
            except (OSError, ValueError):
                report['errors'].append({'file': path.name, 'error': '输入读取或持久导入失败；请核对文件及状态'})
    return report


def cycle(service, config, private, stop):
    report = scan(service, config)
    report.update(batches=[], deliveries=[], output_dir=str(config['output_dir']))
    for batch in service.list_batches():
        unfinished = any(t['state'] in {'pending', 'running'} for t in batch['tasks'])
        if unfinished and not private_queue(batch):
            report['blocked'].append({'id': batch['id'], 'error': '旧批次没有固定私人预算 scope；保留原队列和预算，请由维护者核对'})
        elif unfinished and not batch['paused']:
            while batch['queued'] and not stop.is_set():
                try:
                    batch = service.run(batch['id'], max_items=1, key_loader=private.load_key)
                    emit({'progress': summary(batch)})
                    if batch['paused']:
                        break
                except (OSError, ValueError):
                    report['errors'].append({'id': batch['id'], 'error': '批次忙碌或无法继续；下轮重查，保留持久记录'})
                    break
        report['batches'].append(summary(batch))
        if not any(t['state'] in {'pending', 'running'} for t in batch['tasks']):
            try:
                report['deliveries'].extend(deliver(service, batch, config))
            except (OSError, ValueError):
                report['errors'].append({'id': batch['id'], 'error': '自动交付失败；核对输出权限或恢复缺失文件，保留历史结果'})
    return report


def deliver(service, batch, config):
    """Persist one immutable automatic delivery per completed batch."""
    if any(t['state'] in {'pending', 'running'} for t in batch['tasks']):
        return []
    with service.worker_lock('server-export-' + batch['id']):
        receipt = service.root / 'server-deliveries' / (batch['id'] + '.json')
        if receipt.exists():
            deliveries = json.loads(receipt.read_text(encoding='utf-8'))
            for item in deliveries:
                for field in ('excel', 'zip'):
                    if not (config['output_dir'] / item[field]).is_file():
                        raise ValueError('已有自动交付文件缺失；请从备份恢复，不自动覆盖历史结果')
            return deliveries
        exports = service.export(batch['id'])['exports']
        deliveries = []
        for item in exports:
            source = service.root / item['path']
            relative = Path(batch['id']) / source.stem
            folder = config['output_dir'] / relative
            folder.parent.mkdir(parents=True, exist_ok=True)
            # Publish a complete directory on the same filesystem. A failed copy
            # leaves no final result; restart can export again without overwrite.
            with tempfile.TemporaryDirectory(prefix='.pending-', dir=folder.parent) as temporary:
                staging = Path(temporary) / 'delivery'
                staging.mkdir()
                shutil.copyfile(source, staging / 'sources.zip')
                shutil.copyfile(source.with_suffix('') / 'teachers.xlsx', staging / 'teachers.xlsx')
                os.rename(staging, folder)
            deliveries.append({'school': item['school'], 'excel': (relative / 'teachers.xlsx').as_posix(),
                               'zip': (relative / 'sources.zip').as_posix()})
        receipt.parent.mkdir(exist_ok=True)
        atomic_json(receipt, deliveries)
        return deliveries


def emit(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Mission C 服务器：预检、离线自检、显式运行与状态')
    parser.add_argument('--config', type=Path, default=ROOT / 'config.json')
    parser.add_argument('command', choices=('preview', 'once', 'watch', 'status', 'demo'))
    args = parser.parse_args(argv)
    try:
        config = configuration(args.config.resolve())
        if args.command == 'preview':
            result = preview(input_files(config))
            emit({'inputs': len(result['inputs']), 'tasks': len(result['tasks']), 'issues': result['issues'], 'completeness': 'not_verified'})
            return int(bool(result['issues']))
        # Credential metadata and bytes are only read after an explicit start.
        private = None
        if args.command in {'once', 'watch'}:
            private = PrivateDeployment(ROOT / '.private' / 'deployment.json')
            private.load_key()  # Fail before importing/enqueuing when the package is incomplete.
        if args.command == 'demo':
            config = dict(config, data_dir=config['data_dir'] / 'offline-demo', output_dir=config['output_dir'] / 'offline-demo')
            service = BatchService(config['data_dir'])
            result = service.demo()
            emit({'demo': summary(result['batch']), 'deliveries': deliver(service, result['batch'], config), 'output_dir': str(config['output_dir'])})
            return 0
        service = BatchService(config['data_dir'])
        if args.command == 'status':
            emit({'batches': [summary(b) for b in service.list_batches()], 'output_dir': str(config['output_dir'])})
            return 0
        stop = threading.Event()
        previous = {}
        try:
            for signum in (signal.SIGINT, signal.SIGTERM):
                previous[signum] = signal.signal(signum, lambda *_: stop.set())
            exit_code = 0
            while not stop.is_set():
                result = cycle(service, config, private, stop)
                emit(result)
                bad = (result['blocked'] or result['errors'] or any(b['issues'] or b['assistance_errors'] or
                       any(b['counts'].get(s, 0) for s in ('failed', 'program_error', 'artifact_missing')) for b in result['batches']))
                exit_code = max(exit_code, int(bool(bad)))
                if args.command == 'once':
                    break
                stop.wait(config['interval_seconds'])
            return exit_code
        finally:
            for signum, handler in previous.items():
                signal.signal(signum, handler)
    except (OSError, ValueError) as error:
        parser.exit(2, str(error) + '\n')


if __name__ == '__main__':
    raise SystemExit(main())
