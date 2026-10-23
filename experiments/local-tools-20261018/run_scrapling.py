"""Bounded public-page fetching, with separate static and browser arms."""
import argparse
import os
import time
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser
import requests
from common import ROOT, USER_AGENT, read, record, save

os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(ROOT/'.browsers-fetch')
from scrapling.fetchers import Fetcher, StealthyFetcher

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['http','browser'])
    parser.add_argument('--ids', nargs='*')
    args = parser.parse_args()
    arm = 'scrapling_'+args.mode
    session = requests.Session()
    session.trust_env = False
    session.headers['User-Agent'] = USER_AGENT
    policies = {}
    samples = read(ROOT/'samples.json')
    if args.ids:
        samples = [s for s in samples if s['id'] in args.ids]
    for s in samples:
        if (ROOT/'results'/arm/f"{s['id']}.json").exists():
            continue
        started = time.monotonic()
        origin = '{0.scheme}://{0.netloc}'.format(urlsplit(s['url']))
        if origin not in policies:
            rp = RobotFileParser()
            try:
                r = session.get(origin+'/robots.txt', timeout=15)
                if r.status_code == 200:
                    rp.parse(r.text.splitlines())
                elif r.status_code in (401,403):
                    rp.disallow_all = True
                else:
                    rp.allow_all = True
                policies[origin] = (rp, r.status_code)
                save(ROOT/'robots'/arm/(urlsplit(origin).netloc+'.json'), {'url':origin+'/robots.txt','status':r.status_code,'text':r.text[:100000]})
            except requests.RequestException as e:
                rp.allow_all = True
                policies[origin] = (rp, type(e).__name__)
                save(ROOT/'robots'/arm/(urlsplit(origin).netloc+'.json'), {'url':origin+'/robots.txt','error':type(e).__name__, 'policy':'No directive retrieved; fixed authorized public samples only.'})
        rp, robot_status = policies[origin]
        if not rp.can_fetch(USER_AGENT, s['url']):
            record(arm,s,started,error='robots_disallowed',extra={'robots_status':robot_status})
            continue
        try:
            if args.mode == 'http':
                page = Fetcher.get(s['url'], timeout=30, retries=0, headers={'User-Agent':USER_AGENT})
            else:
                page = StealthyFetcher.fetch(s['url'], headless=True, timeout=45000, wait=1000,
                    network_idle=False, solve_cloudflare=False, google_search=False,
                    disable_resources=False, block_ads=False, selector_config={'adaptive':False},
                    additional_args={'executable_path':os.environ['FACULTY_TEST_BROWSER']} if os.environ.get('FACULTY_TEST_BROWSER') else {})
            record(arm,s,started,raw=page.body,status=page.status,final_url=page.url,encoding=page.encoding,
                   extra={'robots_status':robot_status})
        except Exception as exc:
            record(arm,s,started,error=type(exc).__name__+': '+str(exc)[:300],extra={'robots_status':robot_status})
        time.sleep(1.2)

if __name__ == '__main__':
    main()
