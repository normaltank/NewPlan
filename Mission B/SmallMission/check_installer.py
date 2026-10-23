"""Development check: mocked Unix hosts, real shell; no host package installation."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import zipfile
import httpx

ROOT = Path(__file__).resolve().parent
OUT = ROOT / ('.setup-verification-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
BASH = Path('D:/Git/bin/bash.exe')
RESULTS = []


def unix(path):
    path = Path(path).resolve().as_posix()
    return '/' + path[0].lower() + path[2:]


def script(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('#!/bin/bash\n' + content + '\n', encoding='utf-8', newline='\n')


def shell_case(label, system, arch, target=None, failure=None, reuse=False):
    root = OUT / (label + ' 中文 path')
    root.mkdir()
    shutil.copy2(ROOT / 'run.sh', root / 'run.sh')
    fake = root / 'commands'
    script(fake / 'uname', 'if [ "$1" = -s ]; then echo ' + system + '; else echo ' + arch + '; fi')
    script(fake / 'sw_vers', 'echo 14.0')
    script(fake / 'ldd', 'echo "ldd (GNU libc) 2.36"')
    script(root / 'fake-python', 'printf "%s\\n" "$@" >> "' + unix(root / 'python-calls') + '"')
    if target and failure != 'checksum':
        uv_dir = root / '.runtime' / ('uv-0.13.1-' + target)
        code = 'printf "%s\\n" "$@" >> "' + unix(root / 'uv-calls') + '"\n'
        if failure == 'download':
            code += 'exit 42'
        else:
            code += 'if [ "$1" = venv ]; then mkdir -p .venv/bin; cp fake-python .venv/bin/python; chmod u+x .venv/bin/python; fi'
        script(uv_dir / 'uv', code)
    if failure == 'checksum':
        script(fake / 'curl', 'while [ "$#" -gt 0 ]; do if [ "$1" = --output ]; then shift; printf corrupt > "$1"; exit 0; fi; shift; done; exit 1')
    if reuse:
        (root / '.venv/bin').mkdir(parents=True)
        shutil.copy2(root / 'fake-python', root / '.venv/bin/python')
    env = os.environ.copy()
    env['PATH'] = str(fake) + os.pathsep + 'D:/Git/usr/bin'
    env['PYTHONUTF8'] = '1'
    result = subprocess.run([str(BASH), '-c', 'export PATH="$1:/usr/bin"; /bin/bash "$2" --setup-only',
                             '--', unix(fake), unix(root / 'run.sh')], cwd=root, env=env,
                            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
    (root / 'result.log').write_text(result.stdout + result.stderr, encoding='utf-8')
    if failure or not target:
        assert result.returncode != 0, (label, result.stdout)
        assert not (root / 'python-calls').exists(), label
        if failure == 'checksum':
            assert '校验不通过' in result.stdout and not (root / '.runtime' / ('uv-0.13.1-' + target) / 'uv').exists()
    else:
        assert result.returncode == 0, (label, result.stdout, result.stderr)
        assert '--setup-only' in (root / 'python-calls').read_text(encoding='utf-8')
        if reuse:
            assert not (root / 'uv-calls').exists()
        else:
            assert '--no-bin' in (root / 'uv-calls').read_text()
            assert '--managed-python' in (root / 'uv-calls').read_text()
    RESULTS.append({'case': label, 'ok': True, 'exit_code': result.returncode})


def archive_check(item):
    target, expected = item
    url = f'https://github.com/astral-sh/uv/releases/download/0.13.1/uv-{target}.tar.gz'
    with httpx.Client(follow_redirects=True, timeout=120) as client:
        response = client.get(url)
        response.raise_for_status()
    raw = response.content
    assert hashlib.sha256(raw).hexdigest() == expected, target
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
        binary = archive.getmember(f'uv-{target}/uv')
        assert binary.isfile() and binary.size > 0
    return {'platform': target, 'archive_bytes': len(raw), 'sha256_verified': expected,
            'expected_extraction_member_verified': True}


def main():
    OUT.mkdir()
    for name in ('run.sh', 'start-macos.command', 'install-macos.command', 'install-linux.sh'):
        raw = (ROOT / name).read_bytes()
        assert b'\r' not in raw, name
        subprocess.run([str(BASH), '-n', unix(ROOT / name)], check=True)
    platforms = [
        ('mac-arm', 'Darwin', 'arm64', 'aarch64-apple-darwin', 'cfe454573412ff7380d15fc7dae5997ab53ffce72fce0a78e91ddbc84001acd2'),
        ('mac-intel', 'Darwin', 'x86_64', 'x86_64-apple-darwin', 'bb7b805bdcf3d0bc8c74ceb94569e6b3e8aa35bd492acdbb9d46bf46d9d4ff6b'),
        ('linux-arm', 'Linux', 'aarch64', 'aarch64-unknown-linux-gnu', '9041c73c99fdc5892cf128140beb354eca9231d502068cc36e6cb53a8e59ad14'),
        ('linux-intel', 'Linux', 'x86_64', 'x86_64-unknown-linux-gnu', 'eadd9d27c134ab5ac1ffd4473b97a741407f3ea238288f03121fc4deddf90220'),
    ]
    for label, system, arch, target, _ in platforms:
        shell_case(label, system, arch, target)
    shell_case('repeated-start', 'Linux', 'x86_64', platforms[-1][3], reuse=True)
    shell_case('interrupted-python-download', 'Linux', 'x86_64', platforms[-1][3], failure='download')
    shell_case('wrong-checksum', 'Darwin', 'arm64', platforms[0][3], failure='checksum')
    shell_case('unsupported-arch', 'Linux', 'i686')
    with ThreadPoolExecutor(max_workers=4) as pool:
        archives = list(pool.map(archive_check, [(p[3], p[4]) for p in platforms]))
    report = {'platform': 'Windows x64, Git Bash', 'native_mac_linux_tested': False,
              'shell_scenarios': RESULTS, 'actual_official_archives': archives}
    (OUT / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    print('EVIDENCE=' + str(OUT))


if __name__ == '__main__':
    main()
