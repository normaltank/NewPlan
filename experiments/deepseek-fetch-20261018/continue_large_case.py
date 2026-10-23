"""Complete the large case from its checkpoint, without changing frozen sources.

Only this experiment's request concurrency is raised to three, with a shared
1.1 s navigation gate. Robots, request handling, extraction and retries remain
those of the snapshot. The interrupted segment remains as separate evidence.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'runtime'))
import api_pilot
import fynu_probe


async def main():
    folder = ROOT / 'runs/seu'
    original = json.loads((folder / 'capture-result.json').read_text(encoding='utf8'))
    if not (folder / 'initial-segment.json').exists():
        (folder / 'initial-segment.json').write_text(json.dumps(original,ensure_ascii=False,indent=2),encoding='utf8')
    source = original['run_dir']
    # The original serial run was stopped after saving its queue. This is an
    # explicit continuation, never a retry of already processed failed pages.
    original_settings = fynu_probe.ConcurrencySettings
    fynu_probe.ConcurrencySettings = lambda **_: original_settings(
        min_concurrency=1, desired_concurrency=3, max_concurrency=3)
    original_factory = api_pilot.make_crawler
    navigation_lock = asyncio.Lock()
    last = 0.0
    async def factory(*args, **kwargs):
        crawler = await original_factory(*args, **kwargs)
        @crawler.pre_navigation_hook
        async def experiment_rate(context):
            nonlocal last
            async with navigation_lock:
                delay = 1.1 - (time.monotonic()-last)
                if delay > 0:
                    await asyncio.sleep(delay)
                last = time.monotonic()
        return crawler
    api_pilot.make_crawler = factory
    pointer = folder / 'continued-pointer.json'
    args = argparse.Namespace(university='东南大学',college='吴健雄学院',
        url='https://wjx.seu.edu.cn/',entries=['https://wjx.seu.edu.cn/xyds/list.htm'],
        model=api_pilot.DEFAULT_MODEL,max_pages=1200,max_calls=45,max_images=500,
        ocr=True,browser=True,pointer=str(pointer),resume_from=source,
        prioritize=['https://me.seu.edu.cn/cxl/list.htm',
            'https://me.seu.edu.cn/cz_31654/list.htm','https://civil.seu.edu.cn/dxp/list.htm'])
    started = datetime.now(timezone.utc).isoformat()
    await api_pilot.main(args)
    run_dir = json.loads(pointer.read_text(encoding='utf8'))['run_dir']
    summary = json.loads((Path(run_dir)/'summary.json').read_text(encoding='utf8'))
    final = dict(original, state='captured',return_code=0,run_dir=run_dir,summary=summary,
        finished=datetime.now(timezone.utc).isoformat(),continuation_started=started,
        previous_segment=source,experiment_concurrency=3,
        minimum_navigation_interval_seconds=1.1,
        note='Complete saved queue; initial segment and continuation token usage must be added separately.')
    (folder/'capture-result.json').write_text(json.dumps(final,ensure_ascii=False,indent=2),encoding='utf8')
    state = json.loads((ROOT/'run-status.json').read_text(encoding='utf8'))
    state['seu'] = final
    (ROOT/'run-status.json').write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'state':'captured','case':'seu','summary':summary},ensure_ascii=False),flush=True)


if __name__ == '__main__':
    asyncio.run(main())
