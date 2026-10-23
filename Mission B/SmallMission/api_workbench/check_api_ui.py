"""Browser acceptance: API settings, mixed imports, evidence, cache and exports."""
import asyncio
from datetime import datetime
import json
import os
import threading
from unittest.mock import patch
from playwright.async_api import async_playwright,expect
from openpyxl import load_workbook
from app import make_server
from audit import Fetcher
from runtime_paths import APP_ROOT
from test_multisource import paired_file
from test_api_engine import FakeClient

class Client(FakeClient):
    def __init__(self,*args,max_calls=200,**kwargs):super().__init__();self.max_calls=max_calls

async def main():
    out=APP_ROOT/'validation'/('ui-'+datetime.now().strftime('%Y%m%d-%H%M%S'));out.mkdir(parents=True)
    upload=out/'双表输入.xlsx'
    paired_file(upload,'测试大学','第二学院',['https://example.edu.cn/staff2.htm'],['https://example.edu.cn/a'])
    async def fetch(fetcher,task):
        html='<title>名单</title><nav><a href="/news">新闻</a></nav><div class="roster"><a href="/a">甲</a><a href="/b">乙</a></div>'
        meta={'requested_url':task['roster_url'],'final_url':task['roster_url'],'status':200,'method':'测试夹具','captured_at':'fixture'}
        fetcher.save(task['id'],'http',html,meta);return html,meta
    server=make_server(out/'data');thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    os.environ['PLAYWRIGHT_BROWSERS_PATH']=str(APP_ROOT.parent/'.portable-browser')
    errors=[]
    try:
        with patch('api_engine.DeepSeekJSON',Client),patch.object(Fetcher,'http',fetch):
            async with async_playwright() as pw:
                browser=await pw.chromium.launch(headless=True)
                page=await browser.new_page(viewport={'width':1440,'height':1050});page.on('pageerror',lambda e:errors.append(str(e)))
                await page.goto(f'http://127.0.0.1:{server.server_port}/#token={server.token}')
                await page.locator('[data-view="settings"]').click()
                await page.locator('#api-key').fill('fixture-key-not-a-real-credential')
                await page.locator('#api-limit').fill('10');await page.locator('#save-settings').click()
                await expect(page.locator('#key-status')).to_contain_text('已配置')
                assert await page.locator('#api-key').input_value()==''
                await page.screenshot(path=str(out/'settings.png'),full_page=True)
                await page.locator('[data-view="new"]').click()
                await page.locator('#paste').fill('学校\t学院\t师资url\t教师url\n测试大学\t第一学院\thttps://example.edu.cn/staff1.htm\thttps://example.edu.cn/a\n测试大学\t第一学院\thttps://example.edu.cn/staff1.htm\thttps://example.edu.cn/x')
                await page.locator('#files').set_input_files(upload)
                await page.locator('#preview-button').click();await page.locator('#preview-groups table').wait_for()
                await page.locator('#start-button').click();await page.locator('#downloads:not([hidden])').wait_for(timeout=30000)
                assert await page.locator('#result-table tbody tr').count()==2
                await expect(page.locator('#job-date')).to_contain_text('API 4 次')
                await page.screenshot(path=str(out/'result.png'),full_page=True)
                async with page.expect_download() as info:await page.locator('#download-summary').click()
                download=await info.value;await download.save_as(out/'summary.xlsx')
                wb=load_workbook(out/'summary.xlsx',read_only=True,data_only=True)
                rows=list(wb.active.values)
                assert rows[0]==('大学名','学院名','核验结果','特殊情况说明') and set(rows[1:])=={('测试大学','第一学院','错误',None),('测试大学','第二学院','错误',None)};wb.close()
                await page.locator('#result-table tbody tr').first.click()
                await page.locator('#college-panel:not([hidden])').wait_for()
                async with page.expect_popup() as info:await page.get_by_text('查看逐条证据',exact=True).click()
                proof=await info.value;await proof.wait_for_load_state()
                await expect(proof.locator('body')).to_contain_text('两次未计入');await proof.close()
                # Repeat imports: fresh source reading, identical compact pages use validated cache.
                await page.locator('[data-view="new"]').click()
                await page.locator('#start-button').click();await page.locator('#downloads:not([hidden])').wait_for(timeout=30000)
                await expect(page.locator('#job-date')).to_contain_text('API 0 次')
                await expect(page.locator('#job-date')).to_contain_text('复用 2 页')
                await page.set_viewport_size({'width':760,'height':1000})
                assert await page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
                await browser.close()
        assert not errors,errors
        report={'status':'passed','mode':'模拟API与网页，仅验证UI及流程','real_api_calls':0,
            'mixed_text_and_dual_sheet':True,'equal_count_different_url_detected':True,'evidence_popup':True,
            'repeat_uses_cache':True,'summary_download':True,'browser_errors':errors}
        (out/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
        print(json.dumps({'output':str(out),**report},ensure_ascii=False))
    finally:
        if server.store.worker:server.store.worker.join(timeout=15)
        server.shutdown();thread.join();server.server_close()

if __name__=='__main__':asyncio.run(main())
