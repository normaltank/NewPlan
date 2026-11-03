import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent

def preserve(out, name):
    if os.environ.get('SERVER_CLI_EVIDENCE'):
        import shutil
        target = Path(os.environ['SERVER_CLI_EVIDENCE'])/name
        shutil.copytree(out, target)


class CLIRunner:
    def cli(self, *args, root=ROOT):
        env = {**os.environ, 'DEEPSEEK_API_KEY': 'secret-must-not-appear', 'PYTHONDONTWRITEBYTECODE': '1'}
        return subprocess.run([sys.executable, str(root/'server_run.py'), *map(str, args)], cwd=root,
                              env=env, text=True, capture_output=True, timeout=90)


class ServerCLITests(CLIRunner, unittest.TestCase):
    def test_check_validates_limits_without_credentials_or_network(self):
        result = self.cli('--check')
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data['limits']['files_per_batch'], 200)
        self.assertEqual(data['mode'], 'deepseek')
        self.assertNotIn('secret-must-not-appear', result.stdout + result.stderr)
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp)/'limits.json'
            config.write_text('{"files_per_batch": 0}')
            result = self.cli('--check', '--limits', config)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn('secret-must-not-appear', result.stdout + result.stderr)


class ServerBatchTests(CLIRunner, unittest.TestCase):
    def test_batch_three_outcomes_and_only_errors_downloaded(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from threading import Thread
        import zipfile
        from openpyxl import load_workbook
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path)
                body = b'<html><div class="roster"><a href="/a">Alice</a><a href="/b">Bob</a></div></html>'
                self.send_response(200)
                self.end_headers()
                self.wfile.write(body)
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                inputs = root/'input'
                inputs.mkdir()
                base = f'http://127.0.0.1:{server.server_port}'
                for i in range(21):
                    (inputs/f'{i:02}.tsv').write_text(f'S\tGood\t{base}/good\t{base}/a\nS\tGood\t{base}/good\t{base}/b\n')
                (inputs/'bad.tsv').write_text(f'S\tBad\t{base}/bad\t{base}/a\nS\tBad\t{base}/bad\t{base}/x\n')
                (inputs/'unknown.tsv').write_text(f'S\tUnknown\t{base}/unknown\t{base}/a\n')
                plans = root/'plans.json'
                plans.write_text(json.dumps({'plans': {base+'/good': {'selector': '.roster'}, base+'/bad': {'selector': '.roster'}}}))
                out = root/'out'
                result = self.cli('--input', inputs, '--output', out, '--cache-dir', root/'cache', '--mode', 'rules', '--plans', plans, '--no-browser')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue((out/'server-status.json').exists())
                with zipfile.ZipFile(out/'results.zip') as z:
                    self.assertEqual(set(z.namelist()), {'核验汇总.xlsx', '更新链接/', next(n for n in z.namelist() if n.startswith('更新链接/') and n.endswith('.xlsx'))})
                    z.extractall(root/'download')
                book = load_workbook(root/'download'/'核验汇总.xlsx')
                rows = list(book.active.values)
                self.assertEqual(rows[0], ('学校', '学院', '核验结果', '特殊情况说明'))
                self.assertEqual({row[1]: row[2] for row in rows[1:]}, {'Good': '正确', 'Bad': '错误', 'Unknown': '特殊情况'})
                book.close()
                book = load_workbook(next((root/'download'/'更新链接').glob('*.xlsx')))
                self.assertEqual({row[3] for row in list(book.active.values)[1:]}, {base+'/a', base+'/b'})
                book.close()
                self.assertNotIn('/a', requests)
                self.assertNotIn('/b', requests)
                again = self.cli('--input', inputs, '--output', out, '--cache-dir', root/'cache', '--mode', 'rules', '--plans', plans, '--no-browser')
                self.assertNotEqual(again.returncode, 0)
                preserve(out, self._testMethodName)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

class ServerPackageTests(CLIRunner, unittest.TestCase):
    def test_source_package_is_explicit_self_contained_and_checkable(self):
        import hashlib
        import zipfile
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root/'server.zip'
            result = subprocess.run([sys.executable, str(ROOT/'build_server.py'), '--output', str(package)],
                                    cwd=ROOT, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            with zipfile.ZipFile(package) as z:
                z.extractall(root/'code')
                names = set(z.namelist())
            self.assertNotIn('app.py', names)
            self.assertNotIn('source_plans.json', names)
            self.assertNotIn('.browsers', names)
            metadata = json.loads((root/'code'/'PACKAGE.json').read_text())
            self.assertEqual(metadata['server_version'], '1.0.0')
            self.assertEqual(len(metadata['source_commit']), 40)
            for name, digest in metadata['files_sha256'].items():
                self.assertEqual(hashlib.sha256((root/'code'/name).read_bytes()).hexdigest(), digest)
            result = self.cli('--check', root=root/'code')
            self.assertEqual(result.returncode, 0, result.stderr)

class StandaloneBatchTests(CLIRunner, unittest.TestCase):
    def test_extracted_package_runs_three_outcomes_with_unchanged_sources(self):
        import hashlib
        import zipfile
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root/'server.zip'
            subprocess.run([sys.executable, str(ROOT/'build_server.py'), '--output', str(package)], cwd=ROOT, check=True, capture_output=True)
            code = root/'code'
            with zipfile.ZipFile(package) as z:
                z.extractall(code)
            before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in code.iterdir()}
            original = self.cli
            self.cli = lambda *args: original(*args, root=code)
            ServerBatchTests.test_batch_three_outcomes_and_only_errors_downloaded(self)
            after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in code.iterdir()}
            self.assertEqual(before, after)

    def test_two_unparsed_files_stay_separate_and_batch_completes(self):
        import zipfile
        from openpyxl import load_workbook
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inputs = root/'input'
            inputs.mkdir()
            for name in ('a.tsv', 'b.tsv'):
                (inputs/name).write_text('not parseable' * 30)
            plans = root/'plans.json'
            plans.write_text('{"plans":{}}')
            limits = root/'limits.json'
            limits.write_text('{"input_file_bytes": 10}')
            out = root/'out'
            result = self.cli('--input', inputs, '--output', out, '--cache-dir', root/'cache', '--mode', 'rules', '--plans', plans, '--limits', limits, '--no-browser')
            self.assertEqual(result.returncode, 0, result.stderr)
            with zipfile.ZipFile(out/'results.zip') as z:
                self.assertEqual(z.namelist(), ['核验汇总.xlsx', '更新链接/'])
                z.extractall(root/'download')
            book = load_workbook(root/'download'/'核验汇总.xlsx')
            rows = list(book.active.values)[1:]
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(row[:3] == (None, None, '特殊情况') for row in rows))
            self.assertIn('a.tsv', rows[0][3])
            self.assertIn('b.tsv', rows[1][3])
            book.close()
            preserve(out, self._testMethodName)

class StandaloneModelTests(CLIRunner, unittest.TestCase):
    def test_extracted_deepseek_uses_local_fake_model_and_external_cache(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from threading import Thread
        from bs4 import BeautifulSoup
        import zipfile
        calls = []
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'<div class="roster"><a href="/a">Alice</a></div>')
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                calls.append(body)
                payload = json.loads(body['messages'][1]['content'])
                region = int(BeautifulSoup(payload['html'], 'lxml').select_one('.roster')['data-mb-id'])
                answer = {'status': 'ready', 'roster_regions': [region], 'pagination_regions': [], 'exclude_regions': [], 'reason': 'local fixture'}
                response = {'model': 'local-fixture', 'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(answer)}}]}
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps(response).encode())
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                package = root/'server.zip'
                subprocess.run([sys.executable, str(ROOT/'build_server.py'), '--output', str(package)], cwd=ROOT, check=True, capture_output=True)
                with zipfile.ZipFile(package) as z:
                    z.extractall(root/'code')
                inputs = root/'input'
                inputs.mkdir()
                base = f'http://127.0.0.1:{server.server_port}'
                (inputs/'in.tsv').write_text(f'S\tC\t{base}/list\t{base}/a\n')
                # Test-only boundary adapter outside the package: only replace provider endpoint.
                shim = root/'shim'
                shim.mkdir()
                (shim/'sitecustomize.py').write_text(f'import deepseek_api\ndeepseek_api.BASE_URL = {base!r}\n')
                env = {**os.environ, 'PYTHONPATH': os.pathsep.join((str(shim), str(root/'code'))),
                       'DEEPSEEK_API_KEY': 'local-fixture-key', 'PYTHONDONTWRITEBYTECODE': '1'}
                for run in ('first', 'cached'):
                    result = subprocess.run([sys.executable, '-B', str(root/'code'/'server_run.py'), '--input', str(inputs), '--output', str(root/run), '--cache-dir', str(root/'cache'), '--no-browser'], cwd=root/'code', env=env, text=True, capture_output=True, timeout=90)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    records = json.loads((root/run/'results.json').read_text())
                    self.assertTrue(records[0]['complete'], records[0]['reason'])
                    self.assertEqual(records[0]['corrected_urls'], [base+'/a'])
                preserve(root/'first', self._testMethodName + '-first')
                preserve(root/'cached', self._testMethodName + '-cached')
                self.assertEqual(len(calls), 2)
                self.assertEqual(json.loads((root/'cached'/'manifest.json').read_text())['api']['cache_hits'], 1)
                self.assertNotIn('local-fixture-key', (root/'first'/'progress.jsonl').read_text())
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

class StandaloneBrowserTests(CLIRunner, unittest.TestCase):
    def test_extracted_rules_reads_javascript_roster_with_real_chromium(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from threading import Thread
        import zipfile
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'''<html><div class="roster"></div><script>document.querySelector('.roster').innerHTML='<a href="/tail">Alice</a>';</script></html>''')
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                package = root/'server.zip'
                subprocess.run([sys.executable, str(ROOT/'build_server.py'), '--output', str(package)], cwd=ROOT, check=True, capture_output=True)
                with zipfile.ZipFile(package) as z:
                    z.extractall(root/'code')
                inputs = root/'input'
                inputs.mkdir()
                base = f'http://127.0.0.1:{server.server_port}'
                (inputs/'in.tsv').write_text(f'S\tC\t{base}/list\t{base}/tail\n')
                plans = root/'plans.json'
                plans.write_text(json.dumps({'plans': {base+'/list': {'selector': '.roster'}}}))
                result = self.cli('--input', inputs, '--output', root/'out', '--cache-dir', root/'cache', '--mode', 'rules', '--plans', plans, root=root/'code')
                self.assertEqual(result.returncode, 0, result.stderr)
                record = json.loads((root/'out'/'results.json').read_text())[0]
                self.assertTrue(record['complete'], record['reason'])
                self.assertEqual(record['corrected_urls'], [base+'/tail'])
                self.assertTrue(list((root/'out'/'evidence').rglob('browser.html')))
                preserve(root/'out', self._testMethodName)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
