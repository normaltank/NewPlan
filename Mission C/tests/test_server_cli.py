import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]


class ServerContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.inputs = self.folder / '中文 inputs'
        self.inputs.mkdir()
        self.data = self.folder / '中文 data'
        self.input = self.inputs / '原表.xlsx'
        self.workbook(self.input)
        source = self.folder / 'page.html'
        source.write_text('<meta charset="utf-8"><main><h1>李明</h1><p>姓名：李明</p><p>职称：教授</p><p>本人邮箱：liming@example.edu</p><p>研究光学。</p></main>', encoding='utf-8')
        self.manifest = self.folder / 'manifest.json'
        self.manifest.write_text(json.dumps({'version': 1, 'entries': [{'url': 'https://example.edu/teacher', 'source': {'path': 'page.html', 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}}]}), encoding='utf-8')

    def workbook(self, path, college='光学院'):
        book = Workbook()
        sheet = book.active
        sheet.title = 'Sheet1'
        sheet.append(['ID', '学校', '学院', '师资URL'])
        sheet.append([1, '虚构大学', college, 'https://example.edu/list'])
        sheet = book.create_sheet('Sheet2')
        sheet.append(['学院ID', '个人URL'])
        sheet.append([1, 'https://example.edu/teacher'])
        book.save(path)
        book.close()

    def cli(self, entry, *args, expected=0):
        result = subprocess.run([sys.executable, str(ROOT / entry), '--data-root', str(self.data), *map(str, args)], capture_output=True, encoding='utf-8', errors='replace', timeout=60)
        self.assertEqual(result.returncode, expected, result.stderr or result.stdout)
        return json.loads(result.stdout)

    def test_scan_new_file_does_not_reprocess_unchanged_or_renamed_content(self):
        scanned = self.cli('server.py', 'scan', self.inputs, '--cache-manifest', self.manifest, '--run')
        self.assertEqual(len(scanned['imported']), 1)
        ident = scanned['imported'][0]['id']
        before = self.cli('batch.py', 'status', ident)
        self.assertEqual(before['quality_counts'], {'personal_candidate': 1})
        self.assertNotIn('pending', before['counts'])
        artifact = self.data / before['tasks'][0]['artifact']
        original = {p.relative_to(artifact).as_posix(): p.read_bytes() for p in artifact.rglob('*') if p.is_file()}
        self.assertEqual(self.cli('server.py', 'scan', self.inputs, '--cache-manifest', self.manifest, '--run')['imported'], [])
        shutil.copyfile(self.input, self.inputs / '改名副本.xlsx')
        self.workbook(self.inputs / '新增.xlsx', '理学院')
        third = self.cli('server.py', 'scan', self.inputs, '--cache-manifest', self.manifest, '--run')
        self.assertEqual(len(third['imported']), 1)
        self.assertEqual(len(self.cli('batch.py', 'list')), 2)
        self.assertEqual(original, {p.relative_to(artifact).as_posix(): p.read_bytes() for p in artifact.rglob('*') if p.is_file()})
        self.workbook(self.input, '新学院')
        changed = self.cli('server.py', 'scan', self.inputs)
        self.assertEqual(len(changed['imported']), 1)
        self.assertFalse(changed['imported'][0]['queued'])
        self.assertEqual(len(self.cli('batch.py', 'list')), 3)
        exported = self.cli('batch.py', 'export', ident)
        with zipfile.ZipFile(self.data / exported['exports'][0]['path']) as package:
            self.assertIn('teachers.xlsx', package.namelist())
            self.assertEqual(json.loads(package.read('teachers.json'))[0]['name'], '李明')


    def test_scan_defaults_import_only_and_reports_bad_file_with_exit_status(self):
        (self.inputs / '损坏.xlsx').write_bytes(b'not an Excel workbook')
        scanned = self.cli('server.py', 'scan', self.inputs, expected=1)
        self.assertEqual(len(scanned['imported']), 2)
        self.assertTrue(any(batch['issues'] for batch in scanned['imported']))
        batches = self.cli('batch.py', 'list')
        self.assertTrue(all(not batch['queued'] for batch in batches))
        self.assertFalse((self.data / 'results').exists())
        result = self.cli('server.py', 'worker', '--once')
        self.assertEqual(result['processed'], [])
        self.assertFalse((self.data / 'results').exists())
        invalid = subprocess.run([sys.executable, str(ROOT / 'server.py'), '--data-root', str(self.data), 'scan', str(self.inputs), '--allow-paid'], capture_output=True, timeout=20)
        self.assertEqual(invalid.returncode, 2)

if __name__ == '__main__':
    unittest.main()



