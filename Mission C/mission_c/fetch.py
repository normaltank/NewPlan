"""Bounded HTTP reads; robots rules apply at every redirect and attachment."""
import time
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

USER_AGENT = "MissionC/1.0"
MAX_BYTES = 20 * 1024 * 1024


class SourceError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def valid_url(value):
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        raise ValueError("URL 必须是没有内嵌凭据的 http/https 地址")
    return value


class Fetcher:
    def __init__(self, timeout=30, delay=0.5):
        self.client = httpx.Client(timeout=timeout, trust_env=False, follow_redirects=False,
                                   headers={"User-Agent": USER_AGENT})
        self.delay = delay
        self.last_request = 0
        self.robots = {}

    def close(self):
        self.client.close()

    def _request(self, url, max_bytes):
        time.sleep(max(0, self.last_request + self.delay - time.monotonic()))
        self.last_request = time.monotonic()
        try:
            with self.client.stream("GET", url) as response:
                if response.status_code >= 400:
                    raise SourceError(f"http_{response.status_code}", f"HTTP {response.status_code}")
                chunks, total = [], 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise SourceError("response_too_large", f"响应超过 {max_bytes} 字节，未将截断内容视为全文")
                    chunks.append(chunk)
                return b"".join(chunks), response
        except httpx.HTTPError as error:
            raise SourceError("network_error", type(error).__name__) from error

    def check_robots(self, url):
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self.robots:
            try:
                data, response = self._request(origin + "/robots.txt", 1024 * 1024)
                if response.is_redirect:
                    raise SourceError("robots_unavailable", "robots.txt 跳转，需人工核实规则")
                rules = RobotFileParser()
                rules.parse(data.decode("utf-8", errors="replace").splitlines())
                self.robots[origin] = rules
            except SourceError as error:
                if error.code in {"http_404", "http_410"}:
                    self.robots[origin] = None
                else:
                    raise SourceError("robots_unavailable", "无法确认 robots.txt 访问规则") from error
        rules = self.robots[origin]
        if rules and not rules.can_fetch(USER_AGENT, url):
            raise SourceError("robots_disallowed", "robots.txt 不允许读取此 URL")

    def get(self, url, allowed_host=None):
        for _ in range(6):
            valid_url(url)
            if allowed_host and urlsplit(url).netloc != allowed_host:
                raise SourceError("external_attachment", "附件跨主机，保留链接待人工核实")
            self.check_robots(url)
            data, response = self._request(url, MAX_BYTES)
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise SourceError("redirect_without_location", "跳转没有目标地址")
                url = urljoin(url, location)
                continue
            return data, {"final_url": str(response.url), "http_status": response.status_code,
                          "content_type": response.headers.get("content-type", "")}
        raise SourceError("redirect_limit", "跳转超过 5 次")
