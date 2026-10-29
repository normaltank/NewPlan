"""Offline public CLI checks; no real teacher/network data is used here."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
COLLECTOR = HERE.parents[1] / "Mission C" / "collect.py"


class CohortCLI(unittest.TestCase):
    def test_saved_page_retains_person_and_tail_and_reentry_reuses_result(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            source = root / "source.html"
            source.write_text('<meta charset="utf-8"><main><h1>陈晨</h1><p>职称：讲师</p>'
                              '<p>邮箱：chen@example.edu</p><h2>个人简介</h2><p>教育经历：示例大学。</p>'
                              '<h2>研究方向</h2><p>量子光学。</p><h2>发表论文</h2><p>最后一篇论文原文。</p></main>', encoding="utf-8")
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"samples": [{"id": "example", "url": "https://example.edu/chen",
                "school": "示例大学", "college": "物理学院", "saved_html": str(source)}]}), encoding="utf-8")
            command = [sys.executable, str(HERE / "cohort_run.py"), "--manifest", str(manifest),
                       "--output", str(root / "out"), "--collector", str(COLLECTOR), "--offline"]
            first = subprocess.run(command, capture_output=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            teachers = root / "out/example/cli/teachers.json"
            record = json.loads(teachers.read_text(encoding="utf-8"))[0]
            self.assertEqual((record["name"], record["title"], record["email"]), ("陈晨", "讲师", "chen@example.edu"))
            self.assertIn("最后一篇论文原文。", record["biography"])
            before = teachers.read_bytes(), teachers.stat().st_mtime_ns
            source.unlink()
            resumed = subprocess.run(command, capture_output=True)
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            self.assertEqual((teachers.read_bytes(), teachers.stat().st_mtime_ns), before)


if __name__ == "__main__":
    unittest.main()
