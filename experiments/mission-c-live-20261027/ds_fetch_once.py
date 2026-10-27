"""One authorized Fetch trial, distinct from DS model extraction."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from compare import OUT, SAMPLES, save
import httpx


async def main():
    folder = OUT / "deepseek-fetch" / "lzjtu"
    folder.mkdir(parents=True, exist_ok=True)
    summary = folder / "result.json"
    if summary.exists():
        row = json.loads(summary.read_text(encoding="utf-8"))
    else:
        attempt = folder / "attempt.json"
        if attempt.exists():
            raise SystemExit("Previous Fetch attempt is unresolved; inspect saved evidence before any retry")
        key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not key:
            raise SystemExit("Use the existing encrypted credential launcher")
        async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=45,
                                     headers={"Authorization": "Bearer " + key}) as client:
            save(attempt, {"url": SAMPLES[0]["url"], "status": "in_flight_or_unknown_until_result", "automatic_retry": False})
            response = await client.post("https://api.deepseek.com/v1/tools/fetch", json={"url": SAMPLES[0]["url"]})
            try:
                data = response.json()
            except ValueError:
                data = {"text": response.text}
            serialized = json.dumps(data, ensure_ascii=False, indent=2).replace(key, "[REDACTED]")
            data = json.loads(serialized)
            (folder / "provider-response.json").write_text(serialized, encoding="utf-8")
            content = data.get("content", "") if isinstance(data, dict) else ""
            content = content if isinstance(content, str) else ""
            (folder / "provider-content.md").write_text(content, encoding="utf-8")
            row = {"method": "deepseek-fetch", "url": SAMPLES[0]["url"], "provider_http_status": response.status_code,
                   "origin_http_status": None, "text_saved": response.status_code == 200 and bool(content.strip()),
                   "provider_title": data.get("title", "") if isinstance(data, dict) else "",
                   "characters": len(content), "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
                   "calls": 1, "not_origin_html": True, "completeness": "not_verified"}
            save(summary, row)
    print(json.dumps(row, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
