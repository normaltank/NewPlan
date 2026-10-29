"""Real local sockets exercise status GET recovery without retrying mutations."""
from contextlib import contextmanager
import json
from itertools import count
from pathlib import Path
import socket
import socketserver
import struct
import sys
import tempfile
import threading
import time
import unittest

import httpx
import test_web
from test_web_browser import WebServer


@contextmanager
def resetting_peer(always=False):
    events = []
    reset = [True]
    connections = count()

    class Peer(socketserver.StreamRequestHandler):
        def handle(self):
            connection = next(connections)
            while True:
                line = self.rfile.readline()
                if not line:
                    return
                method, path, _ = line.decode().strip().split(' ')
                while self.rfile.readline() not in (b'\r\n', b'\n', b''):
                    pass
                events.append((method, path, connection))
                if path.startswith('/api/batches/') and (always or reset[0]):
                    reset[0] = False
                    self.request.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER,
                        struct.pack('hh' if sys.platform == 'win32' else 'ii', 1, 0))
                    return
                body = json.dumps({'queued':False, 'processed':1}).encode()
                self.wfile.write(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: '
                    + str(len(body)).encode() + b'\r\n\r\n' + body)
                self.wfile.flush()

    class Server(socketserver.ThreadingTCPServer):
        daemon_threads = True

        def shutdown_request(self, request):
            # TCPServer normally sends FIN before close, which masks SO_LINGER's
            # RST as EOF. Close directly to reproduce the CI ReadError boundary.
            self.close_request(request)

    server = Server(('127.0.0.1', 0), Peer)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_address[1]}', events
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class StatusPolling(unittest.TestCase):
    def test_warm_status_connection_reset_recovers_on_new_connection(self):
        with resetting_peer() as (url, events):
            with httpx.Client(base_url=url, trust_env=False, timeout=2) as client:
                self.assertEqual(client.get('/warm').status_code, 200)
                value = test_web.HTTPFlow().until(client, 'synthetic', lambda value:not value['queued'])
                self.assertEqual(value, {'queued':False, 'processed':1})
                self.assertEqual([event[:2] for event in events],
                    [('GET','/warm'), ('GET','/api/batches/synthetic'), ('GET','/api/batches/synthetic')])
                self.assertEqual(events[0][2], events[1][2])
                self.assertNotEqual(events[1][2], events[2][2])

    def test_persistent_status_resets_fail_with_bounded_attempts_and_diagnostic(self):
        with resetting_peer(always=True) as (url, events):
            with httpx.Client(base_url=url, trust_env=False, timeout=2) as client:
                self.assertEqual(client.get('/warm').status_code, 200)
                started = time.monotonic()
                with self.assertRaisesRegex(AssertionError, 'status GET.*ReadError'):
                    test_web.HTTPFlow().until(client, 'synthetic', lambda value:not value['queued'])
                self.assertLess(time.monotonic()-started, 3)
                self.assertLessEqual(len(events), 4)
                self.assertTrue(all(event[0] == 'GET' for event in events))

    def test_exited_web_process_fails_with_return_code_and_service_log(self):
        with tempfile.TemporaryDirectory() as temporary:
            server = WebServer(Path(temporary))
            try:
                with httpx.Client(base_url=server.url, trust_env=False, timeout=2) as client:
                    self.assertEqual(client.get('/api/config').status_code, 200)
                    server.close()
                    flow = test_web.HTTPFlow()
                    flow.http_servers = {server.url:server}
                    with self.assertRaisesRegex(AssertionError, r'server exited.*returncode=.*server.log'):
                        flow.until(client, 'synthetic', lambda value:not value['queued'])
            finally:
                server.close()
