"""Small distribution surface over the unchanged Mission B audit engine."""
from __future__ import annotations

import argparse
import base64
from collections import Counter
import hashlib
from http.server import ThreadingHTTPServer
import io
import json
import logging
from pathlib import Path
import platform
import re
import secrets
import sys
import threading
import traceback
from urllib.parse import urlsplit
import webbrowser
import zipfile
import zlib

from app import Handler, Store, atomic_json, instance_lock, now
from input_adapter import read_directory
from lite_mail import MailReporter, load_config
from openpyxl import Workbook
from reporting import college_summaries, sheet
from runtime_paths import APP_ROOT, ASSETS, VERSION, plans_path

LITE_VERSION = '1.0.7'
STATUSES = ('正确', '错误', '特殊情况')
ARCHIVE_NAME = '核验结果与更新链接.zip'
MAX_FILES = 20


class Journal:
    """Append-only JSON lines; compressed evidence makes a single sendable log."""
    def __init__(self, path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
        self.lock = threading.RLock()
        self.secrets = set()

    def protect(self, value):
        if value:
            self.secrets.add(value)

    def redact(self, text):
        for value in sorted(self.secrets, key=len, reverse=True):
            text = text.replace(value, '[REDACTED]')
            text = text.replace(json.dumps(value, ensure_ascii=False)[1:-1], '[REDACTED]')
        text = re.sub(r'(?i)\bsk-[A-Za-z0-9_-]{8,}', '[REDACTED]', text)
        text = re.sub(r'(?i)(bearer\s+)[^\s"<>]+', r'\1[REDACTED]', text)
        text = re.sub(r'(?i)([?&](?:api_key|apikey|token|access_token|key)=)[^&\s"<>]+', r'\1[REDACTED]', text)
        return text

    def write(self, event, **data):
        with self.lock:
            line = self.redact(json.dumps({'time': now(), 'event': event, **data}, ensure_ascii=False, default=str))
            with self.path.open('a', encoding='utf-8') as handle:
                handle.write(line + '\n')

    def snapshot(self, job_id, path, name):
        # Only textual, allowlisted audit evidence is supplied by the caller.
        raw = self.redact(path.read_text(encoding='utf-8', errors='replace')).encode('utf-8')
        self.write('evidence', job_id=job_id, path=name, encoding='zlib+base64',
                   sha256=hashlib.sha256(raw).hexdigest(),
                   content=base64.b64encode(zlib.compress(raw)).decode('ascii'))


class JournalHandler(logging.Handler):
    def __init__(self, journal):
        super().__init__(logging.WARNING)
        self.journal = journal

    def emit(self, record):
        self.journal.write('runtime_error', level=record.levelname, message=self.format(record))


def public_rows(results):
    # Keep the engine's decisions, suppress the diagnostic note only at this boundary.
    return [[r['school'], r['college'], r['verification_result'], '']
            for r in college_summaries(results)]


def public_job(job):
    rows = public_rows(job['results'])
    counts = Counter(row[2] for row in rows)
    return {key: job[key] for key in ('id', 'created', 'status', 'completed', 'total')} | {
        'counts': {status: counts[status] for status in STATUSES},
        'summary_headers': ['学校', '学院', '核验结果'],
        'summary_rows': [row[:3] for row in rows],
        'results_ready': job['status'] == 'completed',
        'download_ready': job['status'] == 'completed',
    }


class LiteStore(Store):
    def __init__(self, root, journal):
        self.journal = journal
        super().__init__(root)
        config = ASSETS / 'lite_config.json'
        if config.is_file():
            self.api_key = json.loads(config.read_text(encoding='utf-8'))['api_key']
        journal.protect(self.api_key)
        self.mail = None
        try:
            mail_config = load_config(ASSETS / 'mail_config.json')
            if mail_config:
                journal.protect(mail_config['password'])
                self.mail = MailReporter(self.root / 'mail-outbox', journal, mail_config, LITE_VERSION)
        except (OSError, ValueError, TypeError):
            journal.write('mail_configuration_invalid')
        if self.api_key:
            self.update_settings({'api_key': self.api_key})
        journal.write('startup', edition=LITE_VERSION, engine=VERSION, python=platform.python_version(),
                      system=platform.platform(), model='deepseek-flash', max_api_calls=self.max_api_calls,
                      automatic_support_mail=bool(self.mail),
                      code_hashes={name: hashlib.sha256((ASSETS / name).read_bytes()).hexdigest()
                                   for name in ('audit.py', 'api_engine.py', 'ai_regions.py', 'deepseek_api.py',
                                                'input_adapter.py', 'reporting.py', 'lite_app.py', 'lite_mail.py') if (ASSETS / name).exists()})
        for job in self.jobs.values():
            if job['status'] == 'finalizing' or (job['status'] == 'completed' and
                    not self.result_exists(job['id'])):
                job.update(status='interrupted', message='上次结果整理未完成')
                self.save(job)
            if job['status'] == 'interrupted':
                journal.write('interrupted', job_id=job['id'], job=job)

    def submit(self, payload):
        with self.lock:
            if self.active():
                raise ValueError('已有核验正在运行，请完成或停止后再提交')
            if not self.api_key:
                raise ValueError('工具尚未配置完成，请联系维护人员')
            if not isinstance(payload.get('files', []), list) or len(payload.get('files', [])) > MAX_FILES:
                raise ValueError(f'每批最多{MAX_FILES}个文件，请减少文件后重试')
            preview = self.preview({key: payload[key] for key in ('files', 'text') if key in payload})
            if preview['errors'] or not preview['task_count']:
                self.journal.write('input_rejected', preview=preview)
                raise ValueError('；'.join(preview['errors']) or '没有找到可核验的输入，请按模板填写')
            self.journal.write('input_accepted', preview=preview)
            job = self.start(preview['id'])
            return self.view(job['id'])

    def execute(self, job, inputs):
        directory = self.root / 'runs' / job['id']
        try:
            rows, files, errors, warnings = read_directory(inputs)
            self.journal.write('run_started', job_id=job['id'], inputs=rows, files=files, errors=errors,
                               warnings=warnings, mode=job['engine'], max_api_calls=self.max_api_calls,
                               plans=json.loads(plans_path().read_text(encoding='utf-8')))
            super().execute(job, inputs)
            # Do not expose "completed" until the simple export and support log exist.
            with self.lock:
                outcome = job['status']
                job['status'] = 'finalizing'
                self.save(job)
            output = directory / 'output'
            for name in ('results.json', 'manifest.json', 'source_plans.json'):
                if (output / name).is_file():
                    self.journal.snapshot(job['id'], output / name, name)
            for folder in ('evidence', 'model-evidence', 'api'):
                for path in sorted((output / folder).rglob('*')):
                    if path.is_file() and path.suffix in ('.html', '.json', '.txt'):
                        self.journal.snapshot(job['id'], path, path.relative_to(output).as_posix())
            if (directory / 'error.txt').exists():
                self.journal.snapshot(job['id'], directory / 'error.txt', 'error.txt')
            if outcome == 'completed':
                self.export_simple(job)
            self.journal.write('run_finished', job_id=job['id'], job={**job, 'status': outcome})
            with self.lock:
                job['status'] = outcome
                self.save(job)
        except Exception:
            self.journal.write('maintenance_error', job_id=job['id'], traceback=traceback.format_exc())
            with self.lock:
                job.update(status='failed', message='结果或日志整理失败', finished=now())
                self.save(job)
        # Support delivery is never part of verification or result finalization.
        if self.mail and job['status'] == 'completed':
            count = sum(row[2] == '特殊情况' for row in public_rows(job['results']))
            if count:
                try:
                    self.mail.submit(job['id'], count)
                except Exception as error:
                    self.journal.write('mail_queue_failed', job_id=job['id'], error=str(error))

    def close(self):
        if self.mail:
            self.mail.close()

    def export_simple(self, job):
        directory = self.root / 'runs' / job['id']
        summary = public_job(job)
        wrong_colleges = {(row[0], row[1]) for row in summary['summary_rows'] if row[2] == '错误'}
        book = Workbook()
        book.remove(book.active)
        sheet(book, '核验结果', summary['summary_headers'], summary['summary_rows'])
        content = io.BytesIO()
        book.save(content)
        results = json.loads((directory / 'output' / 'results.json').read_text(encoding='utf-8'))
        target = directory / ARCHIVE_NAME
        temp = target.with_suffix('.tmp')
        with zipfile.ZipFile(temp, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('核验后链接/', '')
            archive.writestr('核验结果.xlsx', content.getvalue())
            for result in results:
                if not result['complete'] or (result['school'], result['college']) not in wrong_colleges:
                    continue
                name = result['corrected_filename']
                if Path(name).name != name or not name.endswith('.xlsx'):
                    raise ValueError('更新链接文件名无效')
                path = directory / 'output' / 'corrected' / name
                archive.write(path, '核验后链接/' + path.name)
        temp.replace(target)

    def result_exists(self, identifier):
        directory = self.root / 'runs' / identifier
        # Older archives are completion evidence, never the new download payload.
        return any((directory / name).is_file() for name in (ARCHIVE_NAME, '更新后的师资链接.zip', '核验结果.zip'))

    def view(self, identifier):
        with self.lock:
            if identifier not in self.jobs:
                raise ValueError('找不到这次任务')
            value = public_job(self.jobs[identifier])
            # The parent saves completion before returning to our final export step.
            value['results_ready'] &= self.result_exists(identifier)
            value['download_ready'] &= value['results_ready']
            if value['status'] == 'completed' and not value['results_ready']:
                value['status'] = 'finalizing'
            return value


class LiteHandler(Handler):
    server_version = 'MissionB-Lite/' + LITE_VERSION

    def route(self, method):
        port = self.server.server_port
        if self.headers.get('Host') not in (f'127.0.0.1:{port}', f'localhost:{port}'):
            return self.send(403, {'error': '只允许本机访问'})
        path = urlsplit(self.path).path
        if method == 'POST':
            if self.headers.get('Origin') not in (None, f'http://127.0.0.1:{port}', f'http://localhost:{port}'):
                return self.send(403, {'error': '请求来源不允许'})
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 32 * 1024 * 1024:
                return self.send(413, {'error': '本批输入过大，请拆为小批次后重试'})
            if not self.headers.get('Content-Type', '').startswith('application/json'):
                return self.send(415, {'error': '请求格式无效'})
            payload = json.loads(self.rfile.read(length).decode('utf-8'))
            if not isinstance(payload, dict):
                raise ValueError('请求格式无效')
            if path == '/api/session':
                if not isinstance(payload.get('token'), str) or not secrets.compare_digest(payload['token'], self.server.token):
                    return self.send(403, {'error': '请重新双击启动程序'})
                return self.send(200, {'ok': True}, extra={'Set-Cookie': f'missionb_session={self.server.token}; HttpOnly; SameSite=Strict; Path=/'})
        if path == '/health' and method == 'GET':
            return self.send(200, {'app': 'MissionB-Lite', 'version': LITE_VERSION, 'engine': VERSION})
        static = {'/': ('index.html', 'text/html; charset=utf-8'),
                  '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/app.css': ('app.css', 'text/css; charset=utf-8')}
        if method == 'GET' and path in static:
            name, mime = static[path]
            return self.send(200, (ASSETS / 'lite_web' / name).read_bytes(), mime)
        if not self.authenticated():
            return self.send(401, {'error': '会话已失效，请重新双击启动程序'})
        store = self.server.store
        if path == '/api/state' and method == 'GET':
            with store.lock:
                latest = max(store.jobs.values(), key=lambda j: (j['created'],
                    (store.root / 'runs' / j['id'] / 'job.json').stat().st_mtime_ns), default=None)
                return self.send(200, {'configured': bool(store.api_key), 'automatic_support_mail': bool(store.mail), 'max_files': MAX_FILES,
                                       'job': store.view(latest['id']) if latest else None})
        if path == '/api/start' and method == 'POST':
            return self.send(201, store.submit(payload))
        if path == '/api/template.xlsx' and method == 'GET':
            return self.download(ASSETS / 'templates' / '输入模板.xlsx')
        match = re.fullmatch(r'/api/jobs/([a-f0-9]{32})(?:/(cancel|download))?', path)
        if match:
            identifier, action = match.groups()
            job = store.view(identifier)
            if action is None and method == 'GET':
                return self.send(200, job)
            if action == 'cancel' and method == 'POST':
                with store.lock:
                    if store.jobs[identifier]['status'] == 'running':
                        store.cancel.set()
                        store.jobs[identifier]['status'] = 'stopping'
                        store.save(store.jobs[identifier])
                        store.journal.write('stop_requested', job_id=identifier)
                return self.send(200, store.view(identifier))
            if action == 'download' and method == 'GET':
                if not job['download_ready']:
                    raise ValueError('结果尚未准备好，请稍后下载')
                with store.lock:
                    path = store.root / 'runs' / identifier / ARCHIVE_NAME
                    if not path.is_file():
                        store.export_simple(store.jobs[identifier])
                return self.download(path, f'核验结果_{identifier[:8]}.zip')
        if path == '/api/shutdown' and method == 'POST':
            if store.active():
                raise ValueError('请等待完成或停止核验后再退出')
            store.journal.write('shutdown')
            self.send(200, {'ok': True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        self.send(404, {'error': '找不到此操作'})

    def handle_method(self, method):
        try:
            self.route(method)
        except (ValueError, KeyError, TypeError) as error:
            self.server.store.journal.write('request_rejected', message=str(error))
            self.send(400, {'error': self.server.store.journal.redact(str(error))})
        except Exception:
            self.server.store.journal.write('request_failed', traceback=traceback.format_exc())
            self.send(500, {'error': '操作未完成，请将软件文件夹内的 MissionB.log 发给维护人员'})


def make_server(data, port=0, log_path=None):
    journal = Journal(log_path or data.parent / 'MissionB.log')
    server = ThreadingHTTPServer(('127.0.0.1', port), LiteHandler)
    server.daemon_threads = True
    server.token = secrets.token_urlsafe(32)
    journal.protect(server.token)
    try:
        server.store = LiteStore(data, journal)
    except Exception:
        server.server_close()
        raise
    return server


def main():
    parser = argparse.ArgumentParser(description='Mission B 精简版')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--data-dir', type=Path, default=APP_ROOT / 'lite-data')
    args = parser.parse_args()
    data = args.data_dir.resolve()
    if not data.is_relative_to(APP_ROOT) or data == APP_ROOT:
        raise ValueError('数据目录必须在本工具的独立子目录内')
    data.mkdir(parents=True, exist_ok=True)
    try:
        handle = instance_lock(data / 'instance.lock')
    except OSError:
        info = json.loads((data / 'instance.json').read_text(encoding='utf-8'))
        if not args.no_browser:
            webbrowser.open(info['url'])
        return
    try:
        server = make_server(data, args.port)
        logger = JournalHandler(server.store.journal)
        logging.getLogger().addHandler(logger)
        url = f'http://127.0.0.1:{server.server_port}/#token={server.token}'
        atomic_json(data / 'instance.json', {'url': url, 'port': server.server_port})
        if sys.platform != 'win32':
            (data / 'instance.json').chmod(0o600)
        if not args.no_browser:
            webbrowser.open(url)
        try:
            server.serve_forever(poll_interval=0.3)
        finally:
            server.server_close()
            server.store.close()
            logging.getLogger().removeHandler(logger)
    finally:
        handle.close()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        Journal(APP_ROOT / 'MissionB.log').write('startup_failed', traceback=traceback.format_exc())
        if sys.platform == 'win32' and getattr(sys, 'frozen', False):
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, '启动失败。请完整解压到可写文件夹后重试。\n如仍失败，请将 MissionB.log 发给维护人员。', 'Mission B 精简版', 0x10)
        sys.exit(1)
