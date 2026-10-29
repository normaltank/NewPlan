"""Single-host local web adapter. BatchService owns every task and run intention."""
from contextlib import asynccontextmanager
from dataclasses import dataclass
import json
from pathlib import Path
import re
import tempfile
import threading
import zipfile

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .batch import BatchService

ASSETS = Path(__file__).with_name('web_static')
MAX_UPLOAD = 20 * 1024 * 1024
MAX_FILES = 20


@dataclass(frozen=True)
class WebPolicy:
    allow_live: bool = False
    allow_paid: bool = False
    paid_max_calls: int = 0


class StartOptions(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mode: str = 'cache'
    cache_id: str = 'demo'
    fetch_mode: str = 'off'
    model_mode: str = 'off'
    allow_paid: bool = False
    paid_max_calls: int = Field(default=0, ge=0)


class LocalBoundary:
    """Reject foreign Host/origin and bound streamed bodies before form parsing."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        headers = dict(scope['headers'])
        host = headers.get(b'host', b'').decode('latin1').lower()
        from urllib.parse import urlsplit
        try:
            hostname = urlsplit('//'+host).hostname
        except ValueError:
            hostname = None
        origin = headers.get(b'origin', b'').decode('latin1')
        expected = scope.get('scheme', 'http')+'://'+host
        mutation = scope['method'] not in {'GET', 'HEAD'}
        error = None
        if hostname not in {'localhost', '127.0.0.1', '::1'}:
            error = (403, '仅允许本机地址')
        elif origin and origin != expected:
            error = (403, '请求必须来自当前页面')
        elif headers.get(b'sec-fetch-site') == b'cross-site':
            error = (403, '不接受跨站请求')
        elif mutation and headers.get(b'x-mission-c') != b'1':
            error = (403, '缺少本地页面请求标记')
        if error:
            await JSONResponse({'detail':error[1]}, status_code=error[0])(scope, receive, send)
            return
        if mutation:
            body = bytearray()
            while True:
                message = await receive()
                if message['type'] == 'http.disconnect':
                    return
                body.extend(message.get('body', b''))
                if len(body) > MAX_UPLOAD + 1024 * 1024:
                    await JSONResponse({'detail':'上传总量不能超过 20 MiB'}, status_code=413)(scope, receive, send)
                    return
                if not message.get('more_body'):
                    break
            delivered = False
            original_receive = receive

            async def bounded_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {'type':'http.request', 'body':bytes(body), 'more_body':False}
                return await original_receive()
            receive = bounded_receive
        async def protected_send(message):
            if message['type'] == 'http.response.start':
                message['headers'] += [(b'x-content-type-options', b'nosniff'),
                    (b'cache-control', b'no-store'), (b'referrer-policy', b'no-referrer'),
                    (b'content-security-policy', b"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")]
            await send(message)
        await self.app(scope, receive, protected_send)


def preflight(value):
    schools = {}
    for task in value['tasks']:
        school = schools.setdefault(task['school'], {'school':task['school'], 'colleges':set(), 'tasks':0})
        school['tasks'] += 1
        school['colleges'].update(r['college'] for r in task['relations'])
    rows = sum(len(t['sources']) for t in value['tasks'])
    return {'files':len(value['inputs']), 'accepted_rows':rows, 'unique_tasks':len(value['tasks']),
        'duplicate_rows':rows-len(value['tasks']), 'issue_count':len(value['issues']),
        'schools':[dict(s, colleges=sorted(s['colleges'])) for s in schools.values()]}


def summary(value, error=None):
    """No source body/biography goes through polling. Details are paged separately."""
    done = sum(value['counts'].get(state, 0) for state in ('success','review','failed','program_error','artifact_missing'))
    return {key:value[key] for key in ('id','state','paused','queued','counts','quality_counts','completeness')} | {
        'preflight':preflight(value), 'processed':done, 'total':len(value['tasks']),
        'running':value['counts'].get('running', 0),
        'mode':('live' if value['run_options']['live'] else 'cache') if value['run_options'] else None,
        'worker_error':error}


def create_app(data_root, *, policy=None, cache_manifest=None):
    policy = policy or WebPolicy()
    service = BatchService(data_root)
    # Only startup-configured files can become cache inputs. No HTTP filesystem paths.
    caches = {'local':Path(cache_manifest).resolve()} if cache_manifest else {}
    errors = {}
    stop = threading.Event()

    def policy_error(options):
        if options['live'] and not policy.allow_live:
            return '当前服务未开放在线访问；请使用严格缓存模式'
        if options['allow_paid'] and (not policy.allow_paid or options['paid_max_calls'] > policy.paid_max_calls or options['paid_max_calls'] < 1):
            return '当前服务不允许此付费预算'
        if options['live'] and (options['fetch_mode'] != 'off' or options['model_mode'] != 'off') and not options['allow_paid']:
            return '在线 Fetch/模型需要服务端允许付费及正数预算'
        return None

    def worker():
        while not stop.is_set():
            try:
                batches = service.list_batches()
                for batch in batches:
                    if stop.is_set():
                        break
                    if not batch['queued'] or batch['paused']:
                        continue
                    blocked = policy_error(batch['run_options'])
                    if blocked:
                        errors[batch['id']] = blocked
                        continue
                    try:
                        service.run(batch['id'], max_items=1)
                        errors.pop(batch['id'], None)
                    except (ValueError, OSError) as error:
                        # A CLI/other worker can own the process lock. It remains authority.
                        errors[batch['id']] = str(error)
            except Exception:
                # Keep the local server alive, with an explicit visible service failure.
                errors['_service'] = '后台读取失败；请检查数据目录和服务日志'
            stop.wait(.25)

    @asynccontextmanager
    async def lifespan(app):
        thread = threading.Thread(target=worker, name='mission-c-web-worker', daemon=True)
        thread.start()
        yield
        stop.set()
        thread.join(timeout=2)

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(LocalBoundary)
    app.mount('/assets', StaticFiles(directory=ASSETS), name='assets')

    @app.exception_handler(ValueError)
    async def value_error(request, error):
        return JSONResponse({'detail':str(error)}, status_code=409 if '另一进程' in str(error) else 400)

    @app.exception_handler(OSError)
    async def file_error(request, error):
        return JSONResponse({'detail':'文件操作失败；请检查数据目录和服务日志'}, status_code=400)

    def batch(ident):
        if not re.fullmatch('[0-9a-f]{32}', ident):
            raise HTTPException(404, '未知批次')
        try:
            return service.status(ident)
        except ValueError:
            raise HTTPException(404, '未知批次')

    @app.get('/')
    def index():
        return FileResponse(ASSETS/'index.html', media_type='text/html')

    @app.get('/api/config')
    def config():
        return {'allow_live':policy.allow_live, 'allow_paid':policy.allow_paid,
            'paid_max_calls':policy.paid_max_calls, 'max_upload_mib':20, 'max_files':MAX_FILES,
            'caches':[{'id':'demo','label':'虚构离线示例缓存'}] + ([{'id':'local','label':'启动时指定的本地缓存'}] if caches else [])}

    @app.post('/api/demo')
    def demo():
        prepared = service.prepare_demo()
        caches['demo'] = service.root/prepared['cache_manifest']
        return summary(prepared['batch'])

    @app.get('/api/sample.xlsx')
    def sample():
        prepared = service.prepare_demo()
        caches['demo'] = service.root/prepared['cache_manifest']
        source = service.root/prepared['batch']['inputs'][0]['stored_file']
        return FileResponse(source, filename='Mission-C-离线示例.xlsx')

    @app.post('/api/import')
    async def upload(request: Request):
        async with request.form(max_files=MAX_FILES, max_fields=0) as form:
            uploads = form.getlist('files')
            if not uploads or len(uploads) > MAX_FILES or len(form) != 1:
                raise HTTPException(400, '请选择 1–20 个 XLSX 文件')
            with tempfile.TemporaryDirectory(prefix='mission-c-upload-') as temporary:
                paths, total = [], 0
                for index, item in enumerate(uploads):
                    name = getattr(item, 'filename', '') or ''
                    if (len(name)>200 or name.startswith('.') or re.search(r'[\\/:\x00-\x1f]', name)
                            or not name.lower().endswith('.xlsx')):
                        raise HTTPException(400, '文件名必须是普通 XLSX 文件名，不能含路径')
                    content = await item.read()
                    total += len(content)
                    if total > MAX_UPLOAD:
                        raise HTTPException(413, '上传总量不能超过 20 MiB')
                    target = Path(temporary)/str(index)/name
                    target.parent.mkdir()
                    target.write_bytes(content)
                    if zipfile.is_zipfile(target):
                        with zipfile.ZipFile(target) as archive:
                            if len(archive.infolist())>2000 or sum(i.file_size for i in archive.infolist())>100*1024*1024:
                                raise HTTPException(413, '工作簿解压后过大')
                    paths.append(target)
                return summary(service.import_files(paths))

    @app.get('/api/batches')
    def batches():
        return [summary(item, errors.get(item['id']) or errors.get('_service')) for item in service.list_batches()]

    @app.get('/api/batches/{ident}')
    def status(ident: str):
        return summary(batch(ident), errors.get(ident) or errors.get('_service'))

    @app.get('/api/batches/{ident}/tasks')
    def tasks(ident: str, offset: int=0, limit: int=50):
        value = batch(ident)
        offset, limit = max(offset,0), min(max(limit,1),100)
        items = []
        for task in value['tasks'][offset:offset+limit]:
            item = {key:task[key] for key in ('id','school','url','relations','sources','state','error','quality')}
            item['rawtext_saved'] = False
            item['preview'] = None
            item['original_candidate'] = None
            if task['artifact'] and task['state'] not in {'pending','running','artifact_missing','program_error'}:
                try:
                    service.bound(task['artifact'])
                    record = json.loads((service.root/task['artifact']/'teachers.json').read_text(encoding='utf-8'))[0]
                    item['rawtext_saved'] = record.get('status') == 'text_saved'
                    fields = {key:record.get(key, '') for key in ('name','title','email')}
                    if task['quality']['eligible_for_workbook']:
                        item['preview'] = fields
                    else:
                        item['original_candidate'] = fields
                except (ValueError,OSError,KeyError,IndexError):
                    pass
            items.append(item)
        return {'total':len(value['tasks']), 'offset':offset, 'items':items}

    @app.get('/api/batches/{ident}/issues')
    def issues(ident: str, offset: int=0, limit: int=50):
        value = batch(ident)
        offset, limit = max(offset,0), min(max(limit,1),100)
        # Original absolute temp paths are never needed by the browser.
        return {'total':len(value['issues']), 'offset':offset,
            'items':[{k:v for k,v in issue.items() if k != 'path'} for issue in value['issues'][offset:offset+limit]]}

    @app.post('/api/batches/{ident}/start')
    def start(ident: str, options: StartOptions):
        current = batch(ident)
        if current['queued']:
            raise HTTPException(409, '批次已有运行意图；请使用继续处理')
        if options.mode not in {'cache','live'}:
            raise HTTPException(400, '请选择严格缓存或在线访问')
        setting = options.model_dump(exclude={'mode','cache_id'}) | {'live':options.mode=='live'}
        if blocked := policy_error(setting):
            raise HTTPException(403, blocked)
        cache = None
        if options.mode == 'cache':
            cache = caches.get(options.cache_id)
            if cache is None:
                raise HTTPException(400, '缓存尚未准备；请先载入或下载离线示例，自己的输入可选择配置的本地缓存或在线访问')
        result = service.enqueue(ident, cache_manifest=cache, **setting)
        errors.pop(ident, None)
        return summary(result)

    @app.post('/api/batches/{ident}/pause')
    def pause(ident: str):
        batch(ident)
        return summary(service.pause(ident))

    @app.post('/api/batches/{ident}/resume')
    def resume(ident: str):
        current = batch(ident)
        if not current['queued']:
            raise HTTPException(409, '批次尚未开始或已经结束')
        if blocked := policy_error(current['run_options']):
            raise HTTPException(403, blocked)
        return summary(service.resume(ident))

    @app.post('/api/batches/{ident}/exports')
    def exports(ident: str):
        batch(ident)
        result = service.export(ident)
        return {'exports':[{'school':item['school'], 'records':item['records'],
            'zip_url':f'/api/batches/{ident}/downloads/{Path(item["path"]).stem}/zip',
            'xlsx_url':f'/api/batches/{ident}/downloads/{Path(item["path"]).stem}/xlsx'} for item in result['exports']]}

    @app.get('/api/batches/{ident}/downloads/{token}/{kind}')
    def download(ident: str, token: str, kind: str):
        batch(ident)
        if not re.fullmatch('[0-9a-f]{32}', token) or kind not in {'zip','xlsx'}:
            raise HTTPException(404, '未知下载')
        folder = service.root/'exports'/ident
        target = folder/(token+'.zip') if kind == 'zip' else folder/token/'teachers.xlsx'
        if not target.is_file() or not target.resolve().is_relative_to(folder.resolve()):
            raise HTTPException(404, '下载不属于此批次或尚未生成')
        return FileResponse(target, filename=f'Mission-C-大学结果.{kind}')

    return app
