"""Real API smoke test of the distributed executable; credentials stay in env."""
from datetime import datetime
import io
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.parse import urlsplit,parse_qs
import zipfile
import httpx
from openpyxl import load_workbook
from runtime_paths import APP_ROOT,VERSION

def main():
    assert os.environ.get('DEEPSEEK_API_KEY'),'Run with the existing secure API launcher'
    out=APP_ROOT/'validation'/('exe-api-'+datetime.now().strftime('%Y%m%d-%H%M%S'));out.mkdir(parents=True)
    with zipfile.ZipFile(APP_ROOT/'release'/f'MissionB-Windows-x64-v{VERSION}.zip') as z:z.extractall(out)
    folder=out/f'MissionB-Windows-x64-v{VERSION}'
    env={k:v for k,v in os.environ.items() if k.upper() not in ('PYTHONHOME','PYTHONPATH','VIRTUAL_ENV','PLAYWRIGHT_BROWSERS_PATH')}
    env['PATH']=str(Path(os.environ['SystemRoot'])/'System32')
    process=subprocess.Popen([str(folder/'MissionB.exe'),'--no-browser'],cwd=folder,env=env,creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        deadline=time.monotonic()+45
        while not (folder/'data'/'instance.json').exists():
            assert process.poll() is None and time.monotonic()<deadline,'Startup failed';time.sleep(.2)
        info=json.loads((folder/'data'/'instance.json').read_text('utf8'))
        token=parse_qs(urlsplit(info['url']).fragment)['token'][0]
        with httpx.Client(base_url=f'http://127.0.0.1:{info["port"]}',trust_env=False,timeout=15) as client:
            client.post('/api/session',json={'token':token}).raise_for_status()
            settings=client.get('/api/settings').json();assert settings['configured']
            client.post('/api/settings',json={'mode':'deepseek','max_calls':6}).raise_for_status()
            reference=next(c for c in json.loads((APP_ROOT/'validation/live-v1/independent-reference.json').read_text('utf8'))['checks'] if c['school']=='清华大学')
            targets=sorted({a['url'] for a in reference['anchors']})
            text='学校\t学院\t师资url\t教师url\n'+'\n'.join('清华大学\t数学科学系\t'+reference['source']+'\t'+u for u in targets)
            preview=client.post('/api/preview',json={'text':text}).json();assert not preview['errors'],preview
            response=client.post('/api/jobs',json={'preview_id':preview['id']});response.raise_for_status();identifier=response.json()['id']
            deadline=time.monotonic()+300
            while True:
                job=client.get('/api/jobs/'+identifier).json()
                if job['status'] not in ('running','stopping'):break
                assert time.monotonic()<deadline,'Job timeout';time.sleep(.5)
            assert job['status']=='completed',job
            result=job['results'][0];assert result['complete'] and result['verification_result']=='正确',result
            record=client.get('/api/jobs/'+identifier+'/college/'+result['id']).json()
            assert client.get('/api/jobs/'+identifier+'/evidence/'+result['id']+'-0').status_code==200
            book=load_workbook(io.BytesIO(client.get('/api/jobs/'+identifier+'/download/summary').content),read_only=True,data_only=True)
            assert list(book.active.values)==[('大学名','学院名','核验结果','特殊情况说明'),('清华大学','数学科学系','正确',None)];book.close()
            output=folder/'data/runs'/identifier/'output'
            # Only compare in memory; never log or serialize the credential.
            secret=os.environ['DEEPSEEK_API_KEY'].encode()
            for p in (folder/'data').rglob('*'):
                if p.is_file() and p.suffix in ('.json','.html','.txt','.log'):
                    assert secret not in p.read_bytes(),'Credential unexpectedly persisted'
            report={'status':'passed','real_api':job['api'],'school':'清华大学','unique':result['stats']['source_unique'],
                'verification_result':result['verification_result'],'no_python_on_PATH':True,'key_not_persisted':True,
                'evidence_route':True,'summary_download':True,'output':str(output)}
            (out/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
            client.post('/api/shutdown',json={}).raise_for_status()
        assert process.wait(timeout=15)==0
        print(json.dumps(report,ensure_ascii=False))
    finally:
        if process.poll() is None:process.terminate();process.wait(timeout=10)

if __name__=='__main__':main()
