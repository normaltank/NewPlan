"""Installer failure/success contracts; no network or host package changes."""
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import bootstrap


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=bootstrap.ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'requirements.txt').write_text('example==1.0\n')
        python = self.root / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        python.parent.mkdir(parents=True)
        python.touch()
        self.ready = self.root / '.venv/.missionb-ready'
        self.signature = hashlib.sha256(b'setup1\0' + (self.root / 'requirements.txt').read_bytes()).hexdigest()

    def test_first_install_requires_browser_success_before_ready(self):
        with patch.object(bootstrap, 'command', return_value=(0, '')) as run:
            bootstrap.prepare(self.root)
        self.assertEqual(self.ready.read_text(), self.signature)
        commands = [c.args[0] for c in run.call_args_list]
        self.assertTrue(any('pip' in c and 'install' in c for c in commands))
        self.assertEqual(commands[-1][-1], bootstrap.BROWSER_CHECK)

    def test_download_failure_never_marks_ready(self):
        with patch.object(bootstrap, 'command', side_effect=[(1, 'not installed'), (0, 'pip'), (1, 'network failure')]):
            with self.assertRaisesRegex(RuntimeError, '下载或安装'):
                bootstrap.prepare(self.root)
        self.assertFalse(self.ready.exists())

    def test_failed_browser_never_marks_ready(self):
        with patch.object(bootstrap, 'command', side_effect=[(0, '')] * 5 + [(1, 'browser crashed')]):
            with self.assertRaisesRegex(RuntimeError, '浏览器无法启动'):
                bootstrap.prepare(self.root)
        self.assertFalse(self.ready.exists())

    def test_interrupted_seed_install_recovers_missing_pip(self):
        with patch.object(bootstrap, 'command', side_effect=[(1, 'missing modules'), (1, 'missing pip')] + [(0, '')] * 5) as run:
            bootstrap.prepare(self.root)
        self.assertIn('ensurepip', run.call_args_list[2].args[0])
        self.assertEqual(self.ready.read_text(), self.signature)

    def test_repeated_start_does_not_download(self):
        self.ready.write_text(self.signature)
        with patch.object(bootstrap, 'command', return_value=(0, '')) as run:
            bootstrap.prepare(self.root)
        self.assertEqual(len(run.call_args_list), 2)
        self.assertTrue(all(c.args[0][-2] == '-c' for c in run.call_args_list))

    def test_deleted_browser_is_reinstalled(self):
        self.ready.write_text(self.signature)
        with patch.object(bootstrap, 'command', side_effect=[(0, ''), (1, "Executable doesn't exist"), (0, ''), (0, '')]) as run:
            bootstrap.prepare(self.root)
        self.assertIn('install', run.call_args_list[2].args[0])
        self.assertEqual(self.ready.read_text(), self.signature)

    def test_check_only_does_not_install_or_write_ready(self):
        with patch.object(bootstrap, 'command', side_effect=[(0, ''), (1, "Executable doesn't exist")]) as run:
            with self.assertRaises(RuntimeError):
                bootstrap.prepare(self.root, check_only=True)
        self.assertEqual(len(run.call_args_list), 2)
        self.assertFalse(self.ready.exists())

    def test_missing_linux_libs_offer_install_and_verify_again(self):
        self.ready.write_text(self.signature)
        with patch.object(bootstrap.sys, 'platform', 'linux'), patch.object(bootstrap, 'install_system_dependencies') as install, patch.object(bootstrap, 'command', side_effect=[(0, ''), (1, 'Host system is missing dependencies'), (0, '')]):
            bootstrap.prepare(self.root)
        install.assert_called_once()

    def test_noninteractive_never_attempts_system_changes(self):
        with patch.object(bootstrap, 'linux_deps_supported', return_value=True), patch.object(bootstrap.sys.stdin, 'isatty', return_value=False), patch.object(bootstrap.subprocess, 'check_call') as install:
            with self.assertRaisesRegex(RuntimeError, '跳过'):
                bootstrap.install_system_dependencies(Path('python'), self.root, {})
        install.assert_not_called()

    def test_declined_system_changes_are_not_executed(self):
        with patch.object(bootstrap, 'linux_deps_supported', return_value=True), patch.object(bootstrap.sys.stdin, 'isatty', return_value=True), patch('builtins.input', return_value='n'), patch.object(bootstrap.subprocess, 'check_call') as install:
            with self.assertRaises(RuntimeError):
                bootstrap.install_system_dependencies(Path('python'), self.root, {})
        install.assert_not_called()

    def test_system_dependency_support_is_explicit(self):
        with patch.object(bootstrap.sys, 'platform', 'linux'):
            for text, expected in [('ID=ubuntu\nVERSION_ID="24.04"', True), ('ID=alpine\nVERSION_ID="3.20"', False), ('ID=debian\nVERSION_ID="11"', False)]:
                with self.subTest(text=text), patch.object(Path, 'read_text', return_value=text):
                    self.assertEqual(bootstrap.linux_deps_supported(), expected)

    def test_environment_stays_local(self):
        with patch.dict(os.environ, {'PIP_TARGET': '/outside', 'PYTHONHOME': '/outside', 'PYTHONPATH': '/outside'}):
            env = bootstrap.environment_variables(self.root)
        self.assertNotIn('PIP_TARGET', env)
        self.assertNotIn('PYTHONHOME', env)
        self.assertNotIn('PYTHONPATH', env)
        self.assertEqual(env['PLAYWRIGHT_BROWSERS_PATH'], str(self.root / '.browsers'))
        self.assertEqual(env['PIP_CONFIG_FILE'], os.devnull)


if __name__ == '__main__':
    unittest.main()
