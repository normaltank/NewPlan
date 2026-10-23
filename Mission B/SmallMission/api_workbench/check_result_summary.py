"""Download the real export from the app and compare all rendered summary cells."""
import asyncio
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import threading

from openpyxl import load_workbook
from playwright.async_api import async_playwright, expect

from app import make_server, brief, atomic_json
from reporting import export, SUMMARY_SCHEMA, SUMMARY_HEADERS
from runtime_paths import APP_ROOT
from test_result_summary import sample_results, sample_manifest


async def main():
    out = APP_ROOT / 'validation' / ('summary-ui-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    out.mkdir(parents=True)
    identifier = '2' * 32
    directory = out / 'data' / 'runs' / identifier / 'output'
    directory.mkdir(parents=True)
    results, manifest = sample_results(), sample_manifest()
    export(directory, results, manifest)
    atomic_json(directory / 'results.json', results)
    atomic_json(directory / 'manifest.json', manifest)
    job = {'id': identifier, 'created': datetime.now().astimezone().isoformat(), 'status': 'completed',
           'completed': len(results), 'total': len(results), 'message': '核验完成 · 输出格式测试样本',
           'results': [brief(r) for r in results], 'summary_available': True, 'summary_schema': SUMMARY_SCHEMA}
    atomic_json(directory.parent / 'job.json', job)
    # Saved files must remain byte-identical while loading history, viewing and downloading.
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.parent.rglob('*') if p.is_file()}
    server = make_server(out / 'data')
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(APP_ROOT.parent / '.portable-browser')
    errors = []
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page(viewport={'width': 1440, 'height': 1200}, device_scale_factor=1)
            page.on('pageerror', lambda e: errors.append(str(e)))
            await page.goto(f'http://127.0.0.1:{server.server_port}/#token={server.token}')
            await expect(page.locator('#version')).to_contain_text('VERSION')
            await page.locator('[data-view="history"]').click()
            await page.locator('.history-card').click()
            await page.locator('#result-table table').wait_for()
            await expect(page.locator('#result-table tbody tr')).to_have_count(7)
            headers = await page.locator('#result-table th').all_text_contents()
            rows = [await row.locator('td').all_text_contents() for row in await page.locator('#result-table tbody tr').all()]
            assert headers == SUMMARY_HEADERS
            assert [r[2] for r in rows] == ['正确', '错误'] + ['特殊情况'] * 5
            assert rows[-1][3] == ''
            await page.screenshot(path=str(out / '核验结果截图.png'), full_page=True)
            async with page.expect_download() as event:
                await page.locator('#download-summary').click()
            download = await event.value
            await download.save_as(out / 'MissionB_四列核验汇总_示例.xlsx')
            wb = load_workbook(out / 'MissionB_四列核验汇总_示例.xlsx', read_only=True, data_only=True)
            exported = [[v if v is not None else '' for v in row] for row in wb.active.values]
            wb.close()
            assert exported == [headers] + rows
            # Details still show the same-count wrong URL, its repair and original evidence.
            await page.locator('#result-table tbody tr').nth(1).click()
            await expect(page.locator('#college-content')).to_contain_text('移出范围外链接')
            await expect(page.locator('#college-content')).to_contain_text('补入缺少链接')
            await page.screenshot(path=str(out / '逐链接差异截图.png'), full_page=True)
            await page.locator('#close-college').click()
            await page.locator('#result-table tbody tr').last.click()
            await expect(page.locator('#college-content')).to_contain_text('特殊情况')
            await expect(page.locator('#college-content')).to_contain_text('未判定，原样保留')
            await page.locator('#close-college').click()
            await page.set_viewport_size({'width': 760, 'height': 1000})
            assert await page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
            await page.screenshot(path=str(out / '窄屏结果截图.png'), full_page=True)
            await browser.close()
        assert not errors, errors
        assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == digest for p, digest in before.items())
        report = {'status': 'passed', 'sample_kind': '隔离测试样本，经真实解析/逐链接比较/导出流程生成；未访问学校网站',
                  'three_categories': True, 'empty_special_note': True, 'ui_matches_download_every_cell': True,
                  'same_count_different_urls_remains_error': True, 'details_retained': True,
                  'history_files_unchanged': True, 'narrow_layout': True, 'real_api_calls': 0, 'browser_errors': errors,
                  'headers': headers, 'rows': rows}
        atomic_json(out / 'verification.json', report)
        print(json.dumps({'output': str(out), **report}, ensure_ascii=False))
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


if __name__ == '__main__':
    asyncio.run(main())
