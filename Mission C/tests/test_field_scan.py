"""Synthetic biographies exercise the public field and HTML extraction boundaries."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mission_c.quality_fields import fields_from_text


class BiographyFieldScan(unittest.TestCase):
    def test_long_unbroken_biography_finishes_without_losing_text_or_fields(self):
        long = '完整研究经历与成果。' * 10000
        biography = '李明\n姓名：李明\n职称：教授\n' + long + '\n本人邮箱：liming@example.edu'
        html = ('<main><h1>李明</h1><p>姓名：李明</p><p>职称：教授</p><p>' + long
                + '</p><p>本人邮箱：liming@example.edu</p></main>')
        script = ('import json, sys; from mission_c.extract import extract_html; '
                  'print(json.dumps(extract_html(sys.stdin.read(), "https://example.edu/li")))')
        # A separate worker bounds even a regex holding the GIL. Five seconds
        # includes imports and leaves ample margin over this small offline page.
        # It performs no collection and starts no further application processes.
        with subprocess.Popen([sys.executable, '-X', 'utf8', '-c', script],
                              cwd=Path(__file__).resolve().parents[1],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, encoding='utf-8') as process:
            try:
                stdout, stderr = process.communicate(html, timeout=5)
            except subprocess.TimeoutExpired:
                if os.name == 'nt':
                    # Windows venv launchers can have a base-Python child. Kill
                    # only this worker's tree before waiting and closing pipes.
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   timeout=5, check=False)
                else:
                    process.kill()
                process.communicate(timeout=5)
                self.fail('100000-character biography extraction exceeded the 5-second deadline')
            self.assertEqual(process.returncode, 0, stderr)
        result = json.loads(stdout)
        self.assertEqual(result['biography'], biography)
        self.assertEqual(result['page_text'], biography)
        self.assertIn(long, result['content_html'])
        self.assertEqual((result['name'], result['title'], result['email']),
                         ('李明', '教授', 'liming@example.edu'))
        self.assertEqual(result['field_evidence']['anomalies'], [])

    def test_email_tokens_keep_candidates_context_and_incomplete_value_warnings(self):
        cases = [
            ('邮箱：foo@@bar.cn', '', ['邮箱格式不完整']),
            ('邮箱：foo@bar@baz.cn', 'bar@baz.cn', []),
            ('联系：good@example.edu，坏@163.', 'good@example.edu', []),
            ('good@example.edu\n邮箱：bad@163.', 'good@example.edu', ['邮箱格式不完整']),
            ('邮箱@', '', ['邮箱格式不完整']),
            ('@.cn', '', ['邮箱格式不完整']),
            ('研究 Au@SiO2 和 Workshop(SRW@ACL2023).', '', []),
            ('联系 \t＠＠\u00a0邮箱：bad@163.\n尾段', '', ['邮箱格式不完整']),
            ('Email:\nld\n3679@163.\ncom', 'ld3679@163.com', []),
        ]
        for text, email, anomalies in cases:
            with self.subTest(text=text):
                result = fields_from_text('李明', text)
                self.assertEqual(result['email']['value'], email)
                self.assertEqual(result['anomalies'], anomalies)
        result = fields_from_text('李明', '邮箱：foo@bar@baz.cn')
        self.assertEqual(result['email_candidates'], [
            {'value': 'bar@baz.cn', 'score': 90, 'evidence': '邮箱:foo@bar@baz.cn',
             'rule': 'personal_body'}])


if __name__ == '__main__':
    unittest.main()
