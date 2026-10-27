"""Public CLI checks; all paid transport is replaced at the external HTTP boundary."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("ds_fetch_once.py")
SUDA_URL = "https://web.suda.edu.cn/hj1/"
LZJTU_URL = "https://jtys.lzjtu.edu.cn/info/1113/4365.htm"

FAKE_HTTP = '''import asyncio, json, os, pathlib, runpy, sys
import httpx
class Client:
    def __init__(self, **kwargs): pass
    async def __aenter__(self):
        if os.environ.get('FETCH_TEST_CONCURRENT'):
            gate = pathlib.Path(os.environ['FETCH_TEST_CALLS'] + '.' + str(os.getpid()))
            gate.touch()
            for _ in range(100):
                if len(list(gate.parent.glob('calls.txt.*'))) >= 2: break
                await asyncio.sleep(.02)
        return self
    async def __aexit__(self, *args): pass
    async def post(self, url, json):
        with open(os.environ['FETCH_TEST_CALLS'], 'a') as stream:
            stream.write('POST\\n')
        if os.environ.get('FETCH_TEST_FAILURE'):
            raise httpx.ReadTimeout('test timeout ' + os.environ['DEEPSEEK_API_KEY'])
        return httpx.Response(int(os.environ.get('FETCH_TEST_STATUS', '200')), content=(' {"title":"何剑", "content":"何剑\\\\n教授\\\\n邮箱 hj@suda.edu.cn ' + os.environ['DEEPSEEK_API_KEY'] + '"} ').encode())
httpx.AsyncClient = Client
sys.argv = sys.argv[1:]
runpy.run_path(sys.argv[0], run_name='__main__')
'''


class FetchCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name)

    def run_cli(self, *args, fake_http=False, failure=False):
        env = dict(os.environ)
        env.pop("DEEPSEEK_API_KEY", None)
        prefix = [sys.executable]
        if fake_http:
            adapter = self.out / "fake_http.py"
            adapter.write_text(FAKE_HTTP, encoding="utf-8")
            env.update(DEEPSEEK_API_KEY="test-secret-do-not-leak", FETCH_TEST_CALLS=str(self.out / "calls.txt"))
            if failure:
                env["FETCH_TEST_FAILURE"] = "1"
            prefix += [str(adapter)]
        return subprocess.run([*prefix, str(SCRIPT), "--output-root", str(self.out), *args],
                              env=env, capture_output=True, text=True, encoding="utf-8", timeout=15)

    def write(self, sample, file, data):
        path = self.out / "deepseek-fetch" / sample / file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_selected_cached_sample_runs_without_a_key(self):
        self.write("suda", "result.json", {"url": SUDA_URL, "calls": 1, "cached_marker": "suda"})
        result = self.run_cli("--sample", "suda")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["url"], SUDA_URL)

    def test_mismatched_cached_url_is_blocked_without_replacing_evidence(self):
        cached = {"url": LZJTU_URL, "calls": 1}
        self.write("suda", "result.json", cached)
        result = self.run_cli("--sample", "suda")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("URL mismatch", result.stderr)
        self.assertEqual(json.loads((self.out / "deepseek-fetch/suda/result.json").read_text()), cached)

    def test_paid_result_is_reused_and_keeps_response_evidence(self):
        first = self.run_cli("--sample", "suda", fake_http=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.run_cli("--sample", "suda")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual((self.out / "calls.txt").read_text().splitlines(), ["POST"])
        row = json.loads(second.stdout)
        self.assertIsNone(row["origin_http_status"])
        self.assertEqual(row["calls"], 1)
        self.assertTrue(row["observed_at"])
        self.assertTrue(row["provider_response_sha256"])
        content = (self.out / "deepseek-fetch/suda/provider-content.md").read_text(encoding="utf-8")
        self.assertIn("hj@suda.edu.cn", content)
        for path in (self.out / "deepseek-fetch/suda").iterdir():
            self.assertNotIn("test-secret-do-not-leak", path.read_text(encoding="utf-8"))

    def test_transport_failure_is_saved_and_never_retried(self):
        first = self.run_cli("--sample", "suda", fake_http=True, failure=True)
        self.assertNotEqual(first.returncode, 0)
        self.assertNotIn("test-secret-do-not-leak", first.stdout + first.stderr)
        failure = json.loads((self.out / "deepseek-fetch/suda/failure.json").read_text(encoding="utf-8"))
        self.assertEqual(failure["status"], "unknown")
        self.assertEqual(failure["error_type"], "ReadTimeout")
        second = self.run_cli("--sample", "suda", fake_http=True)
        self.assertNotEqual(second.returncode, 0)
        self.assertIn("unresolved", second.stderr)
        self.assertEqual((self.out / "calls.txt").read_text().splitlines(), ["POST"])

    def test_simultaneous_invocations_cannot_pay_twice(self):
        adapter = self.out / "fake_http.py"
        adapter.write_text(FAKE_HTTP, encoding="utf-8")
        env = dict(os.environ, DEEPSEEK_API_KEY="test-secret-do-not-leak",
                   FETCH_TEST_CALLS=str(self.out / "calls.txt"), FETCH_TEST_CONCURRENT="1")
        command = [sys.executable, str(adapter), str(SCRIPT), "--output-root", str(self.out), "--sample", "suda"]
        processes = [subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(2)]
        for process in processes:
            process.communicate(timeout=15)
        self.assertEqual((self.out / "calls.txt").read_text().splitlines(), ["POST"])

    def test_provider_http_failure_is_saved_as_failure_not_usable_text(self):
        adapter = self.out / "fake_http.py"
        adapter.write_text(FAKE_HTTP, encoding="utf-8")
        env = dict(os.environ, DEEPSEEK_API_KEY="test-secret-do-not-leak",
                   FETCH_TEST_CALLS=str(self.out / "calls.txt"), FETCH_TEST_STATUS="403")
        result = subprocess.run([sys.executable, str(adapter), str(SCRIPT), "--output-root", str(self.out),
                                 "--sample", "suda"], env=env, capture_output=True, text=True, encoding="utf-8")
        row = json.loads(result.stdout)
        self.assertFalse(row["text_saved"])
        self.assertEqual(row["failure"], "provider_http_error")
        self.assertIsNone(row["origin_http_status"])

    def test_legacy_default_cache_and_unresolved_attempt_remain_offline(self):
        self.write("lzjtu", "result.json", {"url": LZJTU_URL, "calls": 1})
        default = self.run_cli()
        self.assertEqual(default.returncode, 0, default.stderr)
        self.assertEqual(json.loads(default.stdout)["url"], LZJTU_URL)
        self.write("suda", "attempt.json", {"url": SUDA_URL, "status": "unknown"})
        pending = self.run_cli("--sample", "suda")
        self.assertNotEqual(pending.returncode, 0)
        self.assertIn("unresolved", pending.stderr)


if __name__ == "__main__":
    unittest.main()
