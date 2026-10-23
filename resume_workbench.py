"""Create an isolated recovery run for a finished/failed job, preserving all originals."""
import argparse
import asyncio
import os
import sys
from pathlib import Path
from workbench_store import Store, ROOT, now, read_json

async def main(args):
    store=Store(ROOT/'runs'/'workbench'/'workbench.db')
    old=store.job(args.job)
    if old['state'] in ('queued','running') or not old['run_dir']:
        raise ValueError('Recovery requires a stopped job with saved originals')
    with store.db() as con:
        key=store._insert_job(con,old['batch_id'],{**old['target'],'recovery_from':old['id']},old['id'])
        con.execute("UPDATE jobs SET state='running',started=? WHERE id=?",(now(),key))
    out=store.path.parent/'jobs'/key
    out.mkdir(parents=True,exist_ok=True)
    pointer=out/'run.json'
    print('RECOVERY_JOB='+key,flush=True)
    command=[sys.executable,str(ROOT/'api_pilot.py'),'--university',old['target']['university'],
             '--college',old['target']['college'],'--url',old['target']['url'],'--resume-from',old['run_dir'],
             '--max-pages','700','--max-images','700','--max-calls','20','--ocr','--browser','--pointer',str(pointer)]
    try:
        with (out/'worker.log').open('wb') as log:
            proc=await asyncio.create_subprocess_exec(*command,cwd=ROOT,env={**os.environ,'PYTHONIOENCODING':'utf-8'},stdout=log,stderr=log)
            while proc.returncode is None:
                try:await asyncio.wait_for(proc.wait(),timeout=2)
                except asyncio.TimeoutError:pass
                run=read_json(pointer,{})
                if run.get('run_dir'):store.update(key,run_dir=run['run_dir'])
        store.update(key,state='finished' if proc.returncode==0 else 'failed',finished=now(),error=None if proc.returncode==0 else '恢复进程失败，已保留材料')
        print('EXIT='+str(proc.returncode),flush=True)
    except BaseException:
        if 'proc' in locals() and proc.returncode is None:
            proc.terminate();await proc.wait()
        store.update(key,state='interrupted',finished=now(),error='恢复进程中断')
        raise

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--job',required=True)
    asyncio.run(main(parser.parse_args()))
