"""Validate allowlisted distribution assets and startup-script permissions."""
import hashlib
import json
from pathlib import Path
import re
import zipfile
from runtime_paths import APP_ROOT,VERSION

def main():
    results=[]
    for target in sorted((APP_ROOT/'release').glob(f'*v{VERSION}.zip')):
        with zipfile.ZipFile(target) as z:
            assert z.testzip() is None
            entries=z.namelist();prefix=entries[0].split('/')[0]+'/'
            assert not any(set(Path(n).parts)&{'data','outputs','validation','.env','.secrets','model-cache','__pycache__'} for n in entries)
            source='Mac-Linux' in target.name;base=prefix if source else prefix+'_internal/'
            for name in ('api_engine.py','ai_regions.py','deepseek_api.py','audit.py','input_adapter.py','reporting.py','runtime_paths.py','web/app.js','web/index.html'):
                assert z.read(base+name)==(APP_ROOT/name).read_bytes(),name+' differs from tested source'
            if source:
                for name in ('run.sh','install-linux.sh','install-macos.command','start-macos.command'):
                    assert z.getinfo(prefix+name).external_attr>>16 & 0o111
            else:
                assert prefix+'MissionB.exe' in entries
                assert any('/.browsers/' in n and n.endswith('chrome-headless-shell.exe') for n in entries)
            for n in entries:
                if n.endswith(('.py','.json','.html','.js','.md','.txt','.sh','.command','.cmd')):
                    content=z.read(n)
                    assert not re.search(rb'(?:sk-[A-Za-z0-9]{24,}|ghp_[A-Za-z0-9]{30,})',content),'Possible embedded credential'
            results.append({'file':target.name,'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
                'matches_tested_sources':True,'private_data_absent':True,'script_permissions_checked':source})
    assert len(results)==2
    (APP_ROOT/'validation'/'packages.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(results,ensure_ascii=False))

if __name__=='__main__':main()
