"""Read already captured eligible pages while the large live case continues."""
import asyncio
import json
from pathlib import Path
import time
from fetch_client import FetchClient, save

ROOT = Path(__file__).resolve().parent


def read(path, default=None):
    try:
        return json.loads(path.read_text(encoding='utf8'))
    except (FileNotFoundError, ValueError):
        return default


async def main():
    client = FetchClient(ROOT/'fetch-api', max_calls=1500, timeout=60)
    seen = set()
    started = time.monotonic()
    semaphore = asyncio.Semaphore(4)
    async def fetch(page):
        async with semaphore:
            result = await client.fetch(page['url'])
        return {'url':page['url'],'status':result['status']}
    try:
        while time.monotonic()-started < 3600:
            pointer = read(ROOT/'runs/seu/continued-pointer.json', {})
            source = Path(pointer.get('run_dir', str(ROOT/'missing')))
            pages = read(source/'pages.json', [])
            new = [p for p in pages if p['url'] not in seen]
            seen.update(p['url'] for p in new)
            eligible = [p for p in new if p.get('status',0)<400 and
                        p.get('body_status') not in ('permission_denied','redirect_out_of_scope')]
            await asyncio.gather(*(fetch(p) for p in eligible))
            save(ROOT/'prefetch-progress.json',{'case':'seu','captured_seen':len(seen),
                 'ledger_calls':len(client.calls),'run_dir':str(source)})
            final = read(ROOT/'runs/seu/capture-result.json', {})
            if final.get('state')=='captured' and final.get('run_dir')==str(source):
                finished_pages = read(source/'pages.json', [])
                if all(p['url'] in seen for p in finished_pages):
                    print(json.dumps({'state':'prefetched','pages':len(seen),'calls':len(client.calls)}),flush=True)
                    return
            await asyncio.sleep(3)
        raise TimeoutError('Experiment prefetch wait limit reached')
    finally:
        await client.close()


if __name__ == '__main__':
    asyncio.run(main())
