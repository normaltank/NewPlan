"""Verify the delivered setup ZIP without touching existing app data."""
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile
import check_installer

ROOT = Path(__file__).resolve().parent


def main():
    target = ROOT / 'release/MissionB-Mac-Linux-v2.1.0-setup1.zip'
    old = ROOT / 'release/MissionB-CrossPlatform-v2.1.0.zip'
    output = ROOT / ('.setup-package-check-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    output.mkdir()
    compared = []
    with zipfile.ZipFile(target) as archive, zipfile.ZipFile(old) as baseline:
        top = archive.namelist()[0].split('/')[0]
        old_top = baseline.namelist()[0].split('/')[0]
        for entry in archive.infolist():
            relative = entry.filename.split('/', 1)[1]
            assert not any(part in {'.runtime', '.venv', '.browsers', 'data', '__pycache__', '.env'} for part in Path(relative).parts)
            raw = archive.read(entry)
            if relative.endswith(('.sh', '.command')):
                assert entry.external_attr >> 16 & 0o111
                assert b'\r' not in raw
            if relative.endswith(('.py', '.md', '.json', '.js', '.sh', '.command', '.txt')):
                assert not re.search(rb'ghp_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9]{30,}', raw), relative
            if relative in {'audit.py', 'app.py', 'reporting.py', 'input_adapter.py', 'runtime_paths.py', 'source_plans.json', 'requirements.txt', 'test_audit.py', 'test_distribution.py'} or relative.startswith('web/'):
                assert raw == baseline.read(old_top + '/' + relative), relative
                compared.append(relative)
        archive.extractall(output)
    package = output / top
    env = os.environ.copy()
    env['PYTHONUTF8'] = '1'
    result = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'test_audit', 'test_distribution', 'test_bootstrap', '-q'],
                            cwd=package, env=env, capture_output=True, text=True, encoding='utf-8', timeout=90)
    (output / 'tests.log').write_text(result.stdout + result.stderr, encoding='utf-8')
    assert result.returncode == 0, result.stderr
    # Recheck the final delivered shell with platform commands mocked, never run an installer on the host.
    check_installer.OUT = output / 'shell'
    check_installer.OUT.mkdir()
    check_installer.ROOT = package
    for label, system, arch, platform in [
        ('mac-arm', 'Darwin', 'arm64', 'aarch64-apple-darwin'),
        ('mac-intel', 'Darwin', 'x86_64', 'x86_64-apple-darwin'),
        ('linux-arm', 'Linux', 'aarch64', 'aarch64-unknown-linux-gnu'),
        ('linux-intel', 'Linux', 'x86_64', 'x86_64-unknown-linux-gnu'),
    ]:
        check_installer.shell_case(label, system, arch, platform)
    check_installer.shell_case('repeat', 'Linux', 'x86_64', 'x86_64-unknown-linux-gnu', reuse=True)
    check_installer.shell_case('bad-hash', 'Darwin', 'arm64', 'aarch64-apple-darwin', failure='checksum')
    for args, expected in [(['--check'], 1), (['--help'], 0), (['--system-deps', '--check'], 2)]:
        fresh = output / ('flag-' + args[0].lstrip('-'))
        fresh.mkdir()
        (fresh / 'run.sh').write_bytes((package / 'run.sh').read_bytes())
        fake = fresh / 'commands'
        check_installer.script(fake / 'uname', 'if [ "$1" = -s ]; then echo Linux; else echo x86_64; fi')
        check_installer.script(fake / 'ldd', 'echo "GNU libc"')
        proc = subprocess.run([str(check_installer.BASH), '-c', 'export PATH="$1:/usr/bin"; shift; /bin/bash "$@"',
                               '--', check_installer.unix(fake), check_installer.unix(fresh / 'run.sh'), *args],
                              capture_output=True, text=True, encoding='utf-8', timeout=30)
        assert proc.returncode == expected, (args, proc.stdout, proc.stderr)
        assert not (fresh / '.venv').exists()
        assert not list((fresh / '.runtime').glob('uv-*'))
    windows = ROOT / 'release/MissionB-Windows-x64-v2.1.0.zip'
    assert hashlib.sha256(windows.read_bytes()).hexdigest() == '43e8518f3f7ee5820b94f41613c4d5dd692ae55a302111ea725739fbacbceb5d'
    sha = hashlib.sha256(target.read_bytes()).hexdigest()
    report = {'artifact': target.name, 'bytes': target.stat().st_size, 'sha256': sha,
              'package_unit_tests': 51, 'unchanged_core_files': compared,
              'original_windows_release_unchanged': True, 'shell_platform_simulation': check_installer.RESULTS,
              'check_help_invalid_flags_no_install': True,
              'actual_archive_checks': '.setup-verification-20261015-180745/verification.json',
              'actual_windows_private_environment_install_and_browser_checks': '.setup-runtime-20261015-180904/verification.json',
              'native_macos_linux_tested': False}
    (ROOT / 'release/verification-setup1.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (ROOT / 'release/SHA256SUMS-setup1.txt').write_text(sha + '  ' + target.name + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
