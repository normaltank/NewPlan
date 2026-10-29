"""Bounded representative tools; raw framework text and shared field parser stay separate."""
import argparse
import asyncio
import importlib.metadata
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "mission-c-live-20261027"))
import compare

OUT = Path(r"D:\Agent Workspace\Intern\MyPlan\OpenSource\Mission C\outputs\diverse-pages-20261027")
REPRESENTATIVES = ["n02_zju_yingxiaoying", "n03_nju_zhouzh", "n05_dlut_xuchang",
                   "n12_chnu_baoxiangzhi", "n07_toronto_hinton"]


def browser():
    from playwright.sync_api import sync_playwright, TimeoutError as BrowserTimeout
    fetcher = compare.Fetcher(timeout=15)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, channel="msedge")
            try:
                for sample in compare.SAMPLES:
                    if compare.done("browser", sample):
                        continue
                    context = None
                    try:
                        fetcher.check_robots(sample["url"])
                        context = browser.new_context(service_workers="block", accept_downloads=False,
                                                      ignore_https_errors=False)
                        page = context.new_page()
                        response = page.goto(sample["url"], wait_until="domcontentloaded", timeout=30000)
                        try:
                            page.wait_for_load_state("networkidle", timeout=8000)
                        except BrowserTimeout:
                            pass
                        folder = compare.artifact("browser", sample)
                        (folder / "raw-visible.txt").write_text(page.locator("body").inner_text(), encoding="utf-8")
                        compare.finish("browser", sample, page.content(), http_status=response.status if response else None,
                                       final_url=page.url, page_title=page.title(),
                                       browser="Edge normal headless; no stealth; verified TLS", retries=0)
                    except Exception as error:
                        compare.finish("browser", sample, error=type(error).__name__, error_detail=str(error)[:500])
                    finally:
                        if context:
                            context.close()
                    time.sleep(1)
            finally:
                browser.close()
    finally:
        fetcher.close()


def trafilatura(samples):
    import trafilatura
    for sample in samples:
        source = OUT / "cohort" / sample["id"] / "cli/0001/source.html"
        if not source.exists() or compare.done("trafilatura", sample):
            continue
        raw = source.read_bytes()
        text = trafilatura.extract(raw, favor_recall=True, include_tables=True, include_links=True) or ""
        folder = compare.artifact("trafilatura", sample)
        (folder / "raw-extracted.txt").write_text(text, encoding="utf-8")
        compare.finish("trafilatura", sample, raw, source_reused=str(source),
                       raw_text_file="raw-extracted.txt", offline=True,
                       options={"favor_recall": True, "include_tables": True, "include_links": True},
                       field_parser="Mission C shared extract_html(source HTML), not Trafilatura field extraction")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("method", choices=["browser", "crawlee", "crawl4ai", "trafilatura"])
    args = parser.parse_args()
    all_samples = json.loads((HERE / "cohort.json").read_text(encoding="utf-8"))["samples"]
    compare.OUT = OUT
    compare.SAMPLES = [x for x in all_samples if x["id"] in REPRESENTATIVES]
    compare.save(OUT / "tool-parameters.json", {"representatives": REPRESENTATIVES,
        "TLS_verification": True, "stealth": False, "retries": 0,
        "timeout_seconds": {"browser_navigation": 30, "browser_networkidle": 8, "robots": 15,
                            "crawl4ai_outer": 50, "crawlee_handler": 30},
        "raw_vs_fields": "Framework raw text saved separately; all HTML fields use same Mission C parser",
        "cache": "existing result.json reused; Crawl4AI BYPASS only on first attempt",
        "versions": {p: importlib.metadata.version(p) for p in
                     ["httpx", "beautifulsoup4", "playwright", "crawl4ai", "crawlee", "trafilatura"]}})
    if args.method == "browser":
        browser()
    elif args.method == "trafilatura":
        trafilatura(all_samples)
    else:
        asyncio.run(getattr(compare, args.method)())


if __name__ == "__main__":
    main()
