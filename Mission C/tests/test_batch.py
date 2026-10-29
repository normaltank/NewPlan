import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from openpyxl import Workbook
ROOT = Path(__file__).resolve().parents[1]

class BatchContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.data = self.folder / '中文 data'
        self.input = self.folder / '原表.xlsx'
        book = Workbook()
        sheet = book.active
        sheet.title = 'Sheet1'
        sheet.append(['ID', '学校', '学院', '师资URL'])
        sheet.append([1, '虚构大学', '光学院', 'https://example.edu/list'])
        sheet.append([1, '虚构大学', '光学院', 'https://example.edu/list2'])
        sheet.append([2, '虚构大学', '理学院', 'https://example.edu/science'])
        sheet = book.create_sheet('Sheet2')
        sheet.append(['学院ID', '个人URL'])
        sheet.append([1, 'https://example.edu/teacher#bio'])
        sheet.append([2, 'https://example.edu/teacher'])
        sheet.append([99, 'https://example.edu/orphan'])
        sheet.append([1, 'bad'])
        book.save(self.input)
    def cli(self, *args, ok=True):
        p = subprocess.run([sys.executable, str(ROOT/'batch.py'), '--data-root', str(self.data), *map(str,args)], capture_output=True, encoding='utf-8', errors='replace')
        if ok: self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout) if ok else p
    def test_preview_import_visible_batch_and_idempotent_content(self):
        preview = self.cli('preview', self.input)
        self.assertFalse(self.data.exists())
        self.assertEqual(len(preview['tasks']), 1)
        self.assertEqual(len(preview['tasks'][0]['relations']), 2)
        self.assertEqual(len(preview['issues']), 2)
        imported = self.cli('import', self.input)
        batch = self.cli('status', imported['id'])
        self.assertEqual(batch['counts']['pending'], 1)
        self.assertEqual(len(batch['tasks'][0]['sources']), 2)
        self.assertEqual(batch['tasks'][0]['relations'][0]['faculty_urls'], ['https://example.edu/list', 'https://example.edu/list2'])
        self.assertEqual(self.cli('import', self.input)['id'], imported['id'])
        self.assertEqual(len(self.cli('list')), 1)
    def cache(self):
        source = self.folder/'page.html'
        source.write_text('<meta charset="utf-8"><main><h1>李明</h1><p>职称：教授</p><p>本人邮箱：liming@example.edu</p><h2>个人简介</h2><p>研究光学。</p></main>', encoding='utf-8')
        import hashlib
        manifest = self.folder/'cache.json'
        manifest.write_text(json.dumps({'version':1,'entries':[{'url':'https://example.edu/teacher', 'source':{'path':'page.html','sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'observed_at':'2026-10-28T01:00:00Z'}}]}), encoding='utf-8')
        return manifest
    def test_run_pause_resume_keeps_bound_artifacts_and_detects_missing(self):
        batch = self.cli('import', self.input)
        ident = batch['id']
        self.cli('pause', ident)
        self.assertEqual(self.cli('run', ident, '--cache-manifest', self.cache())['counts'], {'pending':1})
        self.cli('resume', ident)
        result = self.cli('run', ident, '--cache-manifest', self.cache())
        task = result['tasks'][0]
        self.assertNotIn(task['state'], ['pending','running','failed'])
        artifact = self.data/task['artifact']
        original = {str(p.relative_to(artifact)):p.read_bytes() for p in artifact.rglob('*') if p.is_file()}
        self.cli('run', ident, '--cache-manifest', self.cache())
        self.assertEqual(original, {str(p.relative_to(artifact)):p.read_bytes() for p in artifact.rglob('*') if p.is_file()})
        (artifact/'0001/biography.txt').unlink()
        missing = self.cli('status', ident)
        self.assertEqual(missing['tasks'][0]['state'], 'artifact_missing')
        self.assertEqual(self.cli('run', ident, '--cache-manifest', self.cache())['tasks'][0]['state'], 'artifact_missing')
    def test_queued_cache_survives_input_removal_and_data_root_move(self):
        ident = self.cli('import', self.input)['id']
        self.cli('enqueue', ident, '--cache-manifest', self.cache())
        (self.folder/'cache.json').unlink()
        (self.folder/'page.html').unlink()
        import shutil
        moved = self.folder/'moved 数据'
        shutil.move(self.data, moved)
        self.data = moved
        self.assertTrue(self.cli('status', ident)['queued'])
        done = self.cli('run', ident)
        self.assertFalse(done['queued'])
        self.assertIn(done['tasks'][0]['state'], ['success','review'])
    def test_public_process_pause_concurrency_and_kill_recovery(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import threading, time
        entered, release = threading.Event(), threading.Event()
        blocked = ['/b']
        requests = []
        class Site(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_GET(self):
                requests.append(self.path)
                if self.path in blocked:
                    entered.set()
                    release.wait(30)
                body = b'User-agent: *\nAllow: /\n' if self.path == '/robots.txt' else '<meta charset="utf-8"><main><h1>王明</h1><p>职称：教授</p><p>研究光学。</p></main>'.encode()
                try:
                    self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.end_headers()
                    self.wfile.write(body)
                except OSError: pass
        server = ThreadingHTTPServer(('127.0.0.1',0),Site)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        base = f'http://127.0.0.1:{server.server_port}'
        book = Workbook(); sheet=book.active; sheet.title='Sheet1'
        sheet.append(['ID','学校','学院','师资URL']); sheet.append([1,'虚构大学','理学院',base+'/list'])
        sheet=book.create_sheet('Sheet2');sheet.append(['学院ID','个人URL'])
        for suffix in ('/a','/b','/c'): sheet.append([1,base+suffix])
        book.save(self.input)
        ident=self.cli('import',self.input)['id']
        self.cli('enqueue',ident,'--live')
        def start():
            process=subprocess.Popen([sys.executable,str(ROOT/'batch.py'),'--data-root',str(self.data),'run',ident],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            self.addCleanup(lambda: process.kill() if process.poll() is None else None)
            return process
        worker=start()
        self.assertTrue(entered.wait(30),'second page not started')
        concurrent=self.cli('run',ident,ok=False)
        self.assertEqual(concurrent.returncode,2)
        self.assertIn('批次正在由另一进程执行',concurrent.stderr)
        self.cli('pause',ident)
        release.set()
        out,err=worker.communicate(timeout=30)
        self.assertEqual(worker.returncode,0,err)
        paused=json.loads(out)
        self.assertEqual(paused['counts'].get('pending'),1)
        self.assertEqual(requests.count('/a'),1)
        self.assertEqual(requests.count('/b'),1)
        first_artifact=self.data/paused['tasks'][0]['artifact']
        first_json=(first_artifact/'teachers.json').read_bytes()
        blocked[:]=['/c'];entered.clear();release.clear()
        self.cli('resume',ident)
        worker=start()
        self.assertTrue(entered.wait(30),'third page not started')
        worker.kill();worker.communicate(timeout=10);release.set();blocked.clear()
        finished=self.cli('run',ident)
        self.assertNotIn('pending',finished['counts'])
        self.assertNotIn('running',finished['counts'])
        self.assertEqual(requests.count('/a'),1)
        self.assertEqual(requests.count('/b'),1)
        self.assertEqual((first_artifact/'teachers.json').read_bytes(),first_json)
    def test_university_zip_has_contract_order_full_text_and_relative_evidence(self):
        import zipfile, io
        from openpyxl import load_workbook
        manifest=self.cache()
        long='完整研究经历与成果。'*5000
        (self.folder/'page.html').write_text('<meta charset="utf-8"><main><h1>李明</h1><p>本人邮箱：liming@example.edu</p><p>'+long+'</p></main>',encoding='utf-8')
        import hashlib
        value=json.loads(manifest.read_text());value['entries'][0]['source']['sha256']=hashlib.sha256((self.folder/'page.html').read_bytes()).hexdigest()
        value['entries'] += [{'url':'https://example.edu/failed','source':{'http_status':404,'error':{'code':'http_404','message':'实际访问404'},'observed_at':'2026-10-28T01:00:00Z'}}]
        manifest.write_text(json.dumps(value),encoding='utf-8')
        from openpyxl import load_workbook
        book=load_workbook(self.input);book['Sheet2'].append([1,'https://example.edu/failed']);book['Sheet2'].append([1,'https://example.edu/missing']);book.save(self.input);book.close()
        ident=self.cli('import',self.input)['id']
        done=self.cli('run',ident,'--cache-manifest',manifest)
        self.assertEqual(done['state'],'completed_with_gaps')
        exported=self.cli('export',ident)
        self.assertEqual(len(exported['exports']),1)
        archive=self.data/exported['exports'][0]['path']
        with zipfile.ZipFile(archive) as package:
            book=load_workbook(io.BytesIO(package.read('teachers.xlsx')))
            self.assertEqual(book.sheetnames,['有邮箱教师','无邮箱教师','主页失效教师'])
            self.assertEqual(list(book.worksheets[0].values)[0],('序号','姓名','职称','邮箱','学校','学院','采集人','采集日期','简介','主页'))
            numbers=[row[0] for sheet in book for row in list(sheet.values)[1:]]
            self.assertEqual(numbers,list(range(1,len(numbers)+1)))
            self.assertEqual(book['主页失效教师'].max_row,1)
            self.assertEqual(book['无邮箱教师'].max_row,1)
            records=json.loads(package.read('teachers.json'))
            good=next(r for r in records if r['requested_url']=='https://example.edu/teacher')
            self.assertIn(long,package.read(good['biography_file']).decode())
            self.assertIn('光学院',good['input_metadata']['college']);self.assertIn('理学院',good['input_metadata']['college'])
            self.assertIn(good['source_file'],package.namelist())
            self.assertIn(long,package.read('teachers.csv').decode('utf-8-sig'))
            self.assertIn('relations.csv',package.namelist())
            self.assertIn('batch.json',package.namelist())
            snapshot=json.loads(package.read('batch.json'))
            for task in snapshot['tasks']:
                if task['artifact']: self.assertIn(task['artifact']+'/binding.json',package.namelist())
    def test_offline_demo_produces_download_without_external_input(self):
        demo=self.cli('demo')
        self.assertEqual(demo['batch']['completeness'],'not_verified')
        self.assertTrue((self.data/demo['delivery']['exports'][0]['path']).is_file())
        self.assertEqual(len(demo['batch']['tasks']),3)
    def test_bad_workbook_conflicting_id_and_same_url_other_school_are_visible(self):
        broken=self.folder/'坏文件.xlsx';broken.write_bytes(b'not a zip')
        second=self.folder/'另一校.xlsx'
        book=Workbook();sheet=book.active;sheet.title='Sheet1'
        sheet.append(['ID','学校','学院','师资URL']);sheet.append([1,'另一大学','理学院','https://example.edu/list'])
        sheet.append([3,'另一大学','A学院','']);sheet.append([3,'另一大学','B学院',''])
        sheet=book.create_sheet('Sheet2');sheet.append(['学院ID','个人URL']);sheet.append([1,'https://example.edu/teacher']);sheet.append([3,'https://example.edu/conflict'])
        book.save(second);book.close()
        result=self.cli('import',self.input,second,broken)
        self.assertEqual(len(result['tasks']),2)
        self.assertEqual({t['school'] for t in result['tasks']},{'虚构大学','另一大学'})
        self.assertEqual(len(result['issues']),5)
        self.assertEqual({t['url'] for t in result['tasks']},{'https://example.edu/teacher'})
    def test_non_personal_and_maintenance_inputs_keep_evidence_outside_teacher_sheets(self):
        from openpyxl import load_workbook
        import hashlib, zipfile, io
        book=load_workbook(self.input);sheet=book['Sheet2']
        for suffix in ('home','maintenance','uncertain','news'):sheet.append([1,'https://example.edu/'+suffix])
        book.save(self.input);book.close()
        manifest=self.cache();value=json.loads(manifest.read_text())
        pages={'news':'<title>李明教授参加学术报告会</title><article class="news"><time>2026-10-28</time><h1>李明教授参加学术报告会</h1><p>李明教授应邀参加会议并作报告。</p></article>', 'home':'<title>光学院首页</title><main><h1>光学院</h1><nav>学院概况 师资队伍 新闻动态 人才培养</nav><p>欢迎访问光学院官方网站</p></main>', 'maintenance':'<title>网站维护中</title><main><h1>系统维护</h1><p>网站正在升级维护，请稍后访问。</p></main>', 'uncertain':'<main><p>研究领域涉及光学与通信。材料尚需核对。</p></main>'}
        for suffix,html in pages.items():
            path=self.folder/(suffix+'.html');path.write_text(html,encoding='utf-8')
            value['entries'].append({'url':'https://example.edu/'+suffix,'source':{'path':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'http_status':200}})
        manifest.write_text(json.dumps(value),encoding='utf-8')
        ident=self.cli('import',self.input)['id']
        done=self.cli('run',ident,'--cache-manifest',manifest)
        classes={t['url'].rsplit('/',1)[-1]:t['quality']['category'] for t in done['tasks']}
        self.assertEqual(classes,{'teacher':'personal_candidate','home':'suspected_non_personal','maintenance':'temporarily_unavailable','uncertain':'identity_review','news':'suspected_non_personal'})
        self.assertEqual(done['quality_counts']['temporarily_unavailable'],1)
        delivery=self.cli('export',ident)
        with zipfile.ZipFile(self.data/delivery['exports'][0]['path']) as package:
            book=load_workbook(io.BytesIO(package.read('teachers.xlsx')))
            self.assertEqual(sum(s.max_row-1 for s in book),1)
            all_records=json.loads(package.read('records.json'))
            self.assertEqual(len(all_records),5)
            self.assertIn('exceptions.csv',package.namelist())
            for record in all_records:
                self.assertIn(record['source_file'],package.namelist())
    def test_personal_navigation_and_research_terms_do_not_override_identity(self):
        import hashlib
        manifest=self.cache()
        source=self.folder/'page.html'
        source.write_text('<title>李明-师资队伍-学院首页</title><nav>学院首页 师资队伍 系统维护 安全验证</nav><main><h1>李明</h1><p>职称：教授</p><p>本人邮箱：liming@example.edu</p><h2>研究方向</h2><p>研究系统维护与安全验证方法。</p></main>',encoding='utf-8')
        value=json.loads(manifest.read_text());value['entries'][0]['source']['sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
        manifest.write_text(json.dumps(value),encoding='utf-8')
        ident=self.cli('import',self.input)['id']
        done=self.cli('run',ident,'--cache-manifest',manifest)
        self.assertEqual(done['tasks'][0]['quality']['category'],'personal_candidate')
    def test_secondary_section_name_without_primary_identity_stays_out_of_delivery(self):
        import zipfile
        demo=self.cli('demo')
        task=next(t for t in demo['batch']['tasks'] if t['url']=='https://example.edu/demo')
        record=json.loads((self.data/task['artifact']/'teachers.json').read_text(encoding='utf-8'))[0]
        self.assertEqual(record['name'],'完整经历')
        self.assertEqual(task['quality']['category'],'identity_review')
        self.assertFalse(task['quality']['eligible_for_workbook'])
        with zipfile.ZipFile(self.data/demo['delivery']['exports'][0]['path']) as package:
            delivered=json.loads(package.read('teachers.json'))
            all_records=json.loads(package.read('records.json'))
            self.assertNotIn('完整经历',[r['name'] for r in delivered])
            self.assertIn('完整经历',[r['name'] for r in all_records])
            self.assertGreaterEqual(len(delivered),1)
    def test_prepare_demo_waits_for_explicit_queue_and_runs_same_offline_materials(self):
        import zipfile
        prepared=self.cli('demo','--prepare-only')
        batch=prepared['batch']
        self.assertEqual(batch['counts'],{'pending':3})
        self.assertFalse(batch['queued'])
        self.assertIsNone(batch['run_options'])
        self.assertTrue(all(t['artifact'] is None for t in batch['tasks']))
        self.assertFalse((self.data/'results').exists())
        self.assertFalse((self.data/'exports').exists())
        manifest=self.data/prepared['cache_manifest']
        self.assertTrue(manifest.is_file())
        queued=self.cli('enqueue',batch['id'],'--cache-manifest',manifest)
        self.assertTrue(queued['queued'])
        done=self.cli('run',batch['id'])
        self.assertEqual(done['quality_counts'],{'identity_review':1,'origin_unavailable':1,'personal_candidate':1})
        delivery=self.cli('export',batch['id'])
        with zipfile.ZipFile(self.data/delivery['exports'][0]['path']) as archive:
            self.assertEqual([r['name'] for r in json.loads(archive.read('teachers.json'))],['李明'])
            self.assertIn('完整经历',[r['name'] for r in json.loads(archive.read('records.json'))])
