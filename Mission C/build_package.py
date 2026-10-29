"""Build an allowlisted portable source package; private sharing is opt-in."""
import argparse
import json
from pathlib import Path
import zipfile

from mission_c.private_deployment import PrivateDeployment

ROOT = Path(__file__).resolve().parent
FILES = ('collect.py','batch.py','server.py','web.py','replay.py','prepare_cache.py',
         'run.bat','replay.bat','server.bat','server.sh','web.bat','web.sh','setup.bat','setup.sh',
         'requirements.txt','requirements-web.txt','requirements-browser.txt','requirements-ocr.txt',
         'README.md','使用说明.md','WEB.md','BATCH.md','SERVER.md','build_package.py',
         'examples/assisted-cache/manifest.json','examples/assisted-cache/local.html',
         'examples/assisted-cache/fallback.json','examples/assisted-cache/model.json',
         'examples/assisted-cache/supplement.json',
         'schedule-examples/cron.example','schedule-examples/mission-c-scan.service',
         'schedule-examples/mission-c-scan.timer','schedule-examples/mission-c-watch.service',
         'schedule-examples/windows-scan.ps1')

MODULES = ('__init__.py','assisted.py','batch.py','batch_delivery.py','batch_quality.py',
           'cli.py','export.py','extract.py','fetch.py','media.py','model_assist.py',
           'ocr_media.py','person_names.py','private_deployment.py','profile_layouts.py',
           'quality_fields.py','render.py','web.py')
ASSETS = ('web_static/app.js','web_static/index.html','web_static/style.css',
          'delivery_static/app.css','delivery_static/app.js','delivery_static/index.html')
PACKAGE_FILES = tuple('mission_c/'+name for name in MODULES+ASSETS)


def write_member(archive, name, payload, mode=0o644):
    info = zipfile.ZipInfo('Mission C/'+name)
    info.create_system = 3
    info.external_attr = (0o100000 | mode) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, payload)


def main(argv=None):
    parser=argparse.ArgumentParser(description='生成普通无凭据包或显式 PRIVATE 私人分发包')
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--private-config',type=Path)
    args=parser.parse_args(argv)
    private=PrivateDeployment(args.private_config) if args.private_config else None
    key=private.load_key() if private else None
    if args.output.exists(): parser.error('输出文件已存在，请使用新路径')
    if private and 'PRIVATE' not in args.output.name: parser.error('私人包文件名必须含 PRIVATE')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(args.output,'x',compression=zipfile.ZIP_DEFLATED) as archive:
        for name in FILES+PACKAGE_FILES:
            write_member(archive, name, (ROOT/name).read_bytes(), 0o755 if name.endswith('.sh') else 0o644)
        if private:
            write_member(archive, '.private/deployment.json', json.dumps({'profile':'deepseek-private-v1','key_file':'credential.txt'}), 0o600)
            write_member(archive, '.private/credential.txt', key, 0o600)
            write_member(archive, 'PRIVATE.txt', '仅供获授权接收者。此私人包包含共享付费凭据，拿到包的人可以提取并使用该凭据；请勿公开上传或转发。每页最多一次 Fetch 和一次模型调用，按去重条目数设批次 2*N 预算。请保护本机文件权限。')
    print('已生成 PRIVATE 私人包（仅供授权接收者）' if private else '已生成普通无凭据包')


if __name__=='__main__': main()
