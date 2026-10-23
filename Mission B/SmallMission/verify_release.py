"""Inspect final archives and write a compact, reproducible handoff record."""
from pathlib import Path
from datetime import datetime
import hashlib
import json
import re
import zipfile

from runtime_paths import VERSION
ROOT=Path(__file__).resolve().parent
RELEASE=ROOT/'release'
files=[]
for path in sorted(RELEASE.glob(f'MissionB-*-v{VERSION}.zip')):
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        names=archive.namelist()
        assert not any(any(p in {'data','outputs','.env','.git','.links','__pycache__'} for p in Path(name).parts) for name in names)
        assert not any(Path(name).name in {'instance.json','app.log','credentials.json','config.toml'} for name in names)
        prefix=names[0].split('/')[0]
        if 'CrossPlatform' in path.name:
            for name in ('run.sh','start-macos.command'):
                info=archive.getinfo(prefix+'/'+name)
                assert (info.external_attr>>16)&0o111
                assert b'\r\n' not in archive.read(info)
            for name in ('app.py','audit.py','reporting.py','input_adapter.py','runtime_paths.py','requirements.txt','source_plans.json'):
                assert archive.read(prefix+'/'+name)==(ROOT/name).read_bytes(),name
        else:
            assert prefix+'/.browsers/chromium_headless_shell-1248/chrome-headless-shell-win64/chrome-headless-shell.exe' in names
            assert prefix+'/third_party/pillow/pillow-12.3.0.dist-info_METADATA' in names
            for name in ('audit.py','reporting.py','input_adapter.py','runtime_paths.py','requirements.txt'):
                assert archive.read(prefix+'/_internal/'+name)==(ROOT/name).read_bytes(),name
        # Scan authored text, not compressed executables or third-party example code.
        for name in names:
            relative=name[len(prefix)+1:]
            if any(x in relative for x in ('.browsers/','third_party/','_internal/playwright/')):
                continue
            if Path(name).suffix in {'.py','.json','.html','.css','.js','.txt','.md'}:
                raw=archive.read(name)
                assert not re.search(rb'(?:ghp_[A-Za-z0-9]{36}|sk-[a-f0-9]{32,64})',raw), 'Credential-shaped content in '+name
        files.append({'file':path.name,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'integrity':'passed','no_task_data_or_credentials':'passed'})

old=json.loads((ROOT/'outputs/live-20261015-final/results.json').read_text(encoding='utf-8'))
replay=json.loads((ROOT/'outputs/package-regression-v2.1-20261015/results.json').read_text(encoding='utf-8'))
fields=['id','complete','needs_human','verdict','stats','corrected_urls']
assert [{k:r[k] for k in fields} for r in old]==[{k:r[k] for k in fields} for r in replay]
portable=sorted((ROOT/'outputs').glob('portable validation 中文 */validation.json'))[-1]
record={'version':VERSION,'created':datetime.now().astimezone().isoformat(),'files':files,
        'tests':{'contract_and_input_and_app':39,'source_zip_after_unzip':39,'previous_college_replay':{'colleges':10,'result':'exact match'},
                 'live_ui':json.loads((ROOT/'outputs/ui-validation-v2.1-20261015/validation.json').read_text(encoding='utf-8')),
                 'windows_portable':json.loads(portable.read_text(encoding='utf-8')),'unix_start_script_syntax':'passed with bash -n'},
        'limitations':['macOS/Linux startup and native runtime not tested on those operating systems','Eight verified roster-page configurations; unknown sites require source-region review','No model API and no explicit profile-page fetches; results concern current source-page links, not true teacher headcounts']}
(RELEASE/f'verification-v{VERSION}.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
(RELEASE/f'SHA256SUMS-v{VERSION}.txt').write_text('\n'.join(f['sha256']+'  '+f['file'] for f in files)+'\n',encoding='utf-8')
(RELEASE/f'交付说明-v{VERSION}.txt').write_text('Mission B 2.1 · 独立师资链接核验工具\n\nWindows 64位：发送 MissionB-Windows-x64-v2.1.0.zip，完整解压后双击 MissionB.exe。无需安装Python。\nmacOS/Linux：发送 MissionB-CrossPlatform-v2.1.0.zip，先安装Python 3.11+，按包内README启动；首次需联网安装。\n\n支持文本粘贴和XLSX/XLSM/XLS/CSV/TSV/TXT文件输入，预览、进度、逐项差异、历史记录与Excel导出。无需DS API。\n\nWindows版已独立运行验收；macOS/Linux版本尚未实机验证。当前配置8个已验证来源页，陌生页面需核实名单区域，无法读取时保留原始输入并转人工。\n\n包内不含历史任务数据和密钥。详细测试记录见 verification-v2.1.0.json，文件校验见 SHA256SUMS-v2.1.0.txt。\n',encoding='utf-8-sig')
print(json.dumps({'status':'passed','files':files},ensure_ascii=False))
