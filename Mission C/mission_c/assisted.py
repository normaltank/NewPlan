"""Bound cached source bytes to URL; provider evidence never impersonates origin HTML."""
import hashlib
import json
from pathlib import Path

from .fetch import SourceError, valid_url


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
        source = self.entry(url).get("source", {})
        if "error" in source:
            error = source["error"]
            raise SourceError(error["code"], error["message"])
        data = self.read(source)
        metadata = {key: source[key] for key in ("final_url", "http_status", "content_type", "observed_at")
                    if key in source}
        metadata.setdefault("content_type", "text/html")
        return data, metadata

    def fetch(self, url, folder):
        item = self.entry(url).get("fetch", {})
        raw = self.read(item)
        return save_fetch(raw, item, folder)


def save_fetch(raw, metadata, folder):
    response = folder / "fetch-response.json"
    response.write_bytes(raw)
    result = {"provider": "deepseek-fetch", "source": "cache", "status": "not_extracted",
              "provider_http_status": metadata.get("provider_http_status"),
              "origin_http_status": None, "observed_at": metadata.get("observed_at"),
              "response_file": response.relative_to(folder.parent).as_posix(),
              "response_sha256": hashlib.sha256(raw).hexdigest(), "completeness": "not_verified"}
    value = json.loads(raw)
    content = value["content"]
    (folder / "fetch-content.md").write_text(content, encoding="utf-8")
    result.update(status="text_saved", title=value.get("title", ""),
                  content_file=(folder / "fetch-content.md").relative_to(folder.parent).as_posix(),
                  content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest())
    return result, content
