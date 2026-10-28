"""Assisted reads observed only through CLI input and delivered artifacts."""
import hashlib
import json
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


if __name__ == "__main__":
    unittest.main()
