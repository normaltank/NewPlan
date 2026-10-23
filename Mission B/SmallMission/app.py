"""Standalone, loopback-only Mission B desktop web application."""
from __future__ import annotations

import argparse
import asyncio
import base64
from collections import Counter
from datetime import datetime
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import mimetypes
from pathlib import Path
import re
import secrets
import sys
import threading
import traceback
from types import SimpleNamespace
from urllib.parse import quote, urlsplit
import uuid
import webbrowser
import zipfile

from audit import lookup_plan, run
from input_adapter import MAX_FILE_BYTES, SUPPORTED, read_directory, tasks_from_rows
from runtime_paths import APP_ROOT, ASSETS, VERSION, plans_path
from reporting import input_assessment, export_names, original_error_status, count_comparison, college_count_summaries

ID = re.compile(r'^[a-f0-9]{32}$')


def now():
    return datetime.now().astimezone().isoformat(timespec='seconds')


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def brief(result):
    legacy = 'original_error' in result and 'count_comparison' not in result and 'source' not in result
    return {**{key: result[key] for key in ('id', 'school', 'college', 'roster_url', 'complete', 'needs_human', 'verdict', 'reason', 'stats')},
            'roster_urls': result.get('roster_urls', [result['roster_url']]),
            'original_error': result.get('original_error', original_error_status(result)),
            'count_comparison': None if legacy else count_comparison(result),
            'input_assessment': result.get('input_assessment', input_assessment(result)) if legacy else input_assessment(result)}


def job_view(job):
    value = json.loads(json.dumps(job))
    value['results'] = [brief(r) for r in value['results']]
    return value


class Store:
    def __init__(self, root):
        self.root = root.resolve()
        if not self.root.is_relative_to(APP_ROOT) or self.root == APP_ROOT:
            raise ValueError('任务数据目录必须位于本工具文件夹内')
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.worker = None
        self.cancel = threading.Event()
        self.jobs = {}
        for path in sorted(self.root.glob('runs/*/job.json')):
            try:
                job = json.loads(path.read_text(encoding='utf-8'))
                if job['status'] in ('running', 'stopping'):
                    job.update(status='interrupted', message='上次程序退出，任务未完成；原始输入和已有证据仍保留。请重新导入运行。')
                    atomic_json(path, job)
                self.jobs[job['id']] = job
            except (ValueError, KeyError):
                logging.exception('Cannot load prior job %s', path)

    def active(self):
        return self.worker is not None and self.worker.is_alive()

    def preview(self, payload):
        identifier = uuid.uuid4().hex
        directory = self.root / 'previews' / identifier / 'inputs'
        directory.mkdir(parents=True)
        entries = payload.get('files', [])
        if not isinstance(entries, list) or len(entries) > 50:
            raise ValueError('每批最多50个文件')
        names = set()
        for item in entries:
            name = item.get('name', '')
            if not isinstance(name, str) or not name or name.startswith('.') or re.search(r'[<>:"/\\|?*\x00-\x1f]', name) or len(name) > 160:
                raise ValueError('文件名无效或过长，请重命名后再导入')
            if Path(name).suffix.lower() not in SUPPORTED:
                raise ValueError(name + '：不支持此文件格式')
            if name.casefold() in names or name == '粘贴输入.txt':
                raise ValueError('存在同名文件，请重命名后再导入：' + name)
            names.add(name.casefold())
            try:
                raw = base64.b64decode(item['content'], validate=True)
            except (ValueError, KeyError, TypeError):
                raise ValueError(name + '：上传内容不完整，请重新选择文件') from None
            if len(raw) > MAX_FILE_BYTES:
                raise ValueError(name + '：单个文件不能超过10MB')
            (directory / name).write_bytes(raw)
        pasted = payload.get('text', '')
        if not isinstance(pasted, str) or len(pasted.encode('utf-8')) > MAX_FILE_BYTES:
            raise ValueError('粘贴文本不能超过10MB')
        if pasted.strip():
            (directory / '粘贴输入.txt').write_text(pasted, encoding='utf-8')
        rows, files, errors, warnings = read_directory(directory)
        config = json.loads(plans_path().read_text(encoding='utf-8'))
        tasks = tasks_from_rows(rows)
        groups = [{**{k: v for k, v in t.items() if k != 'rows'}, 'rows': len(t['rows']),
                   'supported': all(bool((lookup_plan(config, url) or {}).get('selector')) for url in t['roster_urls'])} for t in tasks]
        teachers = [row for row in rows if row.get('record_kind') != 'source']
        value = {'id': identifier, 'created': now(), 'files': files, 'errors': errors, 'warnings': warnings,
                 'row_count': len(teachers), 'task_count': len(tasks),
                 'source_count': sum(len(t['roster_urls']) for t in tasks),
                 'college_count': len({(t['school'], t['college']) for t in tasks}),
                 'placeholder_count': sum(not r['url'] for r in teachers),
                 'groups': groups, 'sample': [r['values'] for r in teachers[:100]], 'sample_limit': 100}
        atomic_json(directory.parent / 'preview.json', value)
        return value

    def start(self, preview_id):
        if not isinstance(preview_id, str) or not ID.fullmatch(preview_id):
            raise ValueError('请先预览本次输入')
        with self.lock:
            if self.active():
                raise ValueError('已有核验正在运行，请等待完成或停止后再提交')
            path = self.root / 'previews' / preview_id
            try:
                preview = json.loads((path / 'preview.json').read_text(encoding='utf-8'))
            except (OSError, ValueError):
                raise ValueError('预览已失效，请重新预览') from None
            if preview['errors'] or not preview['task_count']:
                raise ValueError('请先修正预览中的格式问题')
            _, files, errors, _ = read_directory(path / 'inputs')
            if errors or files != preview['files']:
                raise ValueError('输入在预览后发生变化，请重新预览')
            identifier = uuid.uuid4().hex
            job = {'id': identifier, 'created': now(), 'status': 'running', 'completed': 0,
                   'total': preview['task_count'], 'message': '准备核验', 'results': [], 'preview_id': preview_id}
            self.jobs[identifier] = job
            self.save(job)
            self.cancel.clear()
            self.worker = threading.Thread(target=self.execute, args=(job, path / 'inputs'), daemon=True)
            self.worker.start()
            return json.loads(json.dumps(job))

    def save(self, job):
        atomic_json(self.root / 'runs' / job['id'] / 'job.json', job)

    def execute(self, job, inputs):
        directory = self.root / 'runs' / job['id']
        def progress(event, data):
            with self.lock:
                if event == 'college_started':
                    job['message'] = '正在读取 ' + data['school'] + ' · ' + data['college']
                elif event == 'source_started':
                    job['message'] = f"正在读取 {data['school']} · {data['college']}（师资页 {data['source_index']}/{data['source_total']}）"
                elif event == 'college_finished':
                    job['completed'] = data['index']
                    job['results'].append(brief(data['result']))
                elif event == 'exporting':
                    job['message'] = '正在整理核验表与来源证据'
                if job['status'] == 'stopping':
                    job['message'] = '将在当前学院处理完成后停止'
                self.save(job)
        try:
            args = SimpleNamespace(input=inputs, output=directory / 'output', plans=plans_path(), no_browser=False, replay=None)
            _, results, manifest = asyncio.run(run(args, on_progress=progress, should_cancel=self.cancel.is_set))
            with zipfile.ZipFile(directory / '完整结果.zip', 'w', zipfile.ZIP_DEFLATED) as z:
                for path in sorted((directory / 'output').rglob('*')):
                    if path.is_file():
                        z.write(path, 'MissionB结果/' + path.relative_to(directory / 'output').as_posix())
            with zipfile.ZipFile(directory / '修正后分学院表.zip', 'w', zipfile.ZIP_DEFLATED) as z:
                for path in sorted((directory / 'output' / 'corrected').glob('*.xlsx')):
                    z.write(path, path.name)
            with self.lock:
                job.update(status='completed', message='核验完成', finished=now(), needs_human=manifest['needs_human'], summary_available=True,
                           summary_rule='url_count_v1', college_summaries=college_count_summaries(results))
        except InterruptedError as e:
            with self.lock:
                job.update(status='cancelled', message=str(e), finished=now())
        except Exception as e:
            logging.exception('Job failed: %s', job['id'])
            with self.lock:
                job.update(status='failed', message='任务未完成：' + str(e), finished=now())
                (directory / 'error.txt').write_text(traceback.format_exc(), encoding='utf-8')
        finally:
            with self.lock:
                self.save(job)

    def get(self, identifier):
        with self.lock:
            if not ID.fullmatch(identifier) or identifier not in self.jobs:
                raise ValueError('找不到这次任务')
            return job_view(self.jobs[identifier])

    def details(self, identifier, college_id):
        self.get(identifier)
        path = self.root / 'runs' / identifier / 'output' / 'results.json'
        # The writer atomically replaces this file, so a browser never sees half a result.
        for result in json.loads(path.read_text(encoding='utf-8')) if path.exists() else []:
            if result['id'] == college_id:
                included = [a for a in result['source']['anchors'] if a['included']]
                groups = []
                for index in range(1, result['source']['root_count'] + 1):
                    anchors = [a for a in included if a['root_index'] == index]
                    groups.append({'index': index, 'occurrences': len(anchors), 'unique': len({a['url'] for a in anchors})})
                return {**brief(result), 'diffs': result['diffs'], 'notes': result['source']['notes'], 'groups': groups,
                        'sources': result.get('sources', []),
                        'anchors': [{k: a[k] for k in ('name', 'url', 'included', 'reason', 'root_index')} for a in result['source']['anchors']]}
        raise ValueError('该学院还没有核验结果')


class Handler(BaseHTTPRequestHandler):
    server_version = 'MissionB/2'

    def log_message(self, *_):
        pass  # Do not log session tokens, uploads, or query strings.

    def send(self, status, data, content_type='application/json; charset=utf-8', extra=None):
        if not isinstance(data, bytes):
            data = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def authenticated(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
        except Exception:
            return False
        return secrets.compare_digest(cookie.get('missionb_session').value if cookie.get('missionb_session') else '', self.server.token)

    def route(self, method):
        port = self.server.server_port
        if self.headers.get('Host') not in (f'127.0.0.1:{port}', f'localhost:{port}'):
            return self.send(403, {'error': '只允许本机访问'})
        path = urlsplit(self.path).path
        if method == 'POST':
            if self.headers.get('Origin') not in (None, f'http://127.0.0.1:{port}', f'http://localhost:{port}'):
                return self.send(403, {'error': '请求来源不允许'})
            length = int(self.headers.get('Content-Length', '0'))
            if length <= 0 or length > 32 * 1024 * 1024:
                return self.send(413, {'error': '本次上传过大，请拆成小批次（每批文件总量建议低于20MB）'})
            if not self.headers.get('Content-Type', '').startswith('application/json'):
                return self.send(415, {'error': '请求格式无效'})
            payload = json.loads(self.rfile.read(length).decode('utf-8'))
            if not isinstance(payload, dict):
                raise ValueError('请求格式无效')
            if path == '/api/session':
                if not isinstance(payload.get('token'), str) or not secrets.compare_digest(payload['token'], self.server.token):
                    return self.send(403, {'error': '请从启动程序重新打开工作台'})
                return self.send(200, {'ok': True}, extra={'Set-Cookie': f'missionb_session={self.server.token}; HttpOnly; SameSite=Strict; Path=/'})
        if path == '/health' and method == 'GET':
            return self.send(200, {'app': 'MissionB', 'version': VERSION})
        static = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/app.css': ('app.css', 'text/css; charset=utf-8')}
        if path in static and method == 'GET':
            name, content_type = static[path]
            return self.send(200, (ASSETS / 'web' / name).read_bytes(), content_type)
        if not self.authenticated():
            return self.send(401, {'error': '会话已失效，请重新双击启动工具'})
        store = self.server.store
        if path == '/api/config' and method == 'GET':
            config = json.loads(plans_path().read_text(encoding='utf-8'))
            return self.send(200, {'version': VERSION, 'scope': config['scope'], 'supported': sum(bool(x.get('selector')) for x in config['plans'].values())})
        if path == '/api/preview' and method == 'POST':
            return self.send(200, store.preview(payload))
        if path == '/api/jobs' and method == 'POST':
            return self.send(201, store.start(payload.get('preview_id')))
        if path == '/api/jobs' and method == 'GET':
            with store.lock:
                jobs = [job_view(j) for j in sorted(store.jobs.values(), key=lambda x: x['created'], reverse=True)]
            return self.send(200, jobs)
        match = re.fullmatch(r'/api/jobs/([a-f0-9]{32})(?:/([^/]+)(?:/([^/]+))?)?', path)
        if match:
            identifier, action, detail = match.groups()
            job = store.get(identifier)
            if not action and method == 'GET':
                return self.send(200, job)
            if action == 'cancel' and method == 'POST':
                with store.lock:
                    if job['status'] == 'running':
                        store.cancel.set()
                        store.jobs[identifier].update(status='stopping', message='将在当前学院处理完成后停止')
                        store.save(store.jobs[identifier])
                return self.send(200, store.get(identifier))
            if action == 'college' and method == 'GET' and detail:
                return self.send(200, store.details(identifier, detail))
            if action == 'download' and method == 'GET':
                if job['status'] != 'completed':
                    raise ValueError('任务尚未完成，不能下载完整交付表')
                directory = store.root / 'runs' / identifier
                manifest = json.loads((directory / 'output' / 'manifest.json').read_text(encoding='utf-8'))
                report_name = manifest.get('report_filename', 'MissionB_核验结果.xlsx')
                names = {'excel': 'output/' + report_name, 'all': '完整结果.zip', 'corrected': '修正后分学院表.zip', 'html': 'output/report.html'}
                if manifest.get('summary_filename'):
                    names['summary'] = 'output/' + manifest['summary_filename']
                if detail not in names:
                    raise ValueError('无此下载文件')
                # Legacy task files remain intact; their download label is upgraded.
                download_name = export_names(job['results'], {**manifest, 'run_id': identifier})[0] if detail == 'excel' and 'report_filename' not in manifest else None
                return self.download(directory / names[detail], download_name)
        if path == '/api/template.xlsx' and method == 'GET':
            return self.download(ASSETS / 'templates' / '输入模板.xlsx')
        if path == '/api/template.tsv' and method == 'GET':
            return self.download(ASSETS / 'templates' / '输入模板.tsv')
        if path == '/api/shutdown' and method == 'POST':
            if store.active():
                raise ValueError('请先等待核验完成，或停止任务后再退出')
            self.send(200, {'ok': True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        self.send(404, {'error': '找不到此页面或操作'})

    def download(self, path, name=None):
        return self.send(200, path.read_bytes(), mimetypes.guess_type(path.name)[0] or 'application/octet-stream',
                         {'Content-Disposition': "attachment; filename*=UTF-8''" + quote(name or path.name)})

    def handle_method(self, method):
        try:
            self.route(method)
        except (ValueError, KeyError, TypeError) as e:
            self.send(400, {'error': str(e)})
        except Exception:
            logging.exception('Request failed')
            self.send(500, {'error': '处理失败，详细原因已写入工具文件夹内 data/app.log'})

    def do_GET(self):
        self.handle_method('GET')

    def do_POST(self):
        self.handle_method('POST')


def make_server(data, port=0):
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    server.token = secrets.token_urlsafe(32)
    server.store = Store(data)
    return server


def instance_lock(path):
    handle = path.open('a+b')
    handle.seek(0)
    if sys.platform == 'win32':
        import msvcrt
        if path.stat().st_size == 0:
            handle.write(b'0'); handle.flush(); handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return handle


def main():
    parser = argparse.ArgumentParser(description='Mission B 师资链接核验工作台')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--data-dir', type=Path, default=APP_ROOT / 'data')
    args = parser.parse_args()
    data = args.data_dir.resolve()
    if not data.is_relative_to(APP_ROOT) or data == APP_ROOT:
        raise ValueError('数据目录必须在本工具的独立子目录内')
    data.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=data / 'app.log', encoding='utf-8', level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    try:
        handle = instance_lock(data / 'instance.lock')
    except OSError:
        info = json.loads((data / 'instance.json').read_text(encoding='utf-8'))
        if not args.no_browser:
            webbrowser.open(info['url'])
        return
    try:
        server = make_server(data, args.port)
        url = f'http://127.0.0.1:{server.server_port}/#token={server.token}'
        atomic_json(data / 'instance.json', {'url': url, 'port': server.server_port})
        if sys.platform != 'win32':
            (data / 'instance.json').chmod(0o600)
        if sys.stdout:
            print('Mission B 工作台已启动，端口：' + str(server.server_port), flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        try:
            server.serve_forever(poll_interval=0.5)
        finally:
            server.server_close()
    finally:
        handle.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        if sys.stderr:
            traceback.print_exc()
        if sys.platform == 'win32' and getattr(sys, 'frozen', False):
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, '启动失败：' + str(error) + '\n请完整解压到可写文件夹后重试。', 'Mission B', 0x10)
        sys.exit(1)
