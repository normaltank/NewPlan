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
              'api_engine.py','ai_regions.py','deepseek_api.py','test_api_engine.py','test_result_summary.py',
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
    (destination/'使用说明.txt').write_text('Mission B 3.0.1 · API 辅助核验\n\n完整解压到可写文件夹。\nmacOS：双击 install-macos.command；以后双击 start-macos.command。\nLinux：运行 bash install-linux.sh；以后运行 bash run.sh。\n安装器会下载独立 Python、依赖和浏览器；Linux 缺少系统组件时会询问安装。\n\n打开工作台的“API设置”，填入自己的 DeepSeek 密钥并应用。\n密钥只保存于本次进程内，退出后需重新填写。\n也可选择已有规则模式，无需 API，但只覆盖已配置来源。\n\n支持文本、四列表和双表 Excel。结果与证据保存在 data。\n首次安装需要联网。Mac/Linux 安装逻辑已测试，尚未实机验收。\n详细范围和限制见 README.md。本包不含任务数据或作者密钥。\n',encoding='utf-8-sig')


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
        for name in ['web','templates','source_plans.json','audit.py','reporting.py','input_adapter.py','runtime_paths.py','requirements.txt','api_engine.py','ai_regions.py','deepseek_api.py']:
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
        browser_source=ROOT/'.portable-browser' if (ROOT/'.portable-browser').exists() else ROOT.parent/'.portable-browser'
        shutil.copytree(browser_source,windows/'.browsers',ignore=shutil.ignore_patterns('.links'))
        shutil.copy2(ROOT/'source_plans.json',windows/'source_plans.json')
        shutil.copy2(ROOT/'README_distribution.md',windows/'README.md')
        shutil.copytree(ROOT/'templates',windows/'templates')
        (windows/'使用说明.txt').write_text('Mission B 3.0.1 · API 辅助核验\n\n完整解压，然后双击 MissionB.exe。无需另装 Python。\n保留 _internal 和 .browsers 文件夹。\n\n在“API设置”填入自己的 DeepSeek 密钥并应用；密钥仅在本次进程内保存。\n也可选择已有规则模式，无需 API，但只覆盖已配置来源。\n支持文本、四列表和双表 Excel。详细范围和限制见 README.md。\n任务保存在 data；关闭网页后仍在后台运行，可从左下角退出工具。\n本包不含任务数据或作者密钥。\n',encoding='utf-8-sig')
        license_files(windows/'third_party')
    for folder in (source,windows):
        target=RELEASE/(folder.name+'.zip')
        make_zip(folder,target)
        print(json.dumps({'file':target.name,'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}),flush=True)


if __name__=='__main__':
    main()
