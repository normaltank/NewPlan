"""Run a fixed, bounded homepage cohort through the existing Mission C CLI.

No paid APIs. Existing/uncertain attempts are never silently retried.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import subprocess
import sys


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--collector", required=True, type=Path)
    parser.add_argument("--offline", action="store_true", help="Only saved_html; never network")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
    samples = manifest["samples"]
    if not 1 <= len(samples) <= 15 or len({x["id"] for x in samples}) != len(samples):
        parser.error("Require 1..15 unique selected samples")
    if any(not re.fullmatch(r"[a-z0-9_-]+", x["id"]) for x in samples):
        parser.error("Sample IDs must be safe directory names")
    args.output.mkdir(parents=True, exist_ok=True)
    summary = []
    for sample in samples:
        folder = args.output / sample["id"]
        folder.mkdir(exist_ok=True)
        result = folder / "run.json"
        fingerprint = hashlib.sha256(json.dumps(sample, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if result.exists():
            old = json.loads(result.read_text(encoding="utf-8"))
            if old["sample_sha256"] != fingerprint or old["offline"] != args.offline:
                parser.error("Existing run has different input; choose a new output directory")
            summary.append(old)
            print(f"{sample['id']}: reuse {old['state']}", flush=True)
            continue
        if args.offline and not sample.get("saved_html"):
            parser.error("Offline mode requires saved_html for every sample")
        command = [sys.executable, str(args.collector.resolve()), "--url", sample["url"], "--output", str(folder / "cli"),
                   "--timeout", "15", "--school", sample.get("school", ""), "--college", sample.get("college", "")]
        if args.offline:
            command.extend(["--html", sample["saved_html"]])
        row = {"sample_id": sample["id"], "url": sample["url"], "sample_sha256": fingerprint,
               "offline": args.offline, "started_at": datetime.now(timezone.utc).isoformat(),
               "state": "attempt_started_outcome_unknown", "command": command,
               "collector_sha256": hashlib.sha256(args.collector.read_bytes()).hexdigest(),
               "python": sys.version, "packages": {p: importlib.metadata.version(p) for p in
                    ("httpx", "beautifulsoup4", "pypdf", "openpyxl")}}
        save(result, row)
        try:
            run = subprocess.run(command, capture_output=True, timeout=75)
            (folder / "stdout.txt").write_bytes(run.stdout)
            (folder / "stderr.txt").write_bytes(run.stderr)
            row.update(exit_code=run.returncode, state="cli_finished")
        except subprocess.TimeoutExpired as error:
            (folder / "stdout.txt").write_bytes(error.stdout or b"")
            (folder / "stderr.txt").write_bytes(error.stderr or b"")
            row.update(state="cli_timeout", error="75 second bounded run expired")
        teachers = folder / "cli" / "teachers.json"
        if teachers.exists():
            records = json.loads(teachers.read_text(encoding="utf-8"))
            row["records"] = [{k: record.get(k) for k in ("name", "title", "email", "status", "error", "sha256",
                "observed_at", "source_file", "field_status", "warnings")} for record in records]
        row["finished_at"] = datetime.now(timezone.utc).isoformat()
        save(result, row)
        summary.append(row)
        print(f"{sample['id']}: {row['state']} exit={row.get('exit_code')}", flush=True)
    save(args.output / "summary.json", summary)
    return int(any(x.get("exit_code") != 0 for x in summary))


if __name__ == "__main__":
    raise SystemExit(main())
