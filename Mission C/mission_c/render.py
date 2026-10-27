"""Optional same-host browser rendering; no login, tab clicks or site traversal."""
import hashlib
import os
from urllib.parse import urlsplit

from .fetch import MAX_BYTES, SourceError


def render_page(url, folder, fetcher):
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as BrowserTimeout
    except ImportError as error:
        raise SourceError("browser_dependency_missing", "先安装 requirements-browser.txt") from error
    host = urlsplit(url).netloc
    blocked = []
    with sync_playwright() as playwright:
        options = {"headless": True}
        if os.name == "nt":
            options["channel"] = "msedge"
        try:
            browser = playwright.chromium.launch(**options)
        except Exception as error:
            raise SourceError("browser_unavailable", "Windows 需要 Edge；其他平台需安装 Playwright Chromium") from error
        try:
            context = browser.new_context(service_workers="block", accept_downloads=False)

            def route(request):
                target = request.request.url
                if urlsplit(target).netloc != host or request.request.resource_type in {"image", "media", "font"}:
                    blocked.append(target)
                    request.abort()
                    return
                try:
                    fetcher.check_robots(target)
                except SourceError:
                    blocked.append(target)
                    request.abort()
                    return
                request.continue_()

            context.route("**/*", route)
            page = context.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                try:
                    page.wait_for_load_state("networkidle", timeout=12000)
                except BrowserTimeout:
                    blocked.append("network_idle_timeout")
                data = page.content().encode("utf-8")
            except Exception as error:
                raise SourceError("browser_render_failed", type(error).__name__) from error
            if len(data) > MAX_BYTES:
                raise SourceError("render_too_large", "浏览器页面超过大小限制")
            path = folder / "rendered.html"
            path.write_bytes(data)
            return data, {"rendered_file": path.relative_to(folder.parent).as_posix(),
                          "rendered_sha256": hashlib.sha256(data).hexdigest(),
                          "rendered_url": page.url, "browser_blocked_requests": sorted(set(blocked))}
        finally:
            browser.close()
