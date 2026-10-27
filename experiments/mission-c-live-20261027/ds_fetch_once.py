"""One authorized Fetch trial, distinct from DS model extraction."""
import argparse
import asyncio
from datetime import datetime, timezone
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", choices=[sample["id"] for sample in SAMPLES], default="lzjtu")
    parser.add_argument("--output-root", type=Path, default=OUT)
    args = parser.parse_args()
    sample = next(sample for sample in SAMPLES if sample["id"] == args.sample)
    folder = args.output_root / "deepseek-fetch" / sample["id"]
    folder.mkdir(parents=True, exist_ok=True)
    summary = folder / "result.json"
    if summary.exists():
        row = json.loads(summary.read_text(encoding="utf-8"))
        if row.get("url") != sample["url"]:
            raise SystemExit("Cached Fetch URL mismatch; saved evidence was not changed")
    else:
        attempt = folder / "attempt.json"
        if attempt.exists():
            raise SystemExit("Previous Fetch attempt is unresolved; inspect saved evidence before any retry")
        key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not key:
            raise SystemExit("Use the existing encrypted credential launcher")
        async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=45,
                                     headers={"Authorization": "Bearer " + key}) as client:
            started_at = datetime.now(timezone.utc).isoformat()
            try:
                with attempt.open("x", encoding="utf-8") as stream:
                    json.dump({"url": sample["url"], "status": "in_flight_or_unknown_until_result",
                               "automatic_retry": False, "started_at": started_at, "calls": 1}, stream)
            except FileExistsError:
                raise SystemExit("Previous Fetch attempt is unresolved; automatic retry blocked") from None
            try:
                response = await client.post("https://api.deepseek.com/v1/tools/fetch", json={"url": sample["url"]})
            except Exception as error:
                save(folder / "failure.json", {"url": sample["url"], "status": "unknown",
                     "error_type": type(error).__name__, "calls": 1, "automatic_retry": False,
                     "observed_at": datetime.now(timezone.utc).isoformat()})
                raise SystemExit("Fetch outcome unknown; failure saved, automatic retry blocked") from None
            observed_at = datetime.now(timezone.utc).isoformat()
            try:
                data = response.json()
            except ValueError:
                data = {"text": response.text}
            serialized = response.content.replace(key.encode(), b"[REDACTED]")
            (folder / "provider-response.json").write_bytes(serialized)
            data = json.loads(json.dumps(data, ensure_ascii=False).replace(key, "[REDACTED]"))
            content = data.get("content", "") if isinstance(data, dict) else ""
            content = content if isinstance(content, str) else ""
            (folder / "provider-content.md").write_text(content, encoding="utf-8")
            row = {"method": "deepseek-fetch", "url": sample["url"], "provider_http_status": response.status_code,
                   "observed_at": observed_at,
                   "started_at": started_at,
                   "provider_response_sha256": hashlib.sha256(serialized).hexdigest(),
                   "response_credential_redacted": serialized != response.content,
                   "origin_http_status": None, "text_saved": response.status_code == 200 and bool(content.strip()),
                   "failure": "provider_http_error" if response.status_code != 200 else (None if content.strip() else "empty_provider_content"),
                   "provider_title": data.get("title", "") if isinstance(data, dict) else "",
                   "characters": len(content), "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
                   "calls": 1, "not_origin_html": True, "completeness": "not_verified"}
            save(summary, row)
    print(json.dumps(row, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
