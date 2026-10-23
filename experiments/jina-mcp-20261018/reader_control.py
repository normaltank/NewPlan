"""One controlled Reader API request: same page/key, explicit full Markdown."""
import datetime as dt
import hashlib
import json
import subprocess
import time
import tomllib
import urllib.request

from probe import CONFIG, ROOT, SAMPLE, NoRedirect


def main():
    config = tomllib.loads(CONFIG.read_text(encoding='utf-8'))['mcp_servers']['jina_test']
    helper = subprocess.run(config['http_headers_helper'], capture_output=True, timeout=20,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    if helper.returncode or helper.stderr:
        raise RuntimeError('Credential helper failed; output suppressed.')
    headers = json.loads(helper.stdout.decode('utf-8-sig'))
    token = headers['Authorization'].removeprefix('Bearer ')
    headers.update({'Accept': 'application/json', 'Content-Type': 'application/json',
                    'X-Md-Link-Style': 'discarded', 'X-Retain-Images': 'none',
                    'X-Respond-With': 'markdown'})
    stamp = dt.datetime.now(dt.timezone.utc).isoformat()
    with (ROOT / 'reader-control-attempt.json').open('x', encoding='utf-8') as marker:
        json.dump({'url': SAMPLE, 'time_utc': stamp, 'content_calls': 1}, marker)
    started = time.monotonic()
    req = urllib.request.Request('https://r.jina.ai/', method='POST', headers=headers,
                                 data=json.dumps({'url': SAMPLE}).encode('utf-8'))
    with urllib.request.build_opener(NoRedirect()).open(req, timeout=100) as response:
        status = response.status
        body = response.read(10_000_000).decode('utf-8')
    if token in body:
        raise RuntimeError('Credential unexpectedly present in response; output suppressed.')
    result = json.loads(body)
    (ROOT / 'reader-control-result.json').write_text(body, encoding='utf-8')
    content = result.get('data', {}).get('content', '')
    summary = {'time_utc': stamp, 'http_status': status, 'content_calls': 1, 'sample_url': SAMPLE,
               'elapsed_seconds': round(time.monotonic() - started, 3),
               'characters': len(content), 'name_found': '邓小鹏' in content,
               'email_found': 'dxp@seu.edu.cn' in content,
               'usage': result.get('data', {}).get('usage', result.get('usage')),
               'response_sha256': hashlib.sha256(body.encode('utf-8')).hexdigest(),
               'changed_option': 'X-Respond-With: markdown', 'account_bill_queried': False}
    (ROOT / 'reader-control-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))
    assert summary['name_found'] and summary['email_found'], 'Reader control lost a known field.'


if __name__ == '__main__':
    main()
