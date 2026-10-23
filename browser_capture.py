"""Bounded same-host rendering for rosters whose content is absent from HTTP HTML."""
import hashlib
from urllib.parse import urlparse
from bs4 import BeautifulSoup


async def render_roster(url, folder):
    from playwright.async_api import async_playwright
    import os
    async with async_playwright() as pw:
        options={'headless':True}
        if os.name=='nt':
            options['channel']='msedge'
        browser=await pw.chromium.launch(**options)
        try:
            page=await browser.new_page()
            host=urlparse(url).netloc
            async def route(request):
                if urlparse(request.request.url).netloc!=host or request.request.resource_type in ('image','media','font'):
                    await request.abort()
                else:
                    await request.continue_()
            await page.route('**/*',route)
            await page.goto(url,wait_until='domcontentloaded',timeout=45000)
            try:
                await page.wait_for_load_state('networkidle',timeout=12000)
            except Exception:
                pass
            html=await page.content()
            (folder/'rendered.html').write_bytes(html.encode('utf-8'))
            soup=BeautifulSoup(html,'lxml')
            (folder/'rendered-text.txt').write_text(soup.get_text('\n',strip=True),encoding='utf-8')
            return soup,{'rendered_sha256':hashlib.sha256(html.encode()).hexdigest(),
                         'rendered_url':page.url,'rendered_chars':len(html)}
        finally:
            await browser.close()
