"""Opt-in real Edge/Chromium exercise of the local page (no external network)."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest

import httpx

ROOT = Path(__file__).resolve().parents[1]


class WebServer:
    def __init__(self, folder, *options):
        self.folder = Path(folder)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            self.port = sock.getsockname()[1]
        self.url = f'http://127.0.0.1:{self.port}'
        self.log = (self.folder/'server.log').open('a', encoding='utf-8')
        self.process = subprocess.Popen([sys.executable, str(ROOT/'web.py'), '--data-root',
            str(self.folder/'data'), '--port', str(self.port), *options], stdout=self.log, stderr=self.log)
        try:
            for _ in range(150):
                if self.process.poll() is not None:
                    raise AssertionError((self.folder/'server.log').read_text(encoding='utf-8'))
                try:
                    if httpx.get(self.url+'/api/config', trust_env=False).status_code == 200:
                        break
                except httpx.ConnectError:
                    pass
                time.sleep(.1)
            else:
                raise AssertionError('Local web server did not start')
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=20)
        self.log.close()


@unittest.skipUnless(os.environ.get('MISSION_C_BROWSER_TESTS') == '1', 'opt-in real browser')
class BrowserFlow(unittest.TestCase):
    def test_demo_preview_explicit_start_refresh_and_university_download(self):
        from playwright.sync_api import sync_playwright
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        if temporary:
            folder = Path(temporary.name)
            server = WebServer(folder)
            self.addCleanup(server.close)
            evidence = Path(os.environ.get('MISSION_C_BROWSER_EVIDENCE', temporary.name))
            evidence.mkdir(parents=True, exist_ok=True)
            events = []
            with sync_playwright() as play:
                channel = os.environ.get('MISSION_C_BROWSER_CHANNEL', 'msedge')
                browser = play.chromium.launch(**({'channel':channel} if channel != 'chromium' else {}), headless=True)
                page = browser.new_page(viewport={'width':1360, 'height':1000})
                page_errors = []
                page.on('pageerror', lambda error: page_errors.append(str(error)))
                page.on('request', lambda req: events.append({'method': req.method, 'url':req.url}))
                page.goto(server.url)
                page.get_by_role('button', name='载入离线示例').click()
                page.get_by_text('虚构示例大学', exact=True).first.wait_for()
                page.get_by_text('尚未开始', exact=True).wait_for()
                page.screenshot(path=str(evidence/'01-demo-preflight.png'), full_page=True)
                page.get_by_role('button', name='开始处理', exact=True).click()
                page.get_by_text('处理结束，有待核或失败条目', exact=True).wait_for(timeout=30000)
                selected = page.url
                page.reload()
                page.get_by_text('处理结束，有待核或失败条目', exact=True).wait_for()
                self.assertEqual(page.url, selected)
                page.get_by_text('身份或页面待核', exact=False).first.wait_for()
                page.get_by_text('李明', exact=True).wait_for()
                page.get_by_text('liming@example.edu',exact=False).wait_for()
                self.assertNotIn('完整经历',page.locator('#tasks > tr').first.locator('td').first.inner_text())
                page.screenshot(path=str(evidence/'02-demo-complete.png'), full_page=True)
                page.get_by_role('button', name='准备大学下载').click()
                with page.expect_download() as download_info:
                    page.get_by_role('link', name='下载全文与来源 ZIP').click()
                download_info.value.save_as(str(evidence/'demo-university.zip'))
                self.assertTrue((evidence/'demo-university.zip').is_file())
                self.assertTrue(all(event['url'].startswith(server.url) for event in events), events)
                self.assertEqual(page_errors, [])
                (evidence/'browser-events.json').write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding='utf-8')
                browser.close()

    def test_upload_two_original_workbooks_close_page_and_download(self):
        from playwright.sync_api import sync_playwright
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        folder = Path(temporary.name)
        server = WebServer(folder)
        self.addCleanup(server.close)
        evidence = Path(os.environ.get('MISSION_C_BROWSER_EVIDENCE', temporary.name))
        evidence.mkdir(parents=True, exist_ok=True)
        events, errors = [], []
        with sync_playwright() as play:
            channel = os.environ.get('MISSION_C_BROWSER_CHANNEL', 'msedge')
            browser = play.chromium.launch(**({'channel':channel} if channel != 'chromium' else {}), headless=True)
            context = browser.new_context(viewport={'width':1360,'height':1000})
            context.on('request', lambda req: events.append({'method':req.method, 'url':req.url}))
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(server.url)
            with page.expect_download() as sample_info:
                page.get_by_role('link', name='下载虚构双 Sheet 示例').click()
            first, second = folder/'原格式甲.xlsx', folder/'原格式乙.xlsx'
            sample_info.value.save_as(str(first))
            second.write_bytes(first.read_bytes())
            page.locator('#files').set_input_files([str(first),str(second)])
            page.get_by_role('button', name='上传并预检').click()
            page.get_by_text('输入已保存并完成预检，尚未开始处理。', exact=True).wait_for()
            batch_id = page.url.split('batch=')[1]
            before = httpx.get(server.url+'/api/batches/'+batch_id, trust_env=False).json()
            self.assertEqual(before['preflight']['files'],2)
            self.assertEqual(before['preflight']['unique_tasks'],3)
            self.assertEqual(before['preflight']['duplicate_rows'],5)
            self.assertFalse(before['queued'])
            self.assertEqual(before['processed'],0)
            page.screenshot(path=str(evidence/'03-upload-preflight.png'),full_page=True)
            page.get_by_role('button', name='开始处理',exact=True).click()
            selected_url = page.url
            page.close()
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(selected_url)
            page.get_by_text('处理结束，有待核或失败条目',exact=True).wait_for(timeout=30000)
            completed = httpx.get(server.url+'/api/batches/'+batch_id, trust_env=False).json()
            page.reload()
            page.get_by_text('处理结束，有待核或失败条目',exact=True).wait_for()
            self.assertEqual(httpx.get(server.url+'/api/batches/'+batch_id,trust_env=False).json(),completed)
            page.get_by_role('button', name='准备大学下载').click()
            with page.expect_download() as workbook_info:
                page.get_by_role('link', name='下载教师工作簿',exact=True).click()
            workbook_info.value.save_as(str(evidence/'uploaded-university.xlsx'))
            with page.expect_download() as zip_info:
                page.get_by_role('link',name='下载全文与来源 ZIP',exact=True).click()
            zip_info.value.save_as(str(evidence/'uploaded-university.zip'))
            page.screenshot(path=str(evidence/'04-upload-result-downloads.png'),full_page=True)
            # Edge opens its own downloads-hub after a link download. It is not network I/O.
            self.assertTrue(all(event['url'].startswith((server.url,'edge://')) for event in events),events)
            self.assertEqual(errors,[])
            (evidence/'browser-upload-events.json').write_text(json.dumps(events,ensure_ascii=False,indent=2),encoding='utf-8')
            browser.close()

    def test_untrusted_school_and_filename_are_literal_text(self):
        from openpyxl import Workbook
        from playwright.sync_api import sync_playwright
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        folder=Path(temporary.name)
        original=folder/'输入 & 原表.xlsx'
        name='<img src="http://untrusted.invalid/x" onerror="window.injected=1">'
        book=Workbook()
        book.active.title='Sheet1'
        book.active.append(['ID','学校','学院','师资URL'])
        book.active.append([1,name,'学院','https://example.edu/list'])
        sheet=book.create_sheet('Sheet2')
        sheet.append(['学院ID','个人URL'])
        sheet.append([1,'https://example.edu/person'])
        book.save(original)
        book.close()
        server=WebServer(folder)
        self.addCleanup(server.close)
        with sync_playwright() as play:
            channel=os.environ.get('MISSION_C_BROWSER_CHANNEL','msedge')
            browser=play.chromium.launch(**({'channel':channel} if channel!='chromium' else {}),headless=True)
            page=browser.new_page()
            page.goto(server.url)
            page.locator('#files').set_input_files(str(original))
            page.get_by_role('button',name='上传并预检').click()
            page.get_by_text(name,exact=True).first.wait_for()
            self.assertEqual(page.locator('#schools img').count(),0)
            self.assertIsNone(page.evaluate('window.injected'))
            self.assertIn('输入 & 原表.xlsx',page.locator('#tasks').inner_text())
            evidence=Path(os.environ.get('MISSION_C_BROWSER_EVIDENCE',temporary.name))
            evidence.mkdir(parents=True,exist_ok=True)
            page.screenshot(path=str(evidence/'05-untrusted-text.png'),full_page=True)
            browser.close()

    def test_reopen_paused_batch_shows_its_saved_mode_without_running_sources(self):
        from playwright.sync_api import sync_playwright
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        server=WebServer(Path(temporary.name),'--allow-live')
        self.addCleanup(server.close)
        with httpx.Client(base_url=server.url,headers={'X-Mission-C':'1'},trust_env=False) as client:
            ident=client.post('/api/demo').json()['id']
            client.post('/api/batches/'+ident+'/pause').raise_for_status()
            client.post('/api/batches/'+ident+'/start',json={'mode':'live'}).raise_for_status()
        with sync_playwright() as play:
            channel=os.environ.get('MISSION_C_BROWSER_CHANNEL','msedge')
            browser=play.chromium.launch(**({'channel':channel} if channel!='chromium' else {}),headless=True)
            page=browser.new_page()
            page.goto(server.url+'/?batch='+ident)
            page.get_by_text('已暂停（当前页结束后生效）',exact=True).wait_for()
            self.assertTrue(page.locator('#live').is_checked())
            self.assertEqual(httpx.get(server.url+'/api/batches/'+ident,trust_env=False).json()['processed'],0)
            browser.close()


if __name__ == '__main__':
    unittest.main()
