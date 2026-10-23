"""Isolated DeepSeek Fetch client. Never equates provider 404 with origin 404."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent
BASE = "https://api.deepseek.com"
ENDPOINT = "/v1/tools/fetch"


def redact(value, key):
    text = json.dumps(value, ensure_ascii=False, indent=2)
    if key:
        text = text.replace(key, "[REDACTED]")
    return re.sub(r"(?:sk|ghp|fc)-[A-Za-z0-9_-]{16,}", "[REDACTED]", text)


def save(path, value, key=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(redact(value, key), encoding="utf-8")


class FetchClient:
    def __init__(self, output, *, max_calls=500, timeout=60, transport=None):
        self.output = Path(output)
        self.key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if not self.key:
            raise RuntimeError("DEEPSEEK_API_KEY is not configured")
        self.max_calls = max_calls
        ledger = self.output / "calls.json"
        self.calls = json.loads(ledger.read_text(encoding="utf8")) if ledger.exists() else []
        self.http = httpx.AsyncClient(
            base_url=BASE, trust_env=False, follow_redirects=False,
            headers={"Authorization": f"Bearer {self.key}"},
            timeout=httpx.Timeout(timeout, connect=15), transport=transport,
        )
        self.last_request = 0.0
        self.rate_lock = asyncio.Lock()

    async def close(self):
        await self.http.aclose()

    async def fetch(self, url, *, attempts=2):
        for old in reversed(self.calls):
            if old.get("url") != url:
                continue
            if old.get("status") == "ok":
                digest = hashlib.sha256(url.encode()).hexdigest()[:16]
                path = self.output / f"{old['index']:04}-{digest}-response.json"
                if path.is_file():
                    data = json.loads(path.read_text(encoding="utf8"))
                    return {"status":"ok", "title":data.get("title",""), "content":data["content"],
                            "origin_status":None, "call_index":old["index"], "reused_saved_response":True}
            if old.get("http_status") in (400,401,402,403,404,413):
                return {"status":old["status"], "content":"", "origin_status":None,
                        "http_status":old["http_status"], "call_index":old["index"], "reused_saved_response":True}
        for attempt in range(1, attempts + 1):
            async with self.rate_lock:
                if len(self.calls) >= self.max_calls:
                    return {"status": "budget_exhausted", "content": "", "origin_status": None}
                wait = 1.05 - (time.monotonic() - self.last_request)
                if wait > 0:
                    await asyncio.sleep(wait)
                self.last_request = time.monotonic()
                started = time.perf_counter()
                index = len(self.calls) + 1
                key = hashlib.sha256(url.encode()).hexdigest()[:16]
                row = {"index": index, "url": url, "attempt": attempt, "endpoint": ENDPOINT,
                       "started_at": datetime.now(timezone.utc).isoformat(), "origin_status": None,
                       "status":"in_flight", "billing_outcome":"unknown_until_response"}
                self.calls.append(row)
                save(self.output / "calls.json", self.calls, self.key)
            result = {"status": "unavailable", "content": "", "origin_status": None}
            response = None
            try:
                response = await self.http.post(ENDPOINT, json={"url": url})
                row["http_status"] = response.status_code
                try:
                    data = response.json()
                except ValueError:
                    data = {"raw_text": response.text}
                save(self.output / f"{index:04}-{key}-response.json", data, self.key)
                good = (response.status_code == 200 and isinstance(data, dict)
                        and isinstance(data.get("content"), str) and bool(data["content"].strip()))
                row["billable_success"] = good
                row["estimated_fetch_usd"] = 0.00075 if good else 0.0
                if good:
                    result = {"status": "ok", "title": data.get("title", ""),
                              "content": data["content"], "origin_status": None}
                    row["chars"] = len(data["content"])
                else:
                    row["provider_error_code"] = str(data.get("error", {}).get("code", "")) if isinstance(data, dict) and isinstance(data.get("error"), dict) else ""
                    result["http_status"] = response.status_code
                    result["status"] = "provider_no_usable_content" if response.status_code == 404 else "provider_error"
            except (httpx.HTTPError, ValueError) as exc:
                row["error_type"] = type(exc).__name__
                row["billable_success"] = False
                row["estimated_fetch_usd"] = 0.0
                result["status"] = "transport_error"
            finally:
                row["seconds"] = round(time.perf_counter() - started, 3)
                row["status"] = result["status"]
                save(self.output / "calls.json", self.calls, self.key)
            retryable = response is None or response.status_code in (408, 429) or response.status_code >= 500
            if result["status"] == "ok" or not retryable or attempt == attempts:
                result["call_index"] = index
                return result
            await asyncio.sleep(min(2 * attempt, 8))


async def probe(url):
    output = ROOT / "probe" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    client = FetchClient(output, max_calls=2, timeout=50)
    try:
        result = await client.fetch(url, attempts=1)
        summary = {"url": url, "fetch_status": result["status"],
                   "fetch_http_status": result.get("http_status", 200 if result["status"] == "ok" else None),
                   "chars": len(result.get("content", "")), "output": str(output)}
        try:
            control = await client.http.get("/user/balance")
            summary["account_control_status"] = control.status_code
        except httpx.HTTPError as exc:
            summary["account_control_error"] = type(exc).__name__
        save(output / "summary.json", summary, client.key)
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    finally:
        await client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="https://me.seu.edu.cn/cxl/list.htm")
    args = parser.parse_args()
    asyncio.run(probe(args.url))
