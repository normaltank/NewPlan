"""Public regression boundaries for persisted budgets and portable package files."""
from contextlib import redirect_stdout, redirect_stderr
import gc
import io
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import httpx

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mission_c.batch import BatchService
from mission_c.cli import main as collect
from test_web import workbook


class ReviewFixes(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.addCleanup(gc.collect)
        self.folder=Path(temporary.name)

    def test_saved_ordinary_batch_keeps_preexisting_unscoped_paid_budget(self):
        data=self.folder/'data'
        html='<main><h1>李明</h1><p>姓名：李明</p><p>职称：教授</p><p>研究方向：光学。完整个人经历。</p></main>'
        source=self.folder/'source.html';source.write_text(html,encoding='utf-8')
        calls=[]
        def external(transport,request):
            if request.url.host=='api.deepseek.com':
                calls.append(request.url.path)
                return httpx.Response(401,json={'error':'fake rejection'})
            self.assertEqual(request.url.host,'example.edu')
            if request.url.path=='/robots.txt': return httpx.Response(404)
            return httpx.Response(200,content=html.encode(),headers={'content-type':'text/html; charset=utf-8'})
        with patch.object(httpx.HTTPTransport,'handle_request',external),redirect_stdout(io.StringIO()),redirect_stderr(io.StringIO()):
            # Public legacy-compatible CLI writes the same unscoped ledger as the
            # pre-upgrade collector; no database/private ledger manipulation.
            collect(['--url','https://example.edu/first','--html',str(source),'--output',str(self.folder/'old-output'),'--fetch-mode','supplement','--model-mode','assist','--allow-paid','--paid-max-calls','2','--paid-attempts',str(data/'paid-attempts')],key_loader=lambda:'fake-upgrade-test-key')
            self.assertEqual(len(calls),2)
            service=BatchService(data)
            path=workbook(self.folder/'two.xlsx',[(1,'https://example.edu/first'),(1,'https://example.edu/second')])
            ident=service.import_files([path])['id']
            service.enqueue(ident,live=True,fetch_mode='supplement',model_mode='assist',allow_paid=True,paid_max_calls=2)
            service=BatchService(data)
            service.run(ident,key_loader=lambda:'fake-upgrade-test-key')
            self.assertEqual(calls,['/v1/tools/fetch','/chat/completions'])

    def package(self, private=False):
        isolated=self.folder/'source'
        if not isolated.exists():
            isolated.mkdir()
            tracked=subprocess.check_output(['git','ls-files','-z','--','Mission C'],cwd=ROOT.parent).decode().split('\0')
            for name in filter(None,tracked):
                destination=isolated/Path(name).relative_to('Mission C')
                destination.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(ROOT.parent/name,destination)
            for name in ('mission_c/data/input.html','mission_c/outputs/source.html','mission_c/cache/page.html','mission_c/.private/fake_credential.py','mission_c/extra.py','mission_c/delivery_static/extra.js'):
                path=isolated/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('fictional-excluded-content')
        output=self.folder/('PRIVATE.zip' if private else 'ordinary.zip')
        options=[]
        if private:
            profile=self.folder/'deployment.json';profile.write_text(json.dumps({'profile':'deepseek-private-v1','key_file':'credential.txt'}))
            (self.folder/'credential.txt').write_text('fake-review-package-key')
            options=['--private-config',str(profile)]
        result=subprocess.run([sys.executable,str(isolated/'build_package.py'),'--output',str(output),*options],capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))
        return output

    def test_packages_exclude_planted_nested_runtime_private_and_unlisted_source_files(self):
        for private in (False,True):
            with zipfile.ZipFile(self.package(private)) as archive:
                self.assertTrue(all(b'fictional-excluded-content' not in archive.read(n) for n in archive.namelist()))
                payloads=[n for n in archive.namelist() if '/.private/' in n]
                self.assertEqual(sorted(payloads),['Mission C/.private/credential.txt','Mission C/.private/deployment.json'] if private else [])

    def test_package_modes_are_portable_unix_scripts_and_private_credentials(self):
        for private in (False,True):
            with zipfile.ZipFile(self.package(private)) as archive:
                for item in archive.infolist():
                    self.assertEqual(item.create_system,3,item.filename)
                    expected=0o600 if '/.private/' in item.filename else 0o755 if item.filename.endswith('.sh') else 0o644
                    self.assertEqual(stat.S_IMODE(item.external_attr>>16),expected,item.filename)
                self.assertIn('Mission C/examples/assisted-cache/manifest.json',archive.namelist())
                self.assertIn('Mission C/schedule-examples/cron.example',archive.namelist())


if __name__=='__main__': unittest.main()
