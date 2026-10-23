"""Normal, isolated browser fallback. Never connects to the workbench browser."""
import asyncio
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from probe_sources import ROOT, inputs

def browser_executable():
    candidates = list((Path(os.environ.get('LOCALAPPDATA', '')) / 'ms-playwright').glob('chromium-*/chrome-win/chrome.exe'))
    return str(sorted(candidates)[-1]) if candidates else None

async def main():
    out = ROOT / 'evidence' / 'browser'
    out.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, executable_path=browser_executable())
        for t in inputs():
            if t['school'] not in ['南京理工大学', '安徽大学']:
                continue
            page = await browser.new_page(viewport={'width': 1440, 'height': 1100})
            key = hashlib.sha256(t['url'].encode()).hexdigest()[:16]
            meta = {k: v for k, v in t.items() if k != 'rows'}
            meta.update(key=key, captured_at=datetime.now(timezone.utc).isoformat())
            try:
                response = await page.goto(t['url'], wait_until='domcontentloaded', timeout=45000)
                await page.wait_for_timeout(5000)
                html = await page.content()
                (out / (key + '.html')).write_text(html, encoding='utf-8')
                await page.screenshot(path=str(out / (key + '.png')), full_page=True)
                soup = BeautifulSoup(html, 'lxml')
                meta.update(status=response.status if response else None, final_url=page.url,
                            title=await page.title(), bytes=len(html.encode()),
                            sha256=hashlib.sha256(html.encode()).hexdigest())
                links = [{'text': a.get_text(' ', strip=True), 'href': a['href'],
                          'ancestors': [p.name + ('#' + p['id'] if p.get('id') else '') +
                                        ('.' + '.'.join(p['class']) if p.get('class') else '')
                                        for p in list(a.parents)[:6] if p.name]}
                         for a in soup.select('a[href]')]
                (out / (key + '.links.json')).write_text(json.dumps(links, ensure_ascii=False, indent=2), encoding='utf-8')
            except Exception as e:
                meta['error'] = type(e).__name__ + ': ' + str(e)
            (out / (key + '.json')).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(meta, ensure_ascii=False), flush=True)
            await page.close()
        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
