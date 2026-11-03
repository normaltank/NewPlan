"""Build a source-only ZIP from an explicit list of the single shared engine."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile
from runtime_paths import VERSION
from server_run import SERVER_VERSION

ROOT = Path(__file__).resolve().parent
SOURCES = (
    'server_run.py', 'server_export.py', 'audit.py', 'reporting.py', 'input_adapter.py',
    'runtime_paths.py', 'api_engine.py', 'ai_regions.py', 'deepseek_api.py',
    'client_pagination.py', 'run_limits.py', 'requirements.txt', 'README_server.md',
    'server-limits.example.json', 'server-plans.example.json',
)


def build(output):
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(['git', 'status', '--porcelain', '--', *SOURCES], cwd=ROOT, text=True).strip())
    files = {name: (ROOT/name).read_bytes() for name in SOURCES}
    metadata = {'server_version': SERVER_VERSION, 'engine_version': VERSION,
                'source_commit': commit, 'source_dirty': dirty,
                'files_sha256': {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
        archive.writestr('PACKAGE.json', json.dumps(metadata, ensure_ascii=False, indent=2))
    return metadata


def main():
    parser = argparse.ArgumentParser(description='Build Mission B server source ZIP; refuses overwrite')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build(args.output.resolve())
    print(str(args.output.resolve()))


if __name__ == '__main__':
    main()
