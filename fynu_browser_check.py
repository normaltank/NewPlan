"""Compare ordinary browser rendering on one public and one restricted profile."""
import asyncio
import json
from pathlib import Path

from acquisition import save_page
from benchmark import ROOT, new_run, write_json
from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

CASES = [
    {'id':'public-control', 'url':'https://www.fynu.edu.cn/hxycl/info/1047/4751.htm',
     'selector':'.v_news_content a[href]', 'kind':'public profile control'},
    {'id':'restricted-profile', 'url':'https://www.fynu.edu.cn/hxycl/content.jsp?urltype=news.NewsContentUrl&wbtreeid=1049&wbnewsid=4178',
     'selector':'.v_news_content a[href]', 'kind':'permission-message comparison'},
]

async def main():
    import time
    out = new_run('fynu-browser-check')
    rows = []
    print(f'RUN_DIR={out}', flush=True)
    config=BrowserConfig(chrome_channel='msedge',channel='msedge',headless=True,
                         ignore_https_errors=False,verbose=False)
    async with AsyncWebCrawler(config=config,base_directory=str(ROOT/'.cache')) as crawler:
        for case in CASES:
            started=time.perf_counter()
            try:
                result=await asyncio.wait_for(crawler.arun(case['url'],config=CrawlerRunConfig(
                    check_robots_txt=True,cache_mode=CacheMode.BYPASS,wait_until='domcontentloaded',
                    page_timeout=30000,delay_before_return_html=2,verbose=False)),timeout=45)
                row=save_page(out,'crawl4ai-browser',case,result.html or '',result.status_code,
                              time.perf_counter()-started,error=result.error_message if not result.success else None,
                              loaded_url=result.redirected_url or result.url)
            except Exception as error:
                row=save_page(out,'crawl4ai-browser',case,'',None,time.perf_counter()-started,error=repr(error))
            rows.append(row)
            print(json.dumps(row,ensure_ascii=False),flush=True)
            await asyncio.sleep(2)
    write_json(out/'results.json',rows)

if __name__=='__main__':
    asyncio.run(main())
