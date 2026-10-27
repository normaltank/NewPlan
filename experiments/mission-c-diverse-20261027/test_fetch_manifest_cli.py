"""Selected manifest samples at the paid runner's external CLI boundary."""
import importlib.util
import json
from pathlib import Path
import unittest

LIVE = Path(__file__).resolve().parents[1] / "mission-c-live-20261027"
spec = importlib.util.spec_from_file_location("legacy_fetch_tests", LIVE / "test_ds_fetch_once_cli.py")
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)


class ManifestCliTests(legacy.FetchCliTests):
    # Inherited tests also exercise the seven existing public behaviors.
    def manifest(self, samples):
        path = self.out / "manifest.json"
        path.write_text(json.dumps({"samples": samples}), encoding="utf-8")
        return str(path)

    def test_manifest_selected_response_is_cached_without_second_post(self):
        manifest = self.manifest([{"id": "n01", "url": "https://example.edu/person"}])
        first = self.run_cli("--manifest", manifest, "--sample", "n01", fake_http=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.run_cli("--manifest", manifest, "--sample", "n01")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(json.loads(second.stdout)["url"], "https://example.edu/person")
        self.assertEqual((self.out / "calls.txt").read_text().splitlines(), ["POST"])

    def test_duplicate_manifest_ids_cannot_start_a_paid_attempt(self):
        manifest = self.manifest([{"id": "n01", "url": "https://example.edu/a"},
                                  {"id": "n01", "url": "https://example.edu/b"}])
        run = self.run_cli("--manifest", manifest, "--sample", "n01", fake_http=True)
        self.assertNotEqual(run.returncode, 0)
        self.assertFalse((self.out / "calls.txt").exists())

    def test_manifest_url_change_cannot_replace_cached_evidence(self):
        self.write("n01", "result.json", {"url": "https://example.edu/old"})
        manifest = self.manifest([{"id": "n01", "url": "https://example.edu/new"}])
        run = self.run_cli("--manifest", manifest, "--sample", "n01", fake_http=True)
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("URL mismatch", run.stderr)
        self.assertFalse((self.out / "calls.txt").exists())

    def test_manifest_unknown_attempt_cannot_start_a_second_post(self):
        self.write("n01", "attempt.json", {"url": "https://example.edu/a", "status": "unknown"})
        manifest = self.manifest([{"id": "n01", "url": "https://example.edu/a"}])
        run = self.run_cli("--manifest", manifest, "--sample", "n01", fake_http=True)
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("unresolved", run.stderr)
        self.assertFalse((self.out / "calls.txt").exists())


if __name__ == "__main__":
    unittest.main()
