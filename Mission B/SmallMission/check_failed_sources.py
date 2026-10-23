"""Bounded recheck of the user's seven failed source pages (no profile fetches)."""
import asyncio
from datetime import datetime
import json
from pathlib import Path
import os

from audit import Fetcher, ROOT, read_source, sha, write_json

PRIOR = Path(r'D:\Agent Workspace\MissionB-Windows-x64-v2.2.0\data\runs\47da2bbb093445a9a648ee4feafc9ef3\output')


async def main():
    os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(ROOT / '.portable-browser')
    out = ROOT / 'outputs' / ('access-recheck-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    out.mkdir()
    config = json.loads((ROOT / 'source_plans.json').read_text('utf-8'))
    results = []
    async with Fetcher(out) as fetcher:
        for college in json.loads((PRIOR / 'results.json').read_text('utf-8')):
            for source in college['sources']:
                if source['failure_kind'] != 'access':
                    continue
                url = source['roster_url']
                task = {'id': sha('\n'.join((college['school'], college['college'], url)).encode())[:12], 'roster_url': url}
                result = await read_source(fetcher, task, config, None, [url], follow_pagination=True)
                results.append(result)
                write_json(out / 'sources.json', results)
                print(json.dumps({'url': url, 'complete': result['parsed']['complete'],
                                  'title': result['parsed']['title'], 'status': result['attempts'][-1].get('status'),
                                  'failure': result['failure_kind'], 'out': str(out)}, ensure_ascii=False), flush=True)
                await asyncio.sleep(5)


if __name__ == '__main__':
    asyncio.run(main())
