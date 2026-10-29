"""Real browser delivery flow, public HTTP state and downloaded artifacts only."""
import csv
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
import zipfile

import httpx
from openpyxl import load_workbook
from test_web_browser import WebServer


@unittest.skipUnless(os.environ.get('MISSION_C_BROWSER_TESTS') == '1', 'opt-in real browser')
class DeliveryBrowser(unittest.TestCase):
    def test_upload_preflight_demo_start_reopen_and_real_downloads(self):
        from playwright.sync_api import sync_playwright
        temporary_dir=tempfile.TemporaryDirectory()
        self.addCleanup(temporary_dir.cleanup)
        if temporary_dir:
            temporary=temporary_dir.name
            folder=Path(temporary)
            server=WebServer(folder)
            self.addCleanup(server.close)
            evidence=Path(os.environ.get('MISSION_C_BROWSER_EVIDENCE',temporary))
            evidence.mkdir(parents=True,exist_ok=True)
            events,errors=[],[]
            with sync_playwright() as play:
                channel=os.environ.get('MISSION_C_BROWSER_CHANNEL','msedge')
                browser=play.chromium.launch(**({'channel':channel} if channel!='chromium' else {}),headless=True)
                context=browser.new_context(viewport={'width':1040,'height':1000})
                context.on('request',lambda req:events.append({'method':req.method,'url':req.url}))
                context.on('page',lambda page:page.on('pageerror',lambda error:errors.append(str(error))))
                page=context.new_page()
                page.goto(server.url)
                # The public example download creates synthetic original-format input.
                sample=httpx.get(server.url+'/api/sample.xlsx',trust_env=False).content
                first,second=folder/'原格式甲.xlsx',folder/'原格式乙.xlsx'
                first.write_bytes(sample)
                second.write_bytes(sample)
                page.locator('#files').set_input_files([str(first),str(second)])
                page.get_by_text('已预检 2 个文件，共 3 个待处理条目。',exact=True).wait_for()
                uploaded=page.url.split('batch=')[1]
                before=httpx.get(server.url+'/api/batches/'+uploaded,trust_env=False).json()
                self.assertEqual(before['preflight']['duplicate_rows'],5)
                self.assertEqual(before['processed'],0)
                self.assertFalse(before['queued'])
                self.assertIn('原格式甲.xlsx',page.locator('#file-names').inner_text())
                page.screenshot(path=str(evidence/'simple-01-upload.png'),full_page=True)
                page.get_by_role('button',name='离线试用 / 查看示例').click()
                page.get_by_text('离线示例已准备，共 3 个待处理条目。',exact=True).wait_for()
                ident=page.url.split('batch=')[1]
                page.get_by_role('button',name='开始离线试用',exact=True).click()
                selected=page.url
                page.close()
                page=context.new_page()
                page.goto(selected)
                page.get_by_text('处理完成',exact=True).wait_for(timeout=30000)
                page.get_by_text('已处理 3 / 3 条',exact=True).wait_for()
                self.assertEqual(page.locator('#progress-percent').inner_text(),'100%')
                self.assertIn('待核或失败 2 条',page.locator('#status-text').inner_text())
                completed=httpx.get(server.url+'/api/batches/'+ident,trust_env=False).json()
                page.reload()
                page.get_by_role('link',name='下载教师 Excel',exact=True).wait_for()
                self.assertEqual(httpx.get(server.url+'/api/batches/'+ident,trust_env=False).json(),completed)
                with page.expect_download() as download:
                    page.get_by_role('link',name='下载教师 Excel',exact=True).click()
                download.value.save_as(str(evidence/'simple-teachers.xlsx'))
                with page.expect_download() as download:
                    page.get_by_role('link',name='下载全文与来源 ZIP',exact=True).click()
                download.value.save_as(str(evidence/'simple-sources.zip'))
                page.screenshot(path=str(evidence/'simple-02-complete.png'),full_page=True)
                page.set_viewport_size({'width':375,'height':812})
                page.screenshot(path=str(evidence/'simple-03-mobile.png'),full_page=True)
                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),375)
                # Reopening the bare URL restores this browser's latest batch.
                page.goto(server.url)
                page.get_by_text('处理完成',exact=True).wait_for()
                self.assertIn(ident,page.url)
                self.assertEqual(errors,[])
                self.assertTrue(all(e['url'].startswith((server.url,'edge://')) for e in events),events)
                (evidence/'simple-browser-events.json').write_text(json.dumps(events,ensure_ascii=False,indent=2),encoding='utf-8')
                browser.close()
                self._audit(evidence)

    def _audit(self,evidence):
        book=load_workbook(evidence/'simple-teachers.xlsx')
        self.assertEqual(book.sheetnames,['有邮箱教师','无邮箱教师','主页失效教师'])
        self.assertEqual(sum(sheet.max_row-1 for sheet in book),1)
        self.assertEqual(book.worksheets[0]['B2'].value,'李明')
        self.assertEqual(book.worksheets[0]['D2'].value,'liming@example.edu')
        book.close()
        with zipfile.ZipFile(evidence/'simple-sources.zip') as archive:
            exceptions=list(csv.DictReader(io.StringIO(archive.read('exceptions.csv').decode('utf-8-sig'))))
            self.assertEqual(len(exceptions),2)
            records=json.loads(archive.read('records.json'))
            teacher=next(r for r in records if r.get('name')=='李明')
            self.assertIn('虚构离线教师正例，研究光学。',archive.read(teacher['biography_file']).decode('utf-8'))
            self.assertIn(b'<main>',archive.read(teacher['source_file']))

    def test_bad_selection_cannot_start_previous_batch_and_broken_file_is_explained(self):
        from playwright.sync_api import sync_playwright
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        folder=Path(temporary.name)
        server=WebServer(folder)
        self.addCleanup(server.close)
        evidence=Path(os.environ.get('MISSION_C_BROWSER_EVIDENCE',temporary.name))
        evidence.mkdir(parents=True,exist_ok=True)
        with sync_playwright() as play:
            channel=os.environ.get('MISSION_C_BROWSER_CHANNEL','msedge')
            browser=play.chromium.launch(**({'channel':channel} if channel!='chromium' else {}),headless=True)
            page=browser.new_page()
            page.goto(server.url)
            page.get_by_role('button',name='离线试用 / 查看示例').click()
            page.get_by_role('button',name='开始离线试用').wait_for()
            previous=page.url.split('batch=')[1]
            page.locator('#files').set_input_files([{'name':f'{n}.xlsx','mimeType':'application/octet-stream','buffer':b'broken'} for n in range(21)])
            page.get_by_role('alert').get_by_text('每批最多 20 个 Excel 文件',exact=False).wait_for()
            self.assertFalse(page.get_by_role('button',name='开始离线试用').is_visible())
            self.assertFalse(httpx.get(server.url+'/api/batches/'+previous,trust_env=False).json()['queued'])
            sample=httpx.get(server.url+'/api/sample.xlsx',trust_env=False).content
            page.locator('#files').set_input_files([{'name':'原表.xlsx','mimeType':'application/octet-stream','buffer':sample},{'name':'损坏.xlsx','mimeType':'application/octet-stream','buffer':b'broken'}])
            page.get_by_text('已预检 2 个文件，共 3 个待处理条目。',exact=True).wait_for()
            page.locator('#issue-title').click()
            page.get_by_text('损坏.xlsx · 文件无法读取，请确认是完整的 XLSX 文件后重新选择。',exact=True).wait_for()
            page.get_by_role('button',name='开始采集',exact=True).click()
            page.get_by_role('alert').get_by_text('当前服务尚未开放网页处理',exact=False).wait_for()
            page.screenshot(path=str(evidence/'simple-04-input-errors.png'),full_page=True)
            browser.close()

    def test_explicit_online_start_pause_service_restart_and_resume(self):
        from collections import Counter
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from playwright.sync_api import sync_playwright
        from test_web import workbook
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        folder=Path(temporary.name)
        calls=Counter()
        entered,release=threading.Event(),threading.Event()
        class Source(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_GET(self):
                if self.path=='/robots.txt': content=b'User-agent: *\nAllow: /\n'
                else:
                    calls[self.path]+=1
                    if self.path=='/b':
                        entered.set()
                        release.wait(30)
                    content='<main><h1>李明</h1><p>姓名：李明</p><p>职称：教授</p><p>本人邮箱：liming@example.edu</p><p>虚构本机个人简介。</p></main>'.encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type','text/html; charset=utf-8')
                self.send_header('Content-Length',str(len(content)))
                self.end_headers()
                self.wfile.write(content)
        source=ThreadingHTTPServer(('127.0.0.1',0),Source)
        self.addCleanup(source.server_close)
        self.addCleanup(source.shutdown)
        threading.Thread(target=source.serve_forever,daemon=True).start()
        base=f'http://127.0.0.1:{source.server_port}'
        original=workbook(folder/'原表.xlsx',[(1,base+'/a'),(1,base+'/b'),(2,base+'/c')])
        server=WebServer(folder,'--allow-live')
        self.addCleanup(server.close)
        self.addCleanup(release.set)
        evidence=Path(os.environ.get('MISSION_C_BROWSER_EVIDENCE',temporary.name))
        evidence.mkdir(parents=True,exist_ok=True)
        with sync_playwright() as play:
            channel=os.environ.get('MISSION_C_BROWSER_CHANNEL','msedge')
            browser=play.chromium.launch(**({'channel':channel} if channel!='chromium' else {}),headless=True)
            page=browser.new_page()
            errors,events=[],[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('request',lambda r:events.append(r.url))
            page.goto(server.url)
            page.locator('#files').set_input_files(str(original))
            page.get_by_role('button',name='开始采集',exact=True).wait_for()
            self.assertEqual(dict(calls),{})
            ident=page.url.split('batch=')[1]
            page.get_by_role('button',name='开始采集',exact=True).click()
            self.assertTrue(entered.wait(25))
            page.get_by_role('button',name='暂停处理',exact=True).click()
            page.get_by_text('已暂停',exact=True).wait_for()
            release.set()
            for _ in range(150):
                status=httpx.get(server.url+'/api/batches/'+ident,trust_env=False).json()
                if status['processed']==2 and status['running']==0: break
                time.sleep(.1)
            self.assertEqual(status['processed'],2)
            self.assertEqual(dict(calls),{'/a':1,'/b':1})
            page.screenshot(path=str(evidence/'simple-05-paused.png'),full_page=True)
            server.close()
            restarted=WebServer(folder,'--allow-live')
            self.addCleanup(restarted.close)
            page.goto(restarted.url+'/?batch='+ident)
            page.get_by_role('button',name='继续处理',exact=True).wait_for()
            self.assertEqual(dict(calls),{'/a':1,'/b':1})
            page.get_by_role('button',name='继续处理',exact=True).click()
            page.get_by_text('处理完成',exact=True).wait_for(timeout=30000)
            page.get_by_role('link',name='下载教师 Excel',exact=True).wait_for()
            self.assertEqual(dict(calls),{'/a':1,'/b':1,'/c':1})
            self.assertTrue(all(u.startswith((server.url,restarted.url,'edge://')) for u in events),events)
            self.assertEqual(errors,[])
            (evidence/'simple-local-online.json').write_text(json.dumps({'source_calls':dict(calls),'browser_urls':events,'page_errors':errors},indent=2),encoding='utf-8')
            page.screenshot(path=str(evidence/'simple-06-online-resumed.png'),full_page=True)
            browser.close()


if __name__=='__main__':
    unittest.main()
