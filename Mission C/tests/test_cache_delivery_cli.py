"""Portable cache preparation and combination replay through public commands."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CacheDeliveryCLI(unittest.TestCase):
    def test_imported_bundle_moves_and_replays_combination_without_original_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            original = folder / "original"
            original.mkdir()
            source = original / "source.html"
            source.write_bytes('<meta charset="utf-8"><main><h1>陈晨</h1><p>陈晨，教授。完整原文最后一项。</p></main>'.encode())
            fetch = original / "fetch.json"
            fetch.write_text(json.dumps({"content": "陈晨较短候选。"}), encoding="utf-8")
            metadata = original / "metadata.json"
            metadata.write_text(json.dumps({"observed_at": "2025-01-01T00:00:00Z"}), encoding="utf-8")
            def asset(path):
                return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            os.utime(source, (1700000000, 1700000000))
            inventory = folder / "inventory.json"
            inventory.write_text(json.dumps({"entries": [
                {"id": "chen", "url": "https://example.edu/chen", "source": asset(source),
                 "source_metadata": str(metadata), "source_status": {"http_status": 200, "text_saved": True},
                 "fetch": {"response": asset(fetch), "metadata": str(metadata), "provider_http_status": 200}},
                {"id": "zhou", "url": "https://example.edu/zhou", "source": None,
                 "source_metadata": str(metadata), "source_status": {"http_status": 412, "text_saved": False},
                 "fetch": {"response": asset(fetch), "metadata": str(metadata), "provider_http_status": 200}},
            ]}), encoding="utf-8")
            bundle = folder / "bundle"
            prepared = subprocess.run([sys.executable, str(ROOT / "prepare_cache.py"), "--inventory", str(inventory),
                                       "--output", str(bundle)], capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(prepared.returncode, 0, prepared.stderr)
            manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
            self.assertFalse(Path(manifest["entries"][0]["source"]["path"]).is_absolute())
            self.assertEqual((bundle / manifest["entries"][0]["source"]["path"]).stat().st_mtime, 1700000000)
            self.assertEqual(manifest["entries"][0]["source"]["observed_at"], "2025-01-01T00:00:00Z")
            portable = folder / "moved"
            shutil.copytree(ROOT, portable, ignore=shutil.ignore_patterns("outputs", "__pycache__", ".venv"))
            shutil.move(str(bundle), str(portable / "cache"))
            shutil.rmtree(original)
            replay = subprocess.run([sys.executable, str(portable / "replay.py"), "--cache-manifest",
                                     str(portable / "cache/manifest.json"), "--output", str(folder / "result")],
                                    cwd=folder, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(replay.returncode, 1, replay.stderr)
            rows = json.loads((folder / "result/teachers.json").read_text(encoding="utf-8"))
            self.assertIn("完整原文最后一项", rows[0]["biography"])
            self.assertEqual(rows[0]["fetch"]["status"], "text_saved")
            self.assertEqual(rows[0]["model"]["error"]["code"], "cache_missing")
            self.assertEqual(rows[1]["status"], "provider_candidate")
            self.assertEqual(rows[1]["error"]["code"], "http_412")
