"""Allowlisted release builder. Never includes task data, tokens, or parent files."""
from pathlib import Path
from datetime import datetime
import argparse
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parent
from runtime_paths import VERSION
STAGE=ROOT/('.release-stage-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
RELEASE=ROOT/'release'
SOURCE_FILES=['app.py','audit.py','reporting.py','input_adapter.py','runtime_paths.py','bootstrap.py',
              'requirements.txt','source_plans.json','run.sh','start-macos.command','start-windows.cmd',
              'test_audit.py','test_distribution.py','test_bootstrap.py','test_multisource.py','test_site_support.py',
              'install-macos.command','install-linux.sh']


def copy_source(destination):
    destination.mkdir(parents=True,exist_ok=False)
    for name in SOURCE_FILES:
        shutil.copy2(ROOT/name,destination/name)
    shutil.copy2(ROOT/'README_distribution.md',destination/'README.md')
    for name in ('web','templates','tests/fixtures'):
        shutil.copytree(ROOT/name,destination/name)
    (destination/'使用说明.txt').write_text('Mission B 师资链接核验 · 自动环境安装版\n\n请先完整解压到自己可写的文件夹。\n\nmacOS 14+：双击 install-macos.command，自动安装并打开工作台。\n以后双击 start-macos.command。若无法双击，在此文件夹终端运行 bash run.sh。\n\nLinux：在此文件夹终端运行 bash install-linux.sh。\n以后运行 bash run.sh。推荐 Debian 12/13 或 Ubuntu 22.04/24.04/26.04，64位 x86/ARM。\n缺少系统组件时会询问是否安装，可能需要管理员密码。\n\nMac/Linux 无需预装 Python，无需 API；首次下载需联网，可能需要数分钟。\n环境保存在当前工具文件夹，不更改系统 Python。\nWindows 源码版仍需要 Python 3.11+，使用 start-windows.cmd；普通 Windows 用户请使用原独立 exe 包。\n\n失败后可重试；安装日志在隐藏文件夹 .runtime 内。\n详细说明与支持范围见 README.md。Mac/Linux 尚未实机验收。\n本包不包含你的任务数据。\n',encoding='utf-8-sig')


def license_files(destination):
    destination.mkdir(exist_ok=True)
    packages=['httpx','httpcore','anyio','h11','idna','certifi','beautifulsoup4','soupsieve','typing_extensions',
              'lxml','openpyxl','et_xmlfile','xlrd','playwright','pyee','greenlet','pyinstaller','pillow']
    versions={}
    for name in packages:
        dist=importlib.metadata.distribution(name)
        versions[name]=dist.version
        target=destination/name;target.mkdir(exist_ok=True)
        for file in dist.files or []:
            if any(key in str(file).lower() for key in ('license','licence','copying','copyright','notice')) or (str(file).endswith('.dist-info/METADATA')):
                path=Path(dist.locate_file(file))
                if path.is_file():
                    clean=str(file).replace('/','_').replace('\\','_').replace('..','_')
                    shutil.copy2(path,target/clean)
    pylicense=Path(sys.base_prefix)/'LICENSE.txt'
    if pylicense.exists():
        shutil.copy2(pylicense,destination/'Python-LICENSE.txt')
    (destination/'versions.json').write_text(json.dumps(versions,indent=2),encoding='utf-8')


def make_zip(directory, target):
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in sorted(directory.rglob('*')):
            if not path.is_file():
                continue
            relative=path.relative_to(directory)
            if any(p in {'data','__pycache__','.env','.links'} for p in relative.parts):
                raise RuntimeError('不应出现在发行目录的路径：'+str(relative))
            info=zipfile.ZipInfo.from_file(path,directory.name+'/'+relative.as_posix())
            info.create_system=3
            info.external_attr=(0o100755 if path.suffix in ('.sh','.command') else 0o100644)<<16
            info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,path.read_bytes())


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source-only',action='store_true',help='Only build the automatic environment source package')
    args=parser.parse_args()
    STAGE.mkdir(exist_ok=True);RELEASE.mkdir(exist_ok=True)
    source=STAGE/f'MissionB-Mac-Linux-v{VERSION}'
    if not source.exists():
        copy_source(source)
    if args.source_only:
        target=RELEASE/(source.name+'.zip')
        make_zip(source,target)
        print(json.dumps({'file':target.name,'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}),flush=True)
        return
    # Distribution paths are new; the builder never deletes previous builds.
    executable=STAGE/'MissionB'
    if not executable.exists():
        command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--windowed','--noupx',
                 '--name','MissionB','--distpath',str(STAGE),'--workpath',str(ROOT/'.build-work'),
                 '--specpath',str(ROOT/'.build-spec')]
        for name in ['web','templates','source_plans.json','audit.py','reporting.py','input_adapter.py','runtime_paths.py','requirements.txt']:
            command+=['--add-data',str(ROOT/name)+';'+(name if (ROOT/name).is_dir() else '.')]
        for name in ('httpx','beautifulsoup4','lxml','openpyxl','playwright','xlrd'):
            command+=['--copy-metadata',name]
        command.append(str(ROOT/'app.py'))
        env=os.environ.copy()
        env['PYINSTALLER_CONFIG_DIR']=str(ROOT/'.build-pyinstaller-cache')
        subprocess.check_call(command,cwd=ROOT,env=env)
    windows=STAGE/f'MissionB-Windows-x64-v{VERSION}'
    if not windows.exists():
        executable.rename(windows)
        shutil.copytree(ROOT/'.portable-browser',windows/'.browsers',ignore=shutil.ignore_patterns('.links'))
        shutil.copy2(ROOT/'source_plans.json',windows/'source_plans.json')
        shutil.copy2(ROOT/'README_distribution.md',windows/'README.md')
        shutil.copytree(ROOT/'templates',windows/'templates')
        (windows/'使用说明.txt').write_text('Mission B 师资链接核验\n\n请完整解压，然后双击 MissionB.exe。\n无需 Python、无需 DeepSeek API。\n不要只复制exe，_internal和.browsers文件夹也需要保留。\n\n详细说明见 README.md。任务数据保存在 data 内；关闭网页后仍在后台运行，可从工作台左下角退出。\n本包不包含你的任务数据。\n',encoding='utf-8-sig')
        license_files(windows/'third_party')
    for folder in (source,windows):
        target=RELEASE/(folder.name+'.zip')
        make_zip(folder,target)
        print(json.dumps({'file':target.name,'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}),flush=True)


if __name__=='__main__':
    main()
