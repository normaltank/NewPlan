"""Bound cached source bytes to URL; provider evidence never impersonates origin HTML."""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import uuid

import httpx

from .fetch import MAX_BYTES, SourceError, valid_url


def atomic_json(path, value):
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class LiveFetch:
    def __init__(self, *, allow_paid=False, max_calls=0, attempts=None, timeout=30):
        self.allow_paid = allow_paid
        self.max_calls = max_calls
        self.attempts = attempts
        self.timeout = timeout

    def fetch(self, url, folder):
        if not self.allow_paid:
            raise SourceError("paid_not_allowed", "在线 Fetch 需要 --allow-paid")
        if self.max_calls < 1:
            raise SourceError("fetch_budget_exhausted", "没有 Fetch 调用预算")
        if not self.attempts:
            raise SourceError("fetch_attempt_store_required", "在线 Fetch 需要持久化尝试记录")
        self.attempts.mkdir(parents=True, exist_ok=True)
        lock = self.attempts / ".fetch.lock"
        try:
            with lock.open("x"):
                pass
        except FileExistsError as error:
            raise SourceError("fetch_attempt_store_busy", "尝试记录已锁定；不自动重试") from error
        try:
            attempt_path = self.attempts / ("fetch-" + hashlib.sha256(url.encode("utf-8")).hexdigest() + ".json")
            if attempt_path.exists():
                try:
                    previous = json.loads(attempt_path.read_text(encoding="utf-8"))
                    state = previous.get("state", "unknown")
                except (OSError, ValueError, AttributeError):
                    state = "unknown"
                code = "fetch_attempt_exists" if state == "completed" else "fetch_attempt_unknown"
                raise SourceError(code, "已有此 URL 的尝试；不自动重发")
            if len(list(self.attempts.glob("fetch-*.json"))) >= self.max_calls:
                raise SourceError("fetch_budget_exhausted", "持久化 Fetch 预算已用完")
            key = os.environ.get("DEEPSEEK_API_KEY", "")
            if not key:
                raise SourceError("fetch_key_missing", "缺少 DEEPSEEK_API_KEY 环境密钥")
            attempt = {"provider": "deepseek-fetch", "url": url, "state": "unknown",
                       "started_at": datetime.now(timezone.utc).isoformat()}
            atomic_json(attempt_path, attempt)
        finally:
            lock.unlink()
        try:
            with httpx.Client(timeout=self.timeout, trust_env=False, follow_redirects=False) as client:
                with client.stream("POST", "https://api.deepseek.com/v1/tools/fetch", json={"url": url},
                                   headers={"Authorization": "Bearer " + key}) as response:
                    raw = bytearray()
                    for chunk in response.iter_bytes():
                        raw.extend(chunk)
                        if len(raw) > MAX_BYTES:
                            raise SourceError("fetch_response_too_large", "提供方响应超过限制；未当成全文")
                    raw = bytes(raw)
                    redacted = raw.replace(key.encode("utf-8"), b"[REDACTED]")
                    observed = datetime.now(timezone.utc).isoformat()
                    metadata = {"source": "live", "provider_http_status": response.status_code,
                                "observed_at": observed, "response_redacted": redacted != raw,
                                "original_response_sha256": hashlib.sha256(raw).hexdigest(),
                                "attempt_file": str(attempt_path.resolve())}
                    result, content = save_fetch(redacted, metadata, folder)
                    attempt.update(state="completed", completed_at=observed,
                                   provider_http_status=response.status_code,
                                   response_sha256=result["response_sha256"],
                                   original_response_sha256=metadata["original_response_sha256"])
                    atomic_json(attempt_path, attempt)
                    return result, content
        except (httpx.HTTPError, SourceError) as error:
            attempt["error"] = {"code": getattr(error, "code", "fetch_network_unknown"),
                                "message": type(error).__name__}
            atomic_json(attempt_path, attempt)
            raise SourceError(attempt["error"]["code"], "提供方结局未知；保留尝试且不自动重发") from error


class CacheManifest:
    def __init__(self, path):
        self.root = path.resolve().parent
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        if value.get("version") != 1 or not isinstance(value.get("entries"), list):
            raise ValueError("缓存清单必须为 version: 1 和 entries 列表")
        self.entries = {}
        for entry in value["entries"]:
            url = valid_url(entry["url"])
            if url in self.entries:
                raise ValueError("缓存清单 URL 重复")
            self.entries[url] = entry

    def entry(self, url):
        if url not in self.entries:
            raise SourceError("cache_missing", "缓存清单没有此 URL；未联网")
        return self.entries[url]

    def bound_item(self, url, kind):
        item = self.entry(url).get(kind, {})
        if not isinstance(item, dict):
            raise SourceError("cache_invalid", "缓存条目必须为对象")
        if item.get("url", url) != url:
            raise SourceError("cache_url_mismatch", "缓存 URL 与输入不匹配")
        return item

    def read(self, item):
        try:
            relative = Path(item["path"])
            path = (self.root / relative).resolve()
            if relative.is_absolute() or not path.is_relative_to(self.root):
                raise SourceError("cache_path_invalid", "缓存路径必须在清单目录内")
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != item["sha256"]:
                raise SourceError("cache_hash_mismatch", "缓存 SHA256 不匹配")
            return data
        except (KeyError, OSError, TypeError) as error:
            raise SourceError("cache_missing", "缓存文件或 SHA256 缺失；未联网") from error

    def source(self, url):
        source = self.bound_item(url, "source")
        if "error" in source:
            error = source["error"]
            raise SourceError(error["code"], error["message"])
        data = self.read(source)
        metadata = {key: source[key] for key in ("final_url", "http_status", "content_type", "observed_at")
                    if key in source}
        metadata.setdefault("content_type", "text/html")
        return data, metadata

    def fetch(self, url, folder):
        item = self.bound_item(url, "fetch")
        raw = self.read(item)
        return save_fetch(raw, item, folder)

    def model(self, url, source_sha256, folder):
        item = self.bound_item(url, "model")
        if not source_sha256 or item.get("source_sha256") != source_sha256:
            raise SourceError("cache_source_hash_mismatch", "模型缓存没有绑定当前原件 SHA256")
        raw = self.read(item)
        path = folder / "model-response.json"
        path.write_bytes(raw)
        return {"status": "validated_not_applied", "source_sha256": source_sha256,
                "response_file": path.relative_to(folder.parent).as_posix(),
                "response_sha256": hashlib.sha256(raw).hexdigest(), "observed_at": item.get("observed_at")}


def save_fetch(raw, metadata, folder):
    response = folder / "fetch-response.json"
    response.write_bytes(raw)
    result = {"provider": "deepseek-fetch", "source": metadata.get("source", "cache"), "status": "not_extracted",
              "provider_http_status": metadata.get("provider_http_status"),
              "origin_http_status": None, "observed_at": metadata.get("observed_at"),
              "response_file": response.relative_to(folder.parent).as_posix(),
              "response_sha256": hashlib.sha256(raw).hexdigest(), "completeness": "not_verified"}
    for key in ("response_redacted", "original_response_sha256", "attempt_file"):
        if key in metadata:
            result[key] = metadata[key]
    try:
        status = metadata.get("provider_http_status")
        if not isinstance(status, int) or not 200 <= status < 300:
            raise SourceError(f"provider_http_{status}", "提供方未返回成功 HTTP 状态")
        value = json.loads(raw)
        if not isinstance(value, dict) or not isinstance(value.get("content"), str):
            raise SourceError("fetch_invalid_response", "Fetch 响应缺少字符串 content")
        content = value["content"]
        if not content.strip() or value.get("truncated") or metadata.get("truncated"):
            raise SourceError("fetch_incomplete_response", "Fetch 正文为空或已标记截断")
        (folder / "fetch-content.md").write_text(content, encoding="utf-8")
        result.update(status="text_saved", title=value.get("title", ""),
                      content_file=(folder / "fetch-content.md").relative_to(folder.parent).as_posix(),
                      content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest())
        return result, content
    except (SourceError, ValueError, UnicodeError) as error:
        result.update(status="read_failed", error={"code": getattr(error, "code", "fetch_invalid_response"),
                                                  "message": str(error)})
        return result, ""
