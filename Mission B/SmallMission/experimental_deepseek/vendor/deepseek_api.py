"""Bounded official DeepSeek JSON client. Secrets only enter through the environment."""
import argparse
import asyncio
import hashlib
import json
import os
import re
import time
from pathlib import Path

import httpx

BASE_URL = 'https://api.deepseek.com'
DEFAULT_MODEL = 'deepseek-flash'


class ApiFailure(RuntimeError):
    pass


class DeepSeekJSON:
    def __init__(self, output: Path, model=DEFAULT_MODEL, max_calls=20):
        self.key = os.environ.get('DEEPSEEK_API_KEY', '').strip()
        if not self.key:
            raise ApiFailure('DEEPSEEK_API_KEY is not configured')
        self.output = output
        output.mkdir(parents=True, exist_ok=True)
        self.model = model
        self.max_calls = max_calls
        self.calls = []
        self.http = httpx.AsyncClient(base_url=BASE_URL, trust_env=False, follow_redirects=False,
                                     timeout=httpx.Timeout(120,connect=20),
                                     headers={'Authorization':f'Bearer {self.key}'})

    def save(self, name, value):
        text=json.dumps(value,ensure_ascii=False,indent=2)
        # Defensive redaction if the provider echoes any credential in an error response.
        text=text.replace(self.key,'[REDACTED]')
        text=re.sub(r'sk-[A-Za-z0-9_-]{16,}', '[REDACTED]',text)
        destination=self.output/name
        temporary=destination.with_suffix(destination.suffix+'.tmp')
        temporary.write_text(text,encoding='utf-8')
        # Windows readers can briefly hold a delete-denying handle while the UI polls.
        # Keep the last complete JSON readable and retry the atomic replacement.
        for attempt in range(40):
            try:
                temporary.replace(destination)
                break
            except PermissionError:
                if attempt==39:
                    raise
                time.sleep(.025)

    async def __aenter__(self):
        return self

    async def __aexit__(self,*args):
        await self.http.aclose()

    async def models(self):
        response=await self.http.get('/models')
        if response.status_code!=200:
            raise ApiFailure(f'Model discovery returned HTTP {response.status_code}')
        data=response.json()
        self.save('models.json',data)
        return [m['id'] for m in data.get('data',[])]

    async def ask(self,label,system,payload,max_tokens=6000):
        if len(self.calls)>=self.max_calls:
            raise ApiFailure('API call budget reached')
        index=len(self.calls)+1
        task={'model':self.model,'messages':[{'role':'system','content':system},
              {'role':'user','content':json.dumps(payload,ensure_ascii=False)}],
              'response_format':{'type':'json_object'},'thinking':{'type':'disabled'},
              'max_tokens':max_tokens,'stream':False,'temperature':0}
        self.save(f'{index:02}-{label}-request.json',task)
        started=time.perf_counter()
        row={'index':index,'label':label,'requested_model':self.model,
             'request_sha256':hashlib.sha256(json.dumps(task,sort_keys=True).encode()).hexdigest()}
        self.calls.append(row)
        try:
            response=await self.http.post('/chat/completions',json=task)
            row['status']=response.status_code
            if response.status_code!=200:
                # Record only the provider's machine error code, never headers or exception repr.
                try:
                    row['provider_error_code']=str(response.json().get('error',{}).get('code',''))[:80]
                except (ValueError,AttributeError):
                    pass
                raise ApiFailure(f'DeepSeek returned HTTP {response.status_code}')
            data=response.json()
            row.update({'id':data.get('id'),'returned_model':data.get('model'),
                        'usage':data.get('usage',{}),'finish_reason':data['choices'][0].get('finish_reason')})
            self.save(f'{index:02}-{label}-response.json',data)
            if row['finish_reason']!='stop':
                raise ApiFailure('Model output did not finish normally')
            result=json.loads(data['choices'][0]['message']['content'])
            if not isinstance(result,dict):
                raise ApiFailure('Expected a JSON object')
            return result
        except (httpx.HTTPError,ValueError,KeyError,IndexError) as exc:
            row['error_type']=type(exc).__name__
            raise ApiFailure(f'API request or structured response failed: {type(exc).__name__}') from None
        finally:
            row['seconds']=round(time.perf_counter()-started,3)
            self.save('calls.json',self.calls)


async def probe():
    from benchmark import new_run
    out=new_run('deepseek-api-probe')
    async with DeepSeekJSON(out/'api',max_calls=1) as api:
        available=await api.models()
        if api.model not in available:
            raise ApiFailure(f'Configured model unavailable; returned model IDs: {available}')
        result=await api.ask('connection','Return only JSON. Output {"ok":true}.',{'check':'connection'},max_tokens=100)
        print(json.dumps({'run_dir':str(out),'base_url':BASE_URL,'model':api.model,
                          'result':result,'usage':api.calls[0].get('usage',{})},ensure_ascii=False),flush=True)


if __name__=='__main__':
    argparse.ArgumentParser().add_argument('--probe',action='store_true')
    try:
        asyncio.run(probe())
    except ApiFailure as error:
        print(str(error),flush=True)
        raise SystemExit(1)
