"""Bounded child-process workers: independent Crawlee runtime per college."""
import asyncio
import json
import os
import sys
from pathlib import Path

from workbench_store import ROOT, now, read_json


async def run_job(store, job):
    key=job['id']
    folder=store.path.parent/'jobs'/key
    folder.mkdir(parents=True,exist_ok=True)
    pointer=folder/'run.json'
    t=job['target']
    args=[sys.executable,str(ROOT/'api_pilot.py'),'--university',t['university'],'--college',t['college'],
          '--url',t['url'],'--max-pages',str(t.get('max_pages',700)),'--max-calls',str(t.get('max_calls',40)),
          '--max-images',str(t.get('max_images',200)),'--ocr','--browser','--pointer',str(pointer)]
    for entry in t.get('entries',[]):
        args.extend(['--entries',entry])
    if t.get('resume_from'):
        args.extend(['--resume-from',t['resume_from']])
    for url in t.get('prioritize',[]):args.extend(['--prioritize',url])
    env={**os.environ,'PYTHONIOENCODING':'utf-8','PYTHONUNBUFFERED':'1'}
    try:
        with (folder/'worker.log').open('wb') as log:
            proc=await asyncio.create_subprocess_exec(*args,cwd=ROOT,env=env,stdout=log,stderr=log)
            elapsed=0
            while proc.returncode is None:
                try:
                    await asyncio.wait_for(proc.wait(),timeout=2)
                except asyncio.TimeoutError:
                    pass
                p=read_json(pointer,{})
                if p.get('run_dir'):
                    store.update(key,run_dir=p['run_dir'])
                elapsed+=2
                if elapsed>7200:
                    proc.kill()
                    await proc.wait()
                    raise TimeoutError('单学院运行超过两小时')
            p=read_json(pointer,{})
            summary=read_json(Path(p['run_dir'])/'summary.json',{}) if p.get('run_dir') else {}
            store.update(key,state='finished' if proc.returncode==0 and summary else 'failed',finished=now(),
                         error=None if proc.returncode==0 and summary else f'采集进程退出码 {proc.returncode}；原始结果保留')
            if t.get('resume_from') and summary:store.carry_unchanged_reviews(key)
            from quality_pipeline import build
            await asyncio.to_thread(build,store,key)
    except asyncio.CancelledError:
        if 'proc' in locals() and proc.returncode is None:
            proc.terminate()
            await proc.wait()
        store.update(key,state='interrupted',finished=now(),error='工作台停止，原件保留，可创建新运行补采')
        raise
    except Exception as exc:
        store.update(key,state='failed',finished=now(),error=type(exc).__name__)


async def worker(store, once=False):
    while True:
        job=store.claim()
        if job:
            await run_job(store,job)
        elif once:
            return
        else:
            await asyncio.sleep(2)
