"""Build a separate allowlisted lite package without touching full releases/data."""
from datetime import datetime
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

from build_release import license_files, make_zip
from lite_app import LITE_VERSION
from lite_mail import load_config

ROOT = Path(__file__).resolve().parent
FILES = ['app.py', 'lite_app.py', 'lite_mail.py', 'audit.py', 'reporting.py', 'input_adapter.py', 'runtime_paths.py',
         'api_engine.py', 'ai_regions.py', 'deepseek_api.py', 'requirements.txt', 'source_plans.json']
BROWSER_ARCHIVE = ROOT / 'release' / 'MissionB-Windows-x64-v3.0.1.zip'
BROWSER_ARCHIVE_SHA256 = 'ab03c09f86cc9b1b6f5fe78d5b00a193e42529d96f81f9c86df488cd3c7f366a'


def browser_from_release(destination):
    if hashlib.sha256(BROWSER_ARCHIVE.read_bytes()).hexdigest() != BROWSER_ARCHIVE_SHA256:
        raise ValueError('浏览器来源包校验失败')
    destination.mkdir()
    with zipfile.ZipFile(BROWSER_ARCHIVE) as archive:
        prefix = 'MissionB-Windows-x64-v3.0.1/.browsers/'
        count = 0
        for info in archive.infolist():
            if not info.filename.startswith(prefix) or info.is_dir():
                continue
            relative = Path(info.filename[len(prefix):])
            if '.links' in relative.parts:
                continue
            target = (destination / relative).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise ValueError('浏览器包路径无效')
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open('wb') as output:
                shutil.copyfileobj(source, output)
            count += 1
    if not count:
        raise ValueError('正式包中没有浏览器')


def read_dpapi(path):
    key_path = str(path.resolve()).replace("'", "''")
    script = ("$ErrorActionPreference = 'Stop'; $value = (Get-Content -LiteralPath '" + key_path + "' -Raw).Trim() | ConvertTo-SecureString; "
              "$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($value); "
              "try { [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) } "
              "finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }")
    return subprocess.check_output([shutil.which('pwsh') or 'powershell', '-NoProfile', '-NonInteractive', '-Command', script],
                                   text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--key-dpapi', type=Path, required=True, help='Windows user-encrypted distribution credential')
    parser.add_argument('--mail-key-dpapi', type=Path, help='Windows user-encrypted SMTP credential')
    parser.add_argument('--mail-sender')
    parser.add_argument('--mail-recipient')
    parser.add_argument('--mail-host', default='smtp.163.com')
    parser.add_argument('--mail-port', type=int, default=465)
    args = parser.parse_args()
    if any((args.mail_key_dpapi, args.mail_sender, args.mail_recipient)) and not all((args.mail_key_dpapi, args.mail_sender, args.mail_recipient)):
        parser.error('邮件配置需要同时提供发件人、收件人和加密授权码文件')
    api_key = read_dpapi(args.key_dpapi)
    if not api_key.startswith('sk-') or len(api_key) < 12 or any(c.isspace() for c in api_key):
        raise ValueError('分发密钥读取失败')
    stage = ROOT / ('.lite-stage-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    stage.mkdir()
    private_config = stage / 'lite_config.json'
    private_config.write_text(json.dumps({'api_key': api_key}), encoding='utf-8')
    mail_config = None
    if args.mail_key_dpapi:
        mail_config = stage / 'mail_config.json'
        mail_config.write_text(json.dumps(dict(host=args.mail_host, port=args.mail_port,
            sender=args.mail_sender, recipient=args.mail_recipient, password=read_dpapi(args.mail_key_dpapi))), encoding='utf-8')
        load_config(mail_config)
    windows = stage / f'MissionB-Lite-Windows-x64-v{LITE_VERSION}'
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--windowed', '--noupx',
               '--name', 'MissionB-Lite', '--distpath', str(stage), '--workpath', str(stage / 'work'),
               '--specpath', str(stage / 'spec')]
    for name in ['lite_web', 'templates', *[n for n in FILES if n != 'lite_app.py']]:
        command += ['--add-data', str(ROOT / name) + ';' + (name if (ROOT / name).is_dir() else '.')]
    for name in ('httpx', 'beautifulsoup4', 'lxml', 'openpyxl', 'playwright', 'xlrd'):
        command += ['--copy-metadata', name]
    command += ['--add-data', str(private_config) + ';.']
    if mail_config:
        command += ['--add-data', str(mail_config) + ';.']
    command.append(str(ROOT / 'lite_app.py'))
    env = os.environ.copy()
    env['PYINSTALLER_CONFIG_DIR'] = str(stage / 'cache')
    subprocess.check_call(command, cwd=ROOT, env=env)
    (stage / 'MissionB-Lite').rename(windows)
    (windows / 'MissionB-Lite.exe').rename(windows / '名单核验.exe')
    browser_from_release(windows / '.browsers')
    shutil.copy2(ROOT / 'source_plans.json', windows / 'source_plans.json')
    shutil.copytree(ROOT / 'templates', windows / 'templates')
    (windows / '使用说明.txt').write_text(
        f'Mission B 精简版 {LITE_VERSION}\n\n完整解压后双击“名单核验.exe”。\n'
        '选择文件 → 开始核验 → 下载结果。无需填写任何密钥。\n'
        '进度条按实际完成项数更新；整理文件后显示100%，即可下载。\n'
        '特殊情况请人工查看原网页。运行问题请发送本文件夹内的 MissionB.log 给维护人员。\n'
        + ('出现特殊情况时，本批诊断日志会自动发送给维护人员；发送失败不影响结果下载。\n' if mail_config else '') +
        '关闭网页不退出程序，请用页面下方“退出”。\n'
        '保留 _internal 和 .browsers；请使用干净发行包分发，不转发运行后的文件夹。\n', encoding='utf-8-sig')
    license_files(windows / 'third_party')
    source = stage / f'MissionB-Lite-Source-v{LITE_VERSION}'
    source.mkdir()
    for name in FILES + ['read_lite_log.py']:
        shutil.copy2(ROOT / name, source / name)
    for name in ('lite_web', 'templates'):
        shutil.copytree(ROOT / name, source / name)
    shutil.copy2(ROOT / 'README_lite.md', source / 'README.md')
    (source / '启动精简版.cmd').write_text('@echo off\r\ncd /d "%~dp0"\r\npython lite_app.py\r\npause\r\n', encoding='ascii')
    metadata = []
    for folder in (windows, source):
        target = ROOT / 'release' / (folder.name + '.zip')
        if target.exists():
            raise FileExistsError('保留已有正式包：' + str(target))
        make_zip(folder, target)
        metadata.append({'file': target.name, 'bytes': target.stat().st_size,
                         'sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
    (ROOT / 'release' / f'MissionB-Lite-v{LITE_VERSION}-manifest.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    print(json.dumps({'stage': str(stage), 'packages': metadata}, indent=2), flush=True)


if __name__ == '__main__':
    main()
