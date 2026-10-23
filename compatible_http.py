"""Preserve verified HTTPS when the default TLS implementation cannot negotiate."""
import logging
from urllib.parse import urlparse
from crawlee.http_clients import ImpitHttpClient,HttpxHttpClient

class CompatibleHttpClient(ImpitHttpClient):
    def __init__(self):
        super().__init__()
        self.fallback=HttpxHttpClient(verify=True,header_generator=None,trust_env=False)
        self.compatible_hosts=set()

    async def _try(self,method,url,*args,**kwargs):
        host=urlparse(url).netloc
        if host in self.compatible_hosts:
            return await getattr(self.fallback,method)(*args,**kwargs)
        try:
            return await getattr(super(),method)(*args,**kwargs)
        except Exception as exc:
            if 'SelectedUnusableCipherSuiteForVersion' not in str(exc):raise
            logging.getLogger(__name__).warning('Default TLS negotiation incompatible for %s; retrying with certificate verification enabled',host)
            result=await getattr(self.fallback,method)(*args,**kwargs)
            self.compatible_hosts.add(host)
            return result

    async def crawl(self,request,**kwargs):
        return await self._try('crawl',request.url,request,**kwargs)

    async def send_request(self,url,**kwargs):
        return await self._try('send_request',url,url,**kwargs)

    async def cleanup(self):
        try:await super().cleanup()
        finally:await self.fallback.cleanup()
