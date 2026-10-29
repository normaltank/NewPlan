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


if __name__ == '__main__':
    unittest.main()
