"""Verify the configured remote MCP without logging credentials or touching collection data."""
import argparse
import datetime as dt
import hashlib
import json
import pathlib
import subprocess
import time
import tomllib
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
WORKSPACE = ROOT.parent.parent
CONFIG = WORKSPACE / '.codex/config.toml'
SAMPLE = 'https://civil.seu.edu.cn/dxp/list.htm'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError('Unexpected MCP redirect; credentials not forwarded.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--read', action='store_true')
    args = parser.parse_args()
    config = tomllib.loads(CONFIG.read_text(encoding='utf-8'))['mcp_servers']['jina_test']
    assert config['url'].startswith('https://mcp.jina.ai/v1?')
    helper = subprocess.run(config['http_headers_helper'], capture_output=True, timeout=20,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    if helper.returncode:
        raise RuntimeError('Credential helper failed; its output was not logged.')
    headers = json.loads(helper.stdout.decode('utf-8-sig'))
    token = headers.get('Authorization', '').removeprefix('Bearer ')
    assert token.startswith('jina_')
    assert not helper.stderr, 'Credential helper emitted stderr.'
    headers.update({'Accept': 'application/json, text/event-stream', 'Content-Type': 'application/json'})
    opener = urllib.request.build_opener(NoRedirect())
    exchanges = []

    def save(name, data):
        text = json.dumps(data, ensure_ascii=False, indent=2)
        if token in text:
            raise RuntimeError('Credential unexpectedly present in response; output suppressed.')
        (ROOT / name).write_text(text, encoding='utf-8')

    def rpc(method, params, request_id=None):
        payload = {'jsonrpc': '2.0', 'method': method, 'params': params}
        if request_id is not None:
            payload['id'] = request_id
        request = urllib.request.Request(config['url'], data=json.dumps(payload).encode('utf-8'),
                                         headers=headers, method='POST')
        started = time.monotonic()
        with opener.open(request, timeout=100) as response:
            session = response.headers.get('Mcp-Session-Id')
            if session:
                headers['Mcp-Session-Id'] = session
            entry = {'method': method, 'status': response.status}
            if response.status == 202 or request_id is None:
                result = None
            elif 'text/event-stream' in response.headers.get('Content-Type', ''):
                event = []
                result = None
                size = 0
                for raw_line in response:
                    size += len(raw_line)
                    if size > 10_000_000:
                        raise RuntimeError('Unexpected oversized MCP response.')
                    line = raw_line.decode('utf-8').rstrip('\r\n')
                    if line.startswith('data:'):
                        event.append(line[5:].lstrip())
                    elif not line and event:
                        message = json.loads('\n'.join(event))
                        event = []
                        if message.get('id') == request_id:
                            result = message
                            break
                if result is None:
                    raise RuntimeError('MCP stream ended without the requested response.')
            else:
                result = json.loads(response.read(10_000_000).decode('utf-8'))
            entry['elapsed_seconds'] = round(time.monotonic() - started, 3)
            exchanges.append(entry)
            if result and 'error' in result:
                save('rpc-error.json', result)
                raise RuntimeError('MCP returned an error; see redacted evidence.')
            return result

    initialized = rpc('initialize', {'protocolVersion': '2025-03-26', 'capabilities': {},
                                     'clientInfo': {'name': 'NewPlan-isolated-jina-probe', 'version': '1.0.0'}}, 1)
    save('initialize.json', initialized)
    headers['MCP-Protocol-Version'] = initialized['result']['protocolVersion']
    rpc('notifications/initialized', {})
    listed = rpc('tools/list', {}, 2)
    save('tools.json', listed)
    tool_names = [t['name'] for t in listed['result']['tools']]
    assert set(tool_names) == {'read_url', 'search_web'}, tool_names
    summary = {'time_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
               'configured_server': 'jina_test', 'credential_helper_valid': True,
               'server_info': initialized['result']['serverInfo'], 'tools': tool_names,
               'content_calls': 0, 'exchanges': exchanges}
    if args.read:
        tool = next(t for t in listed['result']['tools'] if t['name'] == 'read_url')
        properties = tool['inputSchema']['properties']
        url_schema = properties.get('url', {})
        choices = url_schema.get('anyOf', [url_schema])
        assert any(choice.get('type') == 'string' for choice in choices), properties
        with (ROOT / 'read-attempt.json').open('x', encoding='utf-8') as marker:
            json.dump({'url': SAMPLE, 'tool': 'read_url', 'time_utc': summary['time_utc']}, marker)
        result = rpc('tools/call', {'name': 'read_url', 'arguments': {'url': SAMPLE}}, 3)
        save('read-result.json', result)
        body = '\n'.join(c.get('text', '') for c in result['result'].get('content', []) if c['type'] == 'text')
        checks = {'not_tool_error': not result['result'].get('isError', False),
                  'name_found': '邓小鹏' in body, 'email_found': 'dxp@seu.edu.cn' in body}
        summary.update({'content_calls': 1, 'sample_url': SAMPLE, 'characters': len(body),
                        'checks': checks, 'result_sha256': hashlib.sha256(body.encode('utf-8')).hexdigest(),
                        'billing_tokens': None, 'billing_note': 'MCP response is retained; no account bill queried.'})
        save('verification.json', summary)
        assert all(checks.values()), checks
    else:
        save('connection.json', summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
