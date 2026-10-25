"""Automatic support mail, observed through task submission and SMTP delivery."""
import base64
from email import policy
from email.parser import BytesParser
import io
import json
import os
from pathlib import Path
import smtplib
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import zipfile
import zlib

import httpx

from app import atomic_json
from lite_app import make_server
from read_lite_log import restore
from runtime_paths import APP_ROOT
from test_distribution import HEAD, ROW
from test_lite import KEY, fixtures, seed, simulated_run

MAIL_PASSWORD = 'synthetic-mail-credential'
MAIL = dict(host='smtp.example.invalid', port=465, sender='sender@example.invalid',
            recipient='owner@example.invalid', password=MAIL_PASSWORD)


class MailTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=APP_ROOT)
        self.root = Path(self.temp.name)
        self.assets = self.root / 'assets'
        self.assets.mkdir()
        atomic_json(self.assets / 'lite_config.json', {'api_key': KEY})
        atomic_json(self.assets / 'mail_config.json', MAIL)
        self.delivered = threading.Event()
        self.messages = []
        self.transports = []
        self.smtp_error = None
        self.login_error = None
        self.close_error = None
        self.gate = None
        outer = self

        class SMTP:
            def __init__(self, host, port, **kwargs):
                outer.transports.append((host, port, kwargs))
            def ehlo(self):
                return 250, b'fixture'
            def login(self, sender, password):
                outer.assertEqual((sender, password), (MAIL['sender'], MAIL_PASSWORD))
                if outer.login_error:
                    raise outer.login_error
            def send_message(self, message, from_addr, to_addrs):
                if outer.gate:
                    outer.gate.wait(5)
                if outer.smtp_error:
                    raise outer.smtp_error
                outer.assertEqual(from_addr, MAIL['sender'])
                outer.assertEqual(to_addrs, [MAIL['recipient']])
                outer.messages.append(BytesParser(policy=policy.default).parsebytes(message.as_bytes()))
                outer.delivered.set()
                return {}
            def close(self):
                if outer.close_error:
                    raise outer.close_error

        self.smtp_patch = patch('smtplib.SMTP_SSL', SMTP)
        self.smtp_patch.start()
        self.start_server()

    def start_server(self):
        with patch('lite_app.ASSETS', self.assets), patch.dict(os.environ, {'DEEPSEEK_API_KEY': ''}):
            self.server = make_server(self.root / 'lite-data')
        self.store = self.server.store
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.client = httpx.Client(base_url=f'http://127.0.0.1:{self.server.server_port}', trust_env=False)
        self.client.post('/api/session', json={'token': self.server.token}).raise_for_status()

    def stop_server(self):
        if self.store.worker:
            self.store.worker.join(10)
        self.client.close()
        self.server.shutdown()
        self.server.server_close()
        if hasattr(self.store, 'close'):
            self.store.close()
        self.thread.join(5)

    def tearDown(self):
        if self.gate:
            self.gate.set()
        self.stop_server()
        self.smtp_patch.stop()
        self.temp.cleanup()

    def run_job(self, runner=simulated_run):
        with patch('app.run', runner):
            response = self.client.post('/api/start', json={'text': HEAD + ROW})
            self.assertEqual(response.status_code, 201, response.text)
            self.store.worker.join(10)
        return self.client.get('/api/state').json()['job']

    def wait_record(self, event):
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            records = [json.loads(line) for line in self.store.journal.path.read_text(encoding='utf-8').splitlines()]
            found = [r for r in records if r['event'] == event]
            if found:
                return found[-1]
            time.sleep(.02)
        self.fail('Missing support event: ' + event)

    def test_special_case_sends_only_current_job_with_restorable_redacted_evidence(self):
        self.store.journal.write('run_started', job_id='f' * 32, inputs=['OLD-PRIVATE-INPUT'])
        job = self.run_job()
        self.assertEqual(job['status'], 'completed')
        self.assertTrue(self.delivered.wait(3), 'Special-case task did not send support mail')
        self.assertEqual(len(self.messages), 1)
        message = self.messages[0]
        self.assertIn(job['id'][:8], str(message['Subject']))
        attachment, = message.iter_attachments()
        with zipfile.ZipFile(io.BytesIO(attachment.get_payload(decode=True))) as archive:
            self.assertEqual(archive.namelist(), ['MissionB.log'])
            log = archive.read('MissionB.log').decode('utf-8')
        for secret in (KEY, MAIL_PASSWORD, self.server.token, 'OLD-PRIVATE-INPUT'):
            self.assertNotIn(secret, log)
        path = self.root / 'received.log'
        path.write_text(log, encoding='utf-8')
        self.assertEqual(restore(path, self.root / 'restored'), job['id'])
        self.assertTrue((self.root / 'restored/evidence/results.json').is_file())
        self.assertEqual(self.client.get(f"/api/jobs/{job['id']}/download").status_code, 200)

    def test_rejected_mail_is_retained_and_retried_on_restart_without_blocking_download(self):
        self.smtp_error = smtplib.SMTPDataError(451, b'temporary rejection')
        job = self.run_job()
        self.assertEqual(job['status'], 'completed')
        self.assertEqual(self.client.get(f"/api/jobs/{job['id']}/download").status_code, 200)
        self.wait_record('mail_retry')
        self.stop_server()
        self.smtp_error = None
        self.start_server()
        self.assertTrue(self.delivered.wait(3), 'Pending support mail was lost on restart')
        self.wait_record('mail_sent')
        self.assertEqual(len(self.messages), 1)
        self.stop_server()
        self.start_server()
        self.store.close()
        self.assertEqual(len(self.messages), 1, 'Already sent support mail was sent again')

    def test_correct_and_wrong_results_do_not_send(self):
        with patch('test_lite.fixtures', return_value=fixtures()[:2]):
            job = self.run_job()
        self.store.close()
        self.assertEqual(job['counts'], {'正确': 1, '错误': 1, '特殊情况': 0})
        self.assertEqual(self.transports, [])

    def test_special_case_with_empty_reason_still_sends(self):
        with patch('test_lite.fixtures', return_value=fixtures()[-1:]):
            job = self.run_job()
        self.assertTrue(self.delivered.wait(3))
        self.assertEqual(job['counts']['特殊情况'], 1)
        self.assertIn('特殊情况学院：1', self.messages[0].get_body(preferencelist=('plain',)).get_content())

    def test_slow_mail_does_not_block_result_download(self):
        self.gate = threading.Event()
        job = self.run_job()
        self.wait_record('mail_sending')
        self.assertFalse(self.messages)
        self.assertEqual(job['status'], 'completed')
        self.assertEqual(self.client.get(f"/api/jobs/{job['id']}/download").status_code, 200)
        self.gate.set()
        self.assertTrue(self.delivered.wait(3))

    def test_unknown_delivery_is_not_resent_automatically(self):
        self.smtp_error = smtplib.SMTPServerDisconnected('connection lost during DATA')
        job = self.run_job()
        self.wait_record('mail_uncertain')
        self.stop_server()
        self.smtp_error = None
        self.start_server()
        self.store.close()
        self.assertEqual(len(self.transports), 1)
        self.assertEqual(self.client.get(f"/api/jobs/{job['id']}/download").status_code, 200)

    def test_three_failed_attempts_stop_and_remain_local(self):
        self.login_error = smtplib.SMTPAuthenticationError(535, MAIL_PASSWORD.encode())
        job = self.run_job()
        self.wait_record('mail_retry')
        for attempt in (2, 3):
            self.stop_server()
            self.start_server()
            deadline = time.monotonic() + 3
            while len(self.transports) < attempt and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertEqual(len(self.transports), attempt)
        self.wait_record('mail_failed')
        self.stop_server()
        self.start_server()
        self.store.close()
        self.assertEqual(len(self.transports), 3)
        self.assertNotIn(MAIL_PASSWORD, self.store.journal.path.read_text(encoding='utf-8'))
        self.assertNotIn(MAIL_PASSWORD, (self.store.root / 'mail-outbox' / job['id'] / 'state.json').read_text(encoding='utf-8'))
        self.assertTrue((self.store.root / 'mail-outbox' / job['id'] / 'support.zip').is_file())

    def test_smtp_close_failure_after_acceptance_does_not_resend(self):
        self.close_error = OSError('fixture close failure')
        self.run_job()
        self.wait_record('mail_sent')
        self.stop_server()
        self.start_server()
        self.store.close()
        self.assertEqual(len(self.messages), 1)

    def test_no_backfill_for_historical_jobs_and_no_mail_configuration_in_ui(self):
        seed(self.store)
        self.stop_server()
        self.start_server()
        self.store.close()
        self.assertEqual(self.transports, [])
        state = self.client.get('/api/state').text
        for value in (MAIL_PASSWORD, MAIL['sender'], MAIL['recipient']):
            self.assertNotIn(value, state)
        self.assertEqual(self.client.get('/mail_config.json').status_code, 404)

    def test_password_is_removed_inside_compressed_evidence(self):
        async def evidence_with_secrets(args, *a, **kw):
            value = await simulated_run(args, *a, **kw)
            (args.output / 'evidence/fixture/http.html').write_text(
                '<html>' + MAIL_PASSWORD + KEY + self.server.token + '</html>', encoding='utf-8')
            return value
        self.run_job(evidence_with_secrets)
        self.assertTrue(self.delivered.wait(3))
        attachment, = self.messages[0].iter_attachments()
        with zipfile.ZipFile(io.BytesIO(attachment.get_payload(decode=True))) as archive:
            records = [json.loads(line) for line in archive.read('MissionB.log').decode().splitlines()]
        record = next(r for r in records if r.get('path') == 'evidence/fixture/http.html')
        text = zlib.decompress(base64.b64decode(record['content'])).decode()
        self.assertEqual(text, '<html>[REDACTED][REDACTED][REDACTED]</html>')

    def test_failed_and_cancelled_tasks_do_not_send(self):
        for error in (RuntimeError('fixture failure'), InterruptedError('fixture cancelled')):
            async def fail(*a, **kw):
                raise error
            job = self.run_job(fail)
            self.assertIn(job['status'], ('failed', 'cancelled'))
        self.store.close()
        self.assertEqual(self.transports, [])


if __name__ == '__main__':
    unittest.main()
