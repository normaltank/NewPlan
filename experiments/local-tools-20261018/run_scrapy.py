"""Fixed URLs only; bounded native Scrapy HTTP test, no business-state writes."""
import time
import scrapy
from scrapy.crawler import CrawlerProcess
from common import ROOT, USER_AGENT, read, record, save

SAMPLES = read(ROOT/'samples.json')

class SampleSpider(scrapy.Spider):
    name = 'fixed_faculty_samples'
    custom_settings = {
        'USER_AGENT': USER_AGENT, 'CONCURRENT_REQUESTS':2, 'CONCURRENT_REQUESTS_PER_DOMAIN':1,
        'DOWNLOAD_DELAY':1.2, 'RANDOMIZE_DOWNLOAD_DELAY':False, 'DOWNLOAD_TIMEOUT':30,
        'RETRY_ENABLED':False, 'REDIRECT_MAX_TIMES':5, 'COOKIES_ENABLED':False,
        'ROBOTSTXT_OBEY':True, 'LOG_LEVEL':'WARNING', 'TELNETCONSOLE_ENABLED':False,
        'HTTPCACHE_ENABLED':False,
    }
    async def start(self):
        for sample in SAMPLES:
            if (ROOT/'results/scrapy_http'/f"{sample['id']}.json").exists():
                continue
            yield scrapy.Request(sample['url'], callback=self.parse, errback=self.failed,
                                 meta={'sample':sample, 'started':time.monotonic(), 'handle_httpstatus_all':True})
    def parse(self, response):
        record('scrapy_http', response.meta['sample'], response.meta['started'], raw=response.body,
               status=response.status, final_url=response.url, encoding=response.encoding)
    def failed(self, failure):
        req = failure.request
        record('scrapy_http', req.meta['sample'], req.meta['started'], error=type(failure.value).__name__+': '+str(failure.value)[:250])

if __name__ == '__main__':
    process = CrawlerProcess()
    crawler = process.create_crawler(SampleSpider)
    process.crawl(crawler)
    process.start()
    save(ROOT/'results/scrapy_http/stats.json', crawler.stats.get_stats())
