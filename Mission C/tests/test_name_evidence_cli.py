"""Name ownership through the supported saved-page CLI, using fictional fixtures."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class NameEvidenceContract(unittest.TestCase):
    def collect(self, html):
        with tempfile.TemporaryDirectory() as scratch:
            folder = Path(scratch)
            source = folder / "profile.html"
            source.write_text('<meta charset="utf-8">' + html, encoding="utf-8")
            output = folder / "output"
            run = subprocess.run(
                [sys.executable, str(ROOT / "collect.py"), "--url", "https://example.edu/person",
                 "--html", str(source), "--output", str(output)],
                capture_output=True, timeout=20,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            return json.loads((output / "teachers.json").read_text(encoding="utf-8"))[0]

    def test_personal_title_keeps_the_hyphenated_full_name(self):
        record = self.collect("<title>Jean-Luc Martin's Homepage</title>"
                              "<b>Jean-Luc Martin</b><p>Research: optics.</p>")
        self.assertEqual(record["name"], "Jean-Luc Martin")

    def test_school_title_uses_the_visible_person_instead_of_the_homepage_label(self):
        record = self.collect("<title>示例大学 张明--中文主页--首页</title>"
                              "<span>张明</span><p>个人简介：从事光学研究。</p>")
        self.assertEqual(record["name"], "张明")
        self.assertIn("从事光学研究。", record["biography"])

    def test_a_research_group_is_not_a_person(self):
        record = self.collect("<title>Research Group</title><h1>Research Group</h1>"
                              "<p>Research: optics and materials.</p>")
        self.assertEqual(record["name"], "")
        self.assertEqual(record["field_status"]["name"], "not_stated")

    def test_school_title_cannot_borrow_the_person_from_a_sidebar(self):
        record = self.collect("<title>示例大学 张明--中文主页--首页</title>"
                              "<aside><span>张明</span></aside>"
                              "<main><h1>个人简介</h1><p>此页未列出本人姓名。</p></main>")
        self.assertEqual(record["name"], "")
        self.assertEqual(record["field_status"]["name"], "not_stated")

    def test_personal_title_keeps_an_apostrophe_and_ignores_the_site_name(self):
        record = self.collect("<title>Anne-Marie O'Neill's Homepage - Example University</title>"
                              "<b>Anne-Marie O'Neill</b><p>Research: optics.</p>")
        self.assertEqual(record["name"], "Anne-Marie O'Neill")

    def test_page_is_preserved_when_it_is_the_persons_surname(self):
        record = self.collect("<title>John Page's Homepage</title><b>John Page</b>"
                              "<p>Research: optics.</p>")
        self.assertEqual(record["name"], "John Page")

    def test_competing_person_headings_remain_a_conflict(self):
        record = self.collect("<title>Jean-Luc Martin's Homepage</title>"
                              "<h1>陈晨</h1><h1>李明</h1><p>研究方向：光学。</p>")
        self.assertEqual(record["name"], "")
        self.assertEqual(record["field_status"]["name"], "conflict")

    def test_chinese_title_separator_does_not_need_spaces(self):
        record = self.collect("<title>陈晨-示例大学</title>"
                              "<main><p>陈晨，教授，研究光学。</p></main>")
        self.assertEqual(record["name"], "陈晨")


if __name__ == "__main__":
    unittest.main()
