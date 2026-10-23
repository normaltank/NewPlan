"""Offline regression with existing provider answers, never billed as new API use."""
import asyncio
import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from audit import run, without_scheme
from deepseek_api import ApiFailure
from runtime_paths import APP_ROOT

BASE=APP_ROOT.parent/'outputs'/'verified-support-v2.3-20261015'
EXPERIMENT=APP_ROOT.parent/'experimental_deepseek'/'runs'/'snapshot-v1'

class SavedAnswers:
    model='saved-deepseek-flash-replay'
    def __init__(self,*args,max_calls=200,**kwargs):self.calls=[];self.max_calls=max_calls
    async def __aenter__(self):return self
    async def __aexit__(self,*args):pass
    async def ask(self,label,system,payload,**kwargs):
        folder=EXPERIMENT/'pages'/hashlib.sha256(payload['url'].encode()).hexdigest()[:16]
        path=folder/(label+'-plan.json')
        if not path.exists():raise ApiFailure('历史试验未取得此页的模型答案，保持未完成核验')
        self.calls.append({'label':label,'usage':{},'replay':True})
        return json.loads(path.read_text('utf8'))

async def main(output):
    out=APP_ROOT/'validation'/output
    args=SimpleNamespace(input=BASE/'inputs',output=out,plans=BASE/'source_plans.json',
        no_browser=True,replay=BASE,mode='deepseek',max_api_calls=200,cache_dir=APP_ROOT/'validation'/'replay-cache')
    with patch('api_engine.DeepSeekJSON',SavedAnswers):
        _,results,manifest=await run(args)
    old={r['id']:r for r in json.loads((EXPERIMENT/'results.json').read_text('utf8'))}
    checks=[]
    for result in results:
        prior=old[result['id']]
        equal={without_scheme(u) for u in result['source']['links']}=={without_scheme(u) for u in prior['links']}
        checks.append({'school':result['school'],'college':result['college'],
            'complete':result['complete'],'old_complete':prior['complete'],'same_candidate_set':equal,
            'source_unique':result['stats']['source_unique'],'issues':result['source']['issues']})
    report={'mode':'旧HTML与已保存模型回答离线回放；不联网、不新增API费用','checks':checks,
        'passed':all(c['same_candidate_set'] and c['complete']==c['old_complete'] for c in checks)}
    (out/'regression.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(report,ensure_ascii=False),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='saved-v1')
    asyncio.run(main(parser.parse_args().output))
