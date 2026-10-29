"""Private delivery exercised through HTTP, with external HTTP transport faked."""
from contextlib import ExitStack
import gc
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mission_c.web import create_app
from test_web import workbook


class PrivateDelivery(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.addCleanup(gc.collect)
        self.folder = Path(temporary.name)
        self.context = ExitStack()
        self.addCleanup(lambda: self.context.close())
        self.profile = self.folder/'private.json'
        self.profile.write_text(json.dumps({'profile':'deepseek-private-v1','key_file':'credential.txt'}))

    def client(self):
        client = TestClient(create_app(self.folder/'data', private_config=self.profile), headers={'X-Mission-C':'1'}, base_url='http://localhost')
        self.context.close()
        self.context = ExitStack()
        return self.context.enter_context(client)

    def upload(self, client, slug='one'):
        path = workbook(self.folder/(slug+'.xlsx'), [(1,'https://example.edu/'+slug),(2,'https://example.edu/'+slug)])
        response = client.post('/api/import', files={'files':(path.name,path.read_bytes())})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['total'],1)
        return response.json()['id']

    def done(self, client, ident):
        for _ in range(200):
            result = client.get('/api/batches/'+ident).json()
            if not result['queued']:
                time.sleep(.1)
                return result
            time.sleep(.03)
        self.fail(str(result))

    def test_missing_private_credential_is_lazy_and_start_fails_closed(self):
        with patch.object(httpx.HTTPTransport,'handle_request',side_effect=AssertionError('unexpected network')):
            client=self.client()
            self.assertEqual(client.get('/').status_code,200)
            ident=self.upload(client)
            response=client.post('/api/batches/'+ident+'/delivery-start')
            self.assertEqual(response.status_code,400,response.text)
            self.assertIn('私人',response.text)
            self.assertFalse(client.get('/api/batches/'+ident).json()['queued'])
            demo=client.post('/api/demo').json()['id']
            self.assertEqual(client.post('/api/batches/'+demo+'/delivery-start').status_code,200)
            self.assertEqual(self.done(client,demo)['delivery_counts']['teachers'],1)

    def test_private_start_uses_two_calls_per_unique_page_across_batches_and_restart(self):
        key='fake-private-fixture-key'
        (self.folder/'credential.txt').write_text(key)
        calls=[]
        html='<main><h1>李明</h1><p>姓名：李明</p><p>职称：教授</p><p>本人邮箱：liming@example.edu</p><p>研究方向：光学。完整个人经历。</p></main>'
        def external(transport, request):
            if request.url.host == 'api.deepseek.com':
                self.assertEqual(request.headers['Authorization'],'Bearer '+key)
                calls.append(request.url.path)
                if request.url.path.endswith('/fetch'):
                    self.assertIn('url',json.loads(request.content))
                    return httpx.Response(200,json={'title':'李明','content':'姓名：李明\n职称：教授\n完整个人经历。'})
                return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps({'url':json.loads(json.loads(request.content)['messages'][1]['content'])['url'],'name':{'value':'李明','evidence':'姓名：李明'},'title':{'value':'教授','evidence':'职称：教授'},'email':{'value':'liming@example.edu','evidence':'本人邮箱：liming@example.edu'},'body_selector':'main'})}}]})
            self.assertEqual(request.url.host,'example.edu')
            if request.url.path == '/robots.txt': return httpx.Response(404)
            return httpx.Response(200,text=html,headers={'content-type':'text/html; charset=utf-8'})
        with patch.object(httpx.HTTPTransport,'handle_request',external):
            client=self.client()
            for slug in ('one','two'):
                ident=self.upload(client,slug)
                response=client.post('/api/batches/'+ident+'/delivery-start',json={'paid_max_calls':999,'key_file':'elsewhere'})
                self.assertEqual(response.status_code,200,response.text)
                done=self.done(client,ident)
                self.assertEqual(done['delivery_counts'],{'teachers':1,'exceptions':0})
                exports=client.post('/api/batches/'+ident+'/exports').json()['exports']
                archive=client.get(exports[0]['zip_url']).content
                self.assertNotIn(key.encode(),archive)
                self.assertNotIn(key,client.get('/api/batches/'+ident+'/tasks').text)
                client=self.client()  # Same persisted store, fresh app/policy.
            self.assertEqual(calls,['/v1/tools/fetch','/chat/completions']*2)
            # A different school creates another task, but cannot bypass global same-URL dedup.
            path=workbook(self.folder/'overlap.xlsx',[(1,'https://example.edu/one')],school='另一大学')
            ident=client.post('/api/import',files={'files':(path.name,path.read_bytes())}).json()['id']
            self.assertEqual(client.post('/api/batches/'+ident+'/delivery-start').status_code,200)
            self.done(client,ident)
            self.assertEqual(len(calls),4)

    def test_builder_ordinary_is_clean_and_private_package_relocates(self):
        import subprocess
        import zipfile
        root=Path(__file__).resolve().parents[1]
        ordinary=self.folder/'ordinary.zip'
        private=self.folder/'PRIVATE.zip'
        key='fake-portable-private-key'
        (self.folder/'credential.txt').write_text(key)
        for destination, options in ((ordinary,[]),(private,['--private-config',str(self.profile)])):
            result=subprocess.run([sys.executable,str(root/'build_package.py'),'--output',str(destination),*options],capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr.decode())
            self.assertNotIn(key.encode(),result.stdout+result.stderr)
        with zipfile.ZipFile(ordinary) as archive:
            self.assertFalse(any('.private' in n or '/data/' in n or '/outputs/' in n for n in archive.namelist()))
            self.assertTrue(all(key.encode() not in archive.read(n) for n in archive.namelist()))
        relocated=self.folder/'relocated'
        with zipfile.ZipFile(private) as archive: archive.extractall(relocated)
        app=create_app(relocated/'data',private_config=relocated/'Mission C'/'.private'/'deployment.json')
        with TestClient(app,base_url='http://localhost',headers={'X-Mission-C':'1'}) as client:
            ident=self.upload(client)
            self.assertEqual(client.post('/api/batches/'+ident+'/pause').status_code,200)
            self.assertNotIn(key,client.get('/api/config').text)
        gc.collect()


if __name__ == '__main__': unittest.main()
