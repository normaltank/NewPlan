"""Assisted reads observed only through CLI input and delivered artifacts."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mission_c.cli import main


class AssistedFetchCLI(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.folder = Path(self.scratch.name)

    def blob(self, name, data):
        data = data.encode("utf-8") if isinstance(data, str) else data
        (self.folder / name).write_bytes(data)
        return {"path": name, "sha256": hashlib.sha256(data).hexdigest()}

    def run_cache(self, entries, *options, urls=()):
        manifest = self.folder / "cache.json"
        manifest.write_text(json.dumps({"version": 1, "entries": entries}), encoding="utf-8")
        output = self.folder / "result"
        argv = ["--cache-manifest", str(manifest), "--output", str(output), *options]
        for url in urls:
            argv.extend(["--url", url])
        with patch.object(httpx.Client, "send", side_effect=AssertionError("offline made a request")):
            code = main(argv)
        return code, json.loads((output / "teachers.json").read_text(encoding="utf-8")), output

    def run_live(self, output_name, url="https://example.edu/a", *options):
        source = self.folder / "local.html"
        source.write_text('<meta charset="utf-8"><main><h1>陈晨</h1><p>本地完整原文。</p></main>', encoding="utf-8")
        output = self.folder / output_name
        code = main(["--url", url, "--html", str(source), "--output", str(output),
                     "--fetch-mode", "supplement", "--allow-paid", "--fetch-max-calls", "1",
                     "--fetch-attempts", str(self.folder / "attempts"), *options])
        return code, json.loads((output / "teachers.json").read_text(encoding="utf-8"))[0], output

    def test_multi_url_manifest_reads_relative_sources_without_network_including_attachments(self):
        first = self.blob("a.html", '<meta charset="utf-8"><main><h1>陈晨</h1>'
                          '<p>陈晨，教授。完整原文。</p><a href="/cv.pdf">附件</a></main>')
        second = self.blob("b.html", '<meta charset="utf-8"><main><h1>周宁</h1><p>第二位原文。</p></main>')
        code, rows, output = self.run_cache([
            {"url": "https://example.edu/a", "source": first},
            {"url": "https://example.edu/b", "source": second},
        ])
        self.assertEqual(code, 0)
        self.assertEqual([row["name"] for row in rows], ["陈晨", "周宁"])
        self.assertEqual(rows[0]["media"][0]["reason"], "offline_replay")
        self.assertEqual((output / rows[0]["source_file"]).read_bytes(), (self.folder / "a.html").read_bytes())
        self.assertEqual(rows[0]["source_mode"], "cache_manifest")

    def test_supplement_preserves_local_full_text_and_separate_provider_evidence(self):
        source = self.blob("source.html", '<meta charset="utf-8"><main><h1>陈晨</h1>'
                           '<p>陈晨，教授。第一段。最后一项成果。</p></main>')
        raw = '{"title":"陈晨", "content":"较短提供方内容。"}'
        fetch = {**self.blob("fetch.json", raw), "provider_http_status": 200,
                 "observed_at": "2025-01-01T00:00:00Z"}
        code, rows, output = self.run_cache([
            {"url": "https://example.edu/a", "source": source, "fetch": fetch},
        ], "--fetch-mode", "supplement")
        self.assertEqual(code, 0)
        row = rows[0]
        self.assertIn("最后一项成果。", row["biography"])
        self.assertNotIn("较短", row["biography"])
        self.assertEqual((output / row["fetch"]["response_file"]).read_text(encoding="utf-8"), raw)
        self.assertEqual((output / row["fetch"]["content_file"]).read_text(encoding="utf-8"), "较短提供方内容。")
        self.assertEqual(row["fetch"]["origin_http_status"], None)
        self.assertNotIn("http_status", row)
        self.assertEqual(row["fetch"]["provider_http_status"], 200)
        self.assertEqual(row["fetch"]["observed_at"], "2025-01-01T00:00:00Z")
        self.assertEqual(row["fetch"]["response_sha256"], fetch["sha256"])
        self.assertEqual(row["biography_source"], "local")

    def test_fetch_fallback_retains_local_failure_and_delivers_provider_candidate(self):
        fetch = {**self.blob("fetch.json", '{"title":"陈晨", "content":"陈晨的提供方完整候选原文。"}'),
                 "provider_http_status": 200}
        code, rows, output = self.run_cache([
            {"url": "https://example.edu/a", "source": {"error": {"code": "http_412", "message": "HTTP 412"}},
             "fetch": fetch},
        ], "--fetch-mode", "fallback")
        row = rows[0]
        self.assertEqual(code, 1)
        self.assertEqual(row["status"], "provider_candidate")
        self.assertEqual(row["biography"], "陈晨的提供方完整候选原文。")
        self.assertEqual(row["biography_source"], "deepseek-fetch")
        self.assertEqual(row["error"]["code"], "http_412")
        self.assertEqual(row["field_status"]["name"], "not_read")
        self.assertEqual(row["source_file"], "")
        self.assertTrue(row["review_required"])
        self.assertEqual((output / row["biography_file"]).read_text(encoding="utf-8"), row["biography"])

    def test_provider_failures_and_malformed_responses_are_isolated_with_raw_bytes(self):
        entries = []
        for i, (raw, status) in enumerate([
            ("gateway timeout", 504), ('{"title":"bad"}', 200),
            ('{"content":[], "title":"bad"}', 200),
            ('{"content":"", "title":"empty"}', 200),
            ('{"content":"partial", "truncated":true}', 200),
            ('{"content":"最后一条。", "title":"ok"}', 200),
        ]):
            entries.append({"url": f"https://example.edu/{i}",
                            "source": {"error": {"code": "http_404", "message": "HTTP 404"}},
                            "fetch": {**self.blob(f"f{i}.json", raw), "provider_http_status": status}})
        code, rows, output = self.run_cache(entries, "--fetch-mode", "fallback")
        self.assertEqual(code, 1)
        self.assertEqual([row["fetch"]["status"] for row in rows],
                         ["read_failed"] * 5 + ["text_saved"])
        self.assertEqual(rows[0]["fetch"]["error"]["code"], "provider_http_504")
        self.assertEqual((output / rows[0]["fetch"]["response_file"]).read_bytes(), b"gateway timeout")
        self.assertEqual(rows[-1]["biography"], "最后一条。")
        self.assertTrue(all(not row["biography"] for row in rows[:-1]))

    def test_url_hash_missing_cache_and_model_binding_failures_are_explicit_per_url(self):
        good = self.blob("good.html", '<meta charset="utf-8"><main><h1>陈晨</h1><p>完整。</p></main>')
        model = self.blob("model.json", '{"choices":[]}')
        code, rows, _ = self.run_cache([
            {"url": "https://example.edu/ok", "source": good},
            {"url": "https://example.edu/wrong-url", "source": {**good, "url": "https://example.edu/other"}},
            {"url": "https://example.edu/wrong-hash", "source": {**good, "sha256": "0" * 64}},
            {"url": "https://example.edu/missing-file", "source": {**good, "path": "absent.html"}},
            {"url": "https://example.edu/wrong-model", "source": good,
             "model": {**model, "source_sha256": "0" * 64}},
        ], urls=["https://example.edu/ok", "https://example.edu/wrong-url", "https://example.edu/wrong-hash",
                 "https://example.edu/missing-file", "https://example.edu/wrong-model", "https://example.edu/absent"])
        self.assertEqual(code, 1)
        self.assertEqual(rows[0]["name"], "陈晨")
        self.assertEqual([row["error"]["code"] for row in rows[1:4]],
                         ["cache_url_mismatch", "cache_hash_mismatch", "cache_missing"])
        self.assertEqual(rows[4]["model_cache"]["error"]["code"], "cache_source_hash_mismatch")
        self.assertIn("完整。", rows[4]["biography"])
        self.assertEqual(rows[5]["error"]["code"], "cache_missing")

    def test_online_fetch_requires_paid_permission_key_and_budget_before_external_post(self):
        self.blob("source.html", '<main><h1>陈晨</h1><p>已有完整原文。</p></main>')
        for i, options in enumerate([
            [], ["--allow-paid"], ["--allow-paid", "--fetch-max-calls", "1"],
        ]):
            with self.subTest(options=options):
                output = self.folder / f"result{i}"
                with patch.dict(os.environ, {}, clear=True), patch.object(
                        httpx.Client, "send", side_effect=AssertionError("unguarded external IO")):
                    code = main(["--url", "https://example.edu/a", "--html", str(self.folder / "source.html"),
                                 "--output", str(output), "--fetch-mode", "supplement",
                                 "--fetch-attempts", str(self.folder / "attempts"), *options])
                row = json.loads((output / "teachers.json").read_text(encoding="utf-8"))[0]
                self.assertEqual(code, 0)
                self.assertEqual(row["fetch"]["status"], "read_failed")
                self.assertEqual(row["fetch"]["error"]["code"],
                                 ["paid_not_allowed", "fetch_budget_exhausted", "fetch_key_missing"][i])
                self.assertIn("已有完整原文。", row["biography"])

    def test_online_post_persists_attempt_before_send_redacts_response_and_enforces_durable_budget(self):
        requests = []
        def respond(client, request, **kwargs):
            requests.append(request)
            self.assertEqual(request.method, "POST")
            self.assertEqual(str(request.url), "https://api.deepseek.com/v1/tools/fetch")
            self.assertEqual(json.loads(request.content), {"url": "https://example.edu/a"})
            self.assertEqual(request.headers["Authorization"], "Bearer synthetic-key-never-real")
            attempts = list((self.folder / "attempts").glob("fetch-*.json"))
            self.assertEqual(len(attempts), 1)
            self.assertEqual(json.loads(attempts[0].read_text())["state"], "unknown")
            return httpx.Response(200, request=request,
                                  json={"title": "陈晨", "content": "补充完整段落。", "echo": "synthetic-key-never-real"})
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "synthetic-key-never-real"}, clear=True), \
                patch.object(httpx.Client, "send", autospec=True, side_effect=respond):
            _, row, output = self.run_live("first")
            _, blocked, _ = self.run_live("second", "https://example.edu/b")
        self.assertEqual(len(requests), 1)
        self.assertEqual(row["fetch"]["status"], "text_saved")
        self.assertEqual(row["fetch"]["source"], "live")
        self.assertEqual(blocked["fetch"]["error"]["code"], "fetch_budget_exhausted")
        self.assertTrue(row["fetch"]["response_redacted"])
        self.assertNotIn("synthetic-key-never-real", (output / row["fetch"]["response_file"]).read_text())
        attempt = json.loads(next((self.folder / "attempts").glob("fetch-*.json")).read_text())
        self.assertEqual(attempt["state"], "completed")
        self.assertEqual(attempt["provider_http_status"], 200)

    def test_unknown_online_outcome_is_persisted_and_same_url_is_never_resent(self):
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "synthetic-key-never-real"}, clear=True), \
                patch.object(httpx.Client, "send", side_effect=httpx.ReadTimeout("synthetic-key-never-real")) as send:
            _, first, _ = self.run_live("first")
            _, second, _ = self.run_live("second")
        self.assertEqual(send.call_count, 1)
        self.assertEqual(first["fetch"]["error"]["code"], "fetch_network_unknown")
        self.assertEqual(second["fetch"]["error"]["code"], "fetch_attempt_unknown")
        attempt = next((self.folder / "attempts").glob("fetch-*.json"))
        self.assertEqual(json.loads(attempt.read_text())["state"], "unknown")
        self.assertNotIn("synthetic-key-never-real", attempt.read_text())


if __name__ == "__main__":
    unittest.main()
