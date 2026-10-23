"""Verify final-navigation status and cookies using a local browser fixture."""
import asyncio
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import threading
from audit import Fetcher, ROOT, write_json


class Site(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        if self.path == '/start':
            self.send_response(412)
            self.send_header('Set-Cookie', 'missionb_fixture=1; Path=/')
            body = '<html><script>location.href="/ready"</script></html>'
        elif self.path in ('/ready', '/second') and 'missionb_fixture=1' in self.headers.get('Cookie', ''):
            self.send_response(200)
            body = '<title>教师名录</title><div class="roster"><a href="https://profile.invalid/person">张老师</a></div>'
        else:
            self.send_response(403)
            body = 'Cookie missing'
        raw = body.encode()
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


async def main():
    os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(ROOT / '.portable-browser')
    out = ROOT/'outputs'/('browser-recovery-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    out.mkdir()
    server = ThreadingHTTPServer(('127.0.0.1', 0), Site)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        async with Fetcher(out) as fetcher:
            _, first = await fetcher.browser_fetch({'id': 'redirect', 'roster_url': f'http://127.0.0.1:{server.server_port}/start'})
            _, second = await fetcher.browser_fetch({'id': 'session', 'roster_url': f'http://127.0.0.1:{server.server_port}/second'})
        assert [n['status'] for n in first['navigations']] == [412, 200], first
        assert first['status'] == 200 and second['status'] == 200
        result = {'status': 'passed', 'final_document_status': first['status'], 'session_reused': second['status'], 'navigation_statuses': [412, 200]}
        write_json(out/'verification.json', result)
        print(json.dumps({**result, 'out': str(out)}, ensure_ascii=False))
    finally:
        server.shutdown(); thread.join(); server.server_close()


if __name__ == '__main__':
    asyncio.run(main())
