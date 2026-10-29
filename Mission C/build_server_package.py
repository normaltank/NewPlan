"""Build the exact headless handoff allowlist; never copy runtime directories."""
import argparse
import json
from pathlib import Path
import zipfile

from mission_c.private_deployment import PrivateDeployment

ROOT = Path(__file__).resolve().parent
TEMPLATES = ('run.py', 'config.json', 'setup.bat', 'setup.sh', 'start.bat', 'start.sh', 'README.md', 'FILES.md')
MODULES = ('__init__.py', 'assisted.py', 'batch.py', 'batch_delivery.py', 'batch_quality.py',
           'cli.py', 'export.py', 'extract.py', 'fetch.py', 'media.py', 'model_assist.py',
           'ocr_media.py', 'person_names.py', 'private_deployment.py', 'profile_layouts.py',
           'quality_fields.py', 'render.py')


def write_member(archive, name, payload):
    info = zipfile.ZipInfo('Mission C Server/' + name)
    info.create_system = 3
    mode = 0o600 if name.startswith('.private/') else 0o755 if name.endswith('.sh') else 0o644
    info.external_attr = (0o100000 | mode) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, payload)


def main(argv=None):
    parser = argparse.ArgumentParser(description='生成服务器普通无凭据包或显式 PRIVATE 私人包')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--private-config', type=Path)
    args = parser.parse_args(argv)
    try:
        private = PrivateDeployment(args.private_config) if args.private_config else None
        key = private.load_key() if private else None
        if args.output.exists():
            raise ValueError('输出文件已存在；请使用新路径')
        if private and 'PRIVATE' not in args.output.name:
            raise ValueError('私人包文件名必须含 PRIVATE')
        payloads = {name: (ROOT / 'server_distribution' / name).read_bytes() for name in TEMPLATES}
        payloads['requirements.txt'] = (ROOT / 'requirements.txt').read_bytes()
        payloads.update({'mission_c/' + name: (ROOT / 'mission_c' / name).read_bytes() for name in MODULES})
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(args.output, 'x') as archive:
            for name, payload in payloads.items():
                write_member(archive, name, payload)
            if private:
                write_member(archive, '.private/deployment.json', json.dumps({'profile': 'deepseek-private-v1', 'key_file': 'credential.txt'}))
                write_member(archive, '.private/credential.txt', key)
                write_member(archive, 'PRIVATE.txt', '仅供获授权接收者。本包包含可提取的共享付费凭据，请勿公开上传或转发。显式 once/watch 启动固定 Fetch supplement + model assist，每页各最多一次，批次最多 2*N 次；unknown 尝试不自动重发。请保护本机文件权限。')
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print('已生成服务器 PRIVATE 私人包（仅供授权接收者）' if private else '已生成服务器普通无凭据包')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
