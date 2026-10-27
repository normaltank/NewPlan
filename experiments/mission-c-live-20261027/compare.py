"""Bounded five-homepage comparison. Completed artifacts are reused on resume."""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "Mission C"))
from mission_c.extract import extract_html
from mission_c.fetch import Fetcher

OUT = Path(r"D:\Agent Workspace\Intern\MyPlan\OpenSource\Mission C\outputs\live-tools-20261027")
SAMPLES = [
    {"id": "lzjtu", "url": "https://jtys.lzjtu.edu.cn/info/1113/4365.htm", "name": ""},
    {"id": "suda", "url": "https://web.suda.edu.cn/hj1/", "name": "何剑"},
    {"id": "ncepu", "url": "https://electric.ncepu.edu.cn/szdw/jsxx/gdyyjyjsyjs/a207300faea944298a27ba0a6d0c6c7b.htm", "name": "王健"},
    {"id": "shu", "url": "https://physics.shu.edu.cn/info/1082/5653.htm", "name": "张惠芳"},
    {"id": "ecnu", "url": "https://faculty.ecnu.edu.cn/_s41/lyq2/main.psp", "name": "李艳青"},
]


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def artifact(method, sample):
    folder = OUT / method / sample["id"]
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def finish(method, sample, data=None, **metadata):
    folder = artifact(method, sample)
    row = {"method": method, "url": sample["url"], "observed_at": datetime.now(timezone.utc).isoformat(), **metadata}
    if data is not None:
        if isinstance(data, str):
            data = data.encode("utf-8")
        (folder / "source.html").write_bytes(data)
        row.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
        if int(metadata.get("http_status") or 200) < 400:
            parsed = extract_html(data, sample["url"])
            for key, file in (("page_text", "page.txt"), ("content_html", "content.html"), ("biography", "biography.txt")):
                (folder / file).write_text(parsed[key], encoding="utf-8")
            parsed.pop("page_text")
            parsed.pop("content_html")
            row.update(parsed)
    row["text_saved"] = bool(row.get("biography"))
    save(folder / "result.json", row)
    print(json.dumps({"method": method, "id": sample["id"], "text_saved": row["text_saved"],
                      "name": row.get("name"), "characters": len(row.get("biography", "")),
                      "http_status": row.get("http_status"), "error": row.get("error")}, ensure_ascii=False), flush=True)
    return row


def done(method, sample):
    return (artifact(method, sample) / "result.json").exists()


def baseline():
    for sample in SAMPLES:
        if done("baseline", sample):
            continue
        folder = artifact("baseline", sample)
        if sample["id"] == "lzjtu":
            result = OUT.parent / "real-test-20261027-lzjtu-baseline-7a544cd" / "teachers.json"
        else:
            result = folder / "cli" / "teachers.json"
            if not result.exists():
                if (folder / "cli").exists():
                    finish("baseline", sample, error="cli_failed_before_record",
                           saved_source="cli/0001/source.html", original_run_preserved=True)
                    continue
                run = subprocess.run([sys.executable, str(ROOT / "Mission C" / "collect.py"),
                                      "--url", sample["url"], "--output", str(folder / "cli")],
                                     timeout=90, check=False, capture_output=True, text=True, encoding="utf-8")
                (folder / "stdout.txt").write_text(run.stdout, encoding="utf-8")
                (folder / "stderr.txt").write_text(run.stderr, encoding="utf-8")
                if not result.exists():
                    finish("baseline", sample, error="cli_failed_before_record", exit_code=run.returncode)
                    continue
        row = json.loads(result.read_text(encoding="utf-8"))[0]
        save(folder / "result.json", {"method": "baseline", **row, "text_saved": bool(row.get("biography"))})
        print(json.dumps({"method": "baseline", "id": sample["id"], "name": row.get("name"),
                          "characters": len(row.get("biography", "")), "error": row.get("error")}, ensure_ascii=False), flush=True)


def browser():
    from playwright.sync_api import sync_playwright, TimeoutError as BrowserTimeout
    fetcher = Fetcher()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, channel="msedge")
            try:
                for sample in SAMPLES:
                    if done("browser", sample):
                        continue
                    fetcher.check_robots(sample["url"])
                    context = browser.new_context(service_workers="block", accept_downloads=False)
                    page = context.new_page()
                    try:
                        response = page.goto(sample["url"], wait_until="domcontentloaded", timeout=30000)
                        try:
                            page.wait_for_load_state("networkidle", timeout=8000)
                        except BrowserTimeout:
                            pass
                        finish("browser", sample, page.content(), http_status=response.status if response else None,
                               final_url=page.url, browser="Edge, normal headless, no stealth", page_title=page.title())
                    except Exception as error:
                        finish("browser", sample, error=type(error).__name__)
                    finally:
                        context.close()
                    time.sleep(1)
            finally:
                browser.close()
    finally:
        fetcher.close()


async def crawl4ai():
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
    from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
    config = BrowserConfig(chrome_channel="msedge", headless=True, ignore_https_errors=False,
                           enable_stealth=False, verbose=False)
    run = CrawlerRunConfig(check_robots_txt=True, cache_mode=CacheMode.BYPASS, max_retries=0,
                           page_timeout=30000, delay_before_return_html=1, word_count_threshold=1,
                           simulate_user=False, override_navigator=False, magic=False,
                           markdown_generator=DefaultMarkdownGenerator(content_source="raw_html", content_filter=None),
                           verbose=False)
    async with AsyncWebCrawler(config=config, base_directory=str(OUT / "crawl4ai-cache")) as crawler:
        for sample in SAMPLES:
            if done("crawl4ai", sample):
                continue
            try:
                result = await asyncio.wait_for(crawler.arun(sample["url"], config=run), timeout=50)
                folder = artifact("crawl4ai", sample)
                raw_markdown = getattr(result.markdown, "raw_markdown", "") or ""
                (folder / "raw-markdown.txt").write_text(raw_markdown, encoding="utf-8")
                (folder / "cleaned.html").write_text(result.cleaned_html or "", encoding="utf-8")
                finish("crawl4ai", sample, result.html or "", http_status=result.status_code,
                       tool_success=result.success, error=result.error_message or None,
                       markdown_chars=len(raw_markdown), markdown_content_source="raw_html", content_filter=None)
            except Exception as error:
                finish("crawl4ai", sample, error=type(error).__name__)
            await asyncio.sleep(1)


async def crawlee():
    from crawlee import ConcurrencySettings, service_locator
    from crawlee.configuration import Configuration
    from crawlee.crawlers import BeautifulSoupCrawler
    from crawlee.events import LocalEventManager
    from crawlee.storage_clients import FileSystemStorageClient
    from compatible_http import CompatibleHttpClient
    pending = [sample for sample in SAMPLES if not done("crawlee", sample)]
    if not pending:
        return
    config = Configuration(storage_dir=str(OUT / "crawlee-storage"), purge_on_start=False, log_level="WARNING")
    storage = FileSystemStorageClient()
    events = LocalEventManager()
    service_locator.set_configuration(config)
    service_locator.set_storage_client(storage)
    service_locator.set_event_manager(events)
    crawler = BeautifulSoupCrawler(
        http_client=CompatibleHttpClient(), configuration=config, storage_client=storage, event_manager=events,
        concurrency_settings=ConcurrencySettings(min_concurrency=1, desired_concurrency=1, max_concurrency=1),
        max_requests_per_crawl=len(pending), max_request_retries=0, max_session_rotations=0,
        retry_on_blocked=False, use_session_pool=False, respect_robots_txt_file=True,
        request_handler_timeout=timedelta(seconds=30), ignore_http_error_status_codes=range(400, 600))
    by_url = {sample["url"]: sample for sample in pending}

    @crawler.pre_navigation_hook
    async def pace(context):
        await asyncio.sleep(1)

    @crawler.router.default_handler
    async def handle(context):
        data = await context.http_response.read()
        finish("crawlee", by_url[context.request.url], data,
               http_status=context.http_response.status_code, final_url=context.request.loaded_url)

    @crawler.failed_request_handler
    async def failure(context, error):
        finish("crawlee", by_url[context.request.url], error=type(error).__name__)

    @crawler.on_skipped_request
    async def skipped(url, reason):
        if str(url) in by_url:
            finish("crawlee", by_url[str(url)], error=str(reason))

    await crawler.run([sample["url"] for sample in pending])


def trafilatura():
    import trafilatura as extractor
    for sample in SAMPLES:
        if done("trafilatura", sample):
            continue
        inputs = [artifact("browser", sample) / "source.html",
                  artifact("baseline", sample) / "cli" / "0001" / "source.html"]
        source = next((path for path in inputs if path.exists() and len(path.read_bytes()) > 100), None)
        if source is None:
            finish("trafilatura", sample, error="no_saved_successful_html")
            continue
        raw = source.read_bytes()
        value = extractor.extract(raw, favor_recall=True, include_tables=True, include_links=True) or ""
        folder = artifact("trafilatura", sample)
        (folder / "extracted.txt").write_text(value, encoding="utf-8")
        row = finish("trafilatura", sample, raw, source_reused=str(source.relative_to(OUT)),
                     extraction_chars=len(value), options={"favor_recall": True, "include_tables": True, "include_links": True})
        row["tool_text"] = value
        save(folder / "result.json", row)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("method", choices=["baseline", "browser", "crawl4ai", "crawlee", "trafilatura"])
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    save(OUT / "samples.json", SAMPLES)
    versions = {package: importlib.metadata.version(package) for package in
                ["httpx", "beautifulsoup4", "playwright", "crawl4ai", "crawlee", "trafilatura"]}
    save(OUT / "versions.json", versions)
    action = globals()[args.method]
    if asyncio.iscoroutinefunction(action):
        asyncio.run(action())
    else:
        action()


if __name__ == "__main__":
    main()
