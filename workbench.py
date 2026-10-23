"""Local acquisition/review workbench; optional nightly batch CLI for server deployment."""
import argparse
import asyncio
import json
import os
import atexit
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from workbench_runner import worker
from workbench_store import ROOT, Conflict, Store, read_json
from batch_input import preview_input
from workbench_export import accepted_records, tables, csv_bytes, workbook_bytes, TEACHER_HEADERS, SOURCE_HEADERS, MERGE_HEADERS, NOTE_HEADERS, STATUS_HEADERS
from workbench_export import university_zip


def make_app(store, run_workers=False, nightly=None, config=None):
    async def assess_finished():
        from quality_pipeline import build
        while True:
            with store.db() as con:
                keys=[r['id'] for r in con.execute("SELECT j.id FROM jobs j WHERE j.state NOT IN ('running','queued') AND j.run_dir IS NOT NULL AND NOT EXISTS (SELECT 1 FROM jobs c WHERE c.parent_id=j.id)")]
            for key in keys:
                try:
                    await asyncio.to_thread(build,store,key,summary_only=True)
                except Exception:
                    import logging
                    logging.exception('Automatic assessment failed for job %s',key)
            await asyncio.sleep(15)

    async def schedule():
        while True:
            dt=datetime.now(ZoneInfo('Asia/Singapore'))
            if dt.strftime('%H:%M')==nightly and config:
                with store.db() as con:
                    exists=con.execute('SELECT 1 FROM schedule_runs WHERE day=?',(dt.date().isoformat(),)).fetchone()
                if not exists:
                    batch=store.create_batch(config['name']+' '+dt.date().isoformat(),config['targets'])
                    with store.db() as con:
                        con.execute('INSERT INTO schedule_runs VALUES(?,?)',(dt.date().isoformat(),batch))
            await asyncio.sleep(20)

    @asynccontextmanager
    async def lifespan(app):
        tasks=[asyncio.create_task(assess_finished())]
        if run_workers:
            store.interrupted()
            tasks.extend(asyncio.create_task(worker(store)) for _ in range(3))
            if nightly:
                tasks.append(asyncio.create_task(schedule()))
        yield
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)

    app=FastAPI(title='采集与复核工作台',lifespan=lifespan,docs_url='/api/docs')
    app.mount('/static',StaticFiles(directory=ROOT/'workbench-static'),name='static')

    @app.middleware('http')
    async def origin_guard(request,call_next):
        # No CORS, no arbitrary host binding, reject cross-origin writes (including DNS rebinding).
        if request.url.hostname not in ('localhost','127.0.0.1','testserver'):
            return JSONResponse({'detail':'工作台当前仅开放本机访问'},status_code=403)
        if request.method not in ('GET','HEAD','OPTIONS'):
            origin=request.headers.get('origin')
            if origin and urlparse(origin).netloc!=request.url.netloc:
                return JSONResponse({'detail':'跨站提交被拒绝'},status_code=403)
            if int(request.headers.get('content-length','0'))>2_000_000:
                return JSONResponse({'detail':'提交过大'},status_code=413)
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Cache-Control']='no-store'
        response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"
        return response

    @app.exception_handler(Conflict)
    async def conflict(request,exc):
        return JSONResponse({'detail':str(exc)},status_code=409)

    @app.exception_handler(ValueError)
    async def invalid(request,exc):
        return JSONResponse({'detail':str(exc)},status_code=422)

    @app.exception_handler(KeyError)
    async def missing(request,exc):
        return JSONResponse({'detail':str(exc)},status_code=404)

    @app.get('/')
    @app.get('/review/{key}')
    def index(key=None):
        return FileResponse(ROOT/'workbench-static'/'index.html')

    @app.get('/api/overview')
    def overview():
        return JSONResponse({**store.listing(),'nightly':nightly,'timezone':'Asia/Singapore','external_push':'not_configured'})

    @app.get('/api/jobs/{key}')
    def job(key,include_related:bool=False):
        cat=store.catalog(key)
        cat['cross_college']=[]
        if include_related:
            _,catalogs=store.batch_catalogs(cat['job']['batch_id'])
            cat['cross_college']=[r for r in tables(catalogs)['records'] if len(r['members'])>1 and any(m['run_id']==key for m in r['members'])]
        return JSONResponse(cat)

    @app.get('/api/jobs/{key}/history')
    def history(key):
        store.job(key)
        return store.history(key)

    @app.get('/api/jobs/{key}/related')
    def related(key):
        _,catalogs=store.batch_catalogs(store.job(key)['batch_id'])
        groups=[r for r in tables(catalogs)['records'] if len(r['members'])>1 and any(m['run_id']==key for m in r['members'])]
        # The review banner only needs links and conflicts, not every biography.
        return JSONResponse([{'college':r['college'],'field_conflicts':r['field_conflicts'],
            'members':[{k:m[k] for k in ('run_id','person_id','college')} for m in r['members']]} for r in groups])

    @app.post('/api/jobs/{key}/decisions/{item_id}')
    def decision(key,item_id,payload:dict):
        return store.decide(key,item_id,payload)

    @app.post('/api/jobs/{key}/bulk-decisions')
    def bulk_decision(key,payload:dict):
        return store.decide_many(key,payload)

    @app.post('/api/jobs/{key}/people')
    def add_person(key,payload:dict):
        return store.add_person(key,payload)

    @app.post('/api/jobs/{key}/reruns')
    def rerun(key,payload:dict):
        child=store.rerun(key,payload.get('entries',[]),payload.get('actor',''),payload.get('reason',''))
        return {'id':child,'review_url':'/review/'+child}

    @app.post('/api/jobs/{key}/continuations')
    def continuation(key,payload:dict):
        child=store.continue_run(key,payload.get('actor',''),payload.get('max_pages',200),payload.get('max_calls',20))
        return {'id':child,'review_url':'/review/'+child}

    @app.post('/api/batches')
    def create(payload:dict):
        preview=preview_input(text=payload.get('text'),targets=payload.get('targets',[]))
        if preview['errors']:
            raise HTTPException(422,'；'.join(f"第 {e['row']} 行：{e['message']}" if e['row'] else e['message'] for e in preview['errors']))
        return {'id':store.create_batch(payload.get('name','新批次'),preview['targets'],payload.get('request_id'))}

    @app.post('/api/batches/preview')
    def preview(payload:dict):
        return preview_input(text=payload.get('text'),targets=payload.get('targets',[]))

    def table_response(catalogs, key, format, table):
        data=tables(catalogs)
        if format=='xlsx':
            return Response(workbook_bytes(data),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                            headers={'Content-Disposition':f'attachment; filename="faculty-{key}.xlsx"'})
        if format=='csv':
            if table not in ('teachers','sources','merges','notes','statuses'):
                raise HTTPException(422,'表格应为 teachers、sources、merges、notes 或 statuses')
            headers={'teachers':TEACHER_HEADERS,'sources':SOURCE_HEADERS,'merges':MERGE_HEADERS,'notes':NOTE_HEADERS,'statuses':STATUS_HEADERS}
            return Response(csv_bytes(headers[table],data[table]),media_type='text/csv',
                            headers={'Content-Disposition':f'attachment; filename="{table}-{key}.csv"'})
        raise HTTPException(422,'支持 xlsx 或 csv')

    @app.get('/api/batches/{key}/export')
    def batch_export(key,format:str='xlsx',table:str='teachers',university:str=''):
        batch,catalogs=store.batch_catalogs(key)
        if university:
            catalogs=[c for c in catalogs if c['job']['target']['university']==university]
            if not catalogs:raise HTTPException(404,'本批没有这所大学')
        if format=='zip':
            return Response(university_zip(catalogs),media_type='application/zip',
                            headers={'Content-Disposition':f'attachment; filename="universities-{key}.zip"'})
        if format=='json':
            return JSONResponse({'batch':batch,**tables(catalogs)})
        return table_response(catalogs,key,format,table)

    @app.get('/api/jobs/{key}/evidence')
    def evidence(key,path:str,text:bool=False):
        cat=store.catalog(key,apply_auto=False)
        if not cat['job']['run_dir']:
            raise HTTPException(404,'尚无原件')
        root=Path(cat['job']['run_dir']).resolve()
        requested=root/path
        selected=requested.resolve()
        if not selected.is_relative_to(root) or not selected.is_file():
            raise HTTPException(404,'原件不存在')
        # Resolve only the requested file for the physical boundary check.
        # Registry membership uses normalized paths, without touching thousands
        # of unrelated files on every evidence request.
        def registered(value):return os.path.normcase(os.path.abspath(root/value))
        requested_key=registered(path)
        allowed=set()
        for person in cat['people']:
            if person.get('body_path'):
                allowed.add(registered(person['body_path']))
        for p in cat['pages']:
            for name in ('source.html','page-text.txt','body-text.txt','native-text.txt','body.html','metadata.json','rendered.html','rendered-text.txt'):
                allowed.add(registered(Path(p['directory'])/name))
        for m in cat['media']:
            for name in (m['source_file'],'ocr.json','ocr.txt'):
                allowed.add(registered(Path(m['directory'])/name))
        for d in cat['documents']:
            folder=root/d['path']
            if requested_key.startswith(registered(d['path'])+os.sep):
                allowed.update(registered(p) for p in folder.rglob('*') if p.is_file() and p.suffix in ('.pdf','.png','.txt','.json'))
        if requested_key not in allowed:
            raise HTTPException(403,'只允许访问本次运行已登记的原件')
        if text:
            if selected.suffix not in ('.txt','.html','.json'):
                raise HTTPException(422,'这份原件不是文本')
            return Response(selected.read_text(encoding='utf-8',errors='replace'),media_type='text/plain')
        if selected.suffix=='.html':
            return FileResponse(selected,media_type='text/plain',filename=selected.name)
        return FileResponse(selected)

    @app.get('/api/jobs/{key}/export')
    def export(key,format:str='json',table:str='teachers'):
        cat=store.catalog(key)
        accepted=accepted_records(cat)
        if format in ('csv','xlsx'):
            return table_response([cat],key,format,table)
        if format!='json':
            raise HTTPException(422,'支持 json、xlsx 或 csv')
        return JSONResponse({'job':cat['job'],'college_review':cat['college_review'],'accepted':accepted,
                             'pending_or_excluded':[p for p in cat['people'] if p['review']['status'] not in ('accepted','auto_accepted')],
                             'issues':cat['issues'],'audit':store.history(key)},
                            headers={'Content-Disposition':f'attachment; filename="review-{key}.json"'})
    return app


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--db',default=str(ROOT/'runs'/'workbench'/'workbench.db'))
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--seed',help='Create a batch on startup (each invocation creates a new batch)')
    parser.add_argument('--batch',help='Run one config headlessly, then exit; suitable for a server scheduler')
    parser.add_argument('--nightly',help='Optional HH:MM daily Asia/Singapore; requires --schedule-config')
    parser.add_argument('--schedule-config')
    parser.add_argument('--review-only',action='store_true',help='Serve reviews against the same database without starting acquisition workers')
    args=parser.parse_args()
    lock=None
    if not args.batch:
        lock_path=Path(args.db).with_suffix(f'.review-{args.port}.lock' if args.review_only else '.server.lock')
        lock_path.parent.mkdir(parents=True,exist_ok=True)
        lock=lock_path.open('a+b')
        lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            lock.close()
            parser.error('该数据库已有工作台实例，请使用已运行的服务')
        atexit.register(lock.close)
    store=Store(args.db)
    config=read_json(args.seed or args.batch) if args.seed or args.batch else None
    if config:
        print('BATCH_ID='+store.create_batch(config['name'],config['targets']),flush=True)
    if args.batch:
        async def once():
            await asyncio.gather(*(worker(store,once=True) for _ in range(3)))
        asyncio.run(once())
        return
    if args.nightly:
        datetime.strptime(args.nightly,'%H:%M')
        if not args.schedule_config:
            parser.error('--nightly requires --schedule-config')
    if not args.review_only and not os.environ.get('DEEPSEEK_API_KEY'):
        parser.error('DEEPSEEK_API_KEY is required for acquisition workers')
    import uvicorn
    uvicorn.run(make_app(store,run_workers=not args.review_only,nightly=args.nightly,config=read_json(args.schedule_config) if args.schedule_config else None),
                host='127.0.0.1',port=args.port,access_log=False)


if __name__=='__main__':
    main()
