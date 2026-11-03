"""Source distributions must run after extraction without the checkout on sys.path."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

import build_release


class SourcePackageTests(unittest.TestCase):
    def test_full_source_zip_can_load_the_engine_after_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source'
            build_release.copy_source(source)
            archive = root / 'source.zip'
            build_release.make_zip(source, archive)
            with zipfile.ZipFile(archive) as package:
                package.extractall(root / 'extracted')
            env = os.environ.copy()
            env.pop('PYTHONPATH', None)
            result = subprocess.run(
                [sys.executable, '-B', '-c', 'import app; import api_engine'],
                cwd=root / 'extracted' / source.name, env=env,
                capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
