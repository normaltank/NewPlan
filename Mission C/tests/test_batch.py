import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from openpyxl import Workbook
ROOT = Path(__file__).resolve().parents[1]

class BatchContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.data = self.folder / '中文 data'
        self.input = self.folder / '原表.xlsx'
        book = Workbook()
        sheet = book.active
        sheet.title = 'Sheet1'
        sheet.append(['ID', '学校', '学院', '师资URL'])
        sheet.append([1, '虚构大学', '光学院', 'https://example.edu/list'])
        sheet.append([1, '虚构大学', '光学院', 'https://example.edu/list2'])
        sheet.append([2, '虚构大学', '理学院', 'https://example.edu/science'])
        sheet = book.create_sheet('Sheet2')
        sheet.append(['学院ID', '个人URL'])
        sheet.append([1, 'https://example.edu/teacher#bio'])
        sheet.append([2, 'https://example.edu/teacher'])
        sheet.append([99, 'https://example.edu/orphan'])
        sheet.append([1, 'bad'])
        book.save(self.input)
    def cli(self, *args, ok=True):
        p = subprocess.run([sys.executable, str(ROOT/'batch.py'), '--data-root', str(self.data), *map(str,args)], capture_output=True, encoding='utf-8', errors='replace')
        if ok: self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout) if ok else p
    def test_preview_import_visible_batch_and_idempotent_content(self):
        preview = self.cli('preview', self.input)
        self.assertFalse(self.data.exists())
        self.assertEqual(len(preview['tasks']), 1)
        self.assertEqual(len(preview['tasks'][0]['relations']), 2)
        self.assertEqual(len(preview['issues']), 2)
        imported = self.cli('import', self.input)
        batch = self.cli('status', imported['id'])
        self.assertEqual(batch['counts']['pending'], 1)
        self.assertEqual(len(batch['tasks'][0]['sources']), 2)
        self.assertEqual(batch['tasks'][0]['relations'][0]['faculty_urls'], ['https://example.edu/list', 'https://example.edu/list2'])
        self.assertEqual(self.cli('import', self.input)['id'], imported['id'])
        self.assertEqual(len(self.cli('list')), 1)
