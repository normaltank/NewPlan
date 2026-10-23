"""One-shot creation of the owner-requested private repository; no content upload."""
import getpass
import json
import sys
from pathlib import Path

import httpx

token=getpass.getpass('GitHub token (hidden): ').strip()
try:
    with httpx.Client(base_url='https://api.github.com',trust_env=False,follow_redirects=False,
                      timeout=30,headers={'Authorization':f'Bearer {token}',
                      'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2026-03-10'}) as client:
        me=client.get('/user')
        if me.status_code!=200:
            raise RuntimeError(f'Account verification: HTTP {me.status_code}')
        login=me.json().get('login')
        if login!='normaltank':
            raise RuntimeError('Authenticated account differs from the project owner; stopped.')
        existing=client.get('/repos/normaltank/NewPlan')
        if existing.status_code==200:
            result=existing.json()
            outcome='already_exists_unchanged'
        elif existing.status_code==404:
            created=client.post('/user/repos',json={'name':'NewPlan','private':True,'auto_init':False})
            if created.status_code!=201:
                raise RuntimeError(f'Repository creation: HTTP {created.status_code}')
            result=created.json()
            outcome='created'
        else:
            raise RuntimeError(f'Repository existence check: HTTP {existing.status_code}')
        checked=client.get('/repos/normaltank/NewPlan')
        if checked.status_code!=200:
            raise RuntimeError(f'Post-creation verification: HTTP {checked.status_code}')
        result=checked.json()
        metadata={'outcome':outcome,**{k:result[k] for k in ['id','full_name','html_url','private','default_branch','created_at','size']}}
        out=Path(__file__).resolve().parent/'runs'/'newplan-repository.json'
        out.write_text(json.dumps(metadata,indent=2),encoding='utf-8')
        print(json.dumps(metadata),flush=True)
except (RuntimeError,httpx.HTTPError) as error:
    print(str(error).replace(token,'[REDACTED]') if isinstance(error,RuntimeError) else type(error).__name__,flush=True)
    sys.exit(1)
finally:
    token=''
