"""Bounded live capture, separate processes so Crawlee state remains isolated."""
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf8")


async def main():
    cases = json.loads((ROOT / "cases.json").read_text(encoding="utf8"))
    limit = asyncio.Semaphore(2)
    results = {}
    async def one(case):
        async with limit:
            folder = ROOT / "runs" / case["case"]
            folder.mkdir(parents=True, exist_ok=True)
            if (folder / "capture-result.json").exists():
                results[case["case"]] = json.loads((folder / "capture-result.json").read_text(encoding="utf8"))
                return
            pointer = folder / "capture-pointer.json"
            args = [sys.executable, str(ROOT / "runtime/api_pilot.py"),
                    "--university", case["university"], "--college", case["college"],
                    "--url", case["url"], "--max-pages", "500", "--max-calls", "45",
                    "--max-images", "200", "--ocr", "--browser", "--pointer", str(pointer)]
            for entry in case["entries"]:
                args.extend(["--entries", entry])
            stamp = {"case": case["case"], "state": "running", "started": datetime.now(timezone.utc).isoformat(),
                     "command": args, "scope": "live_capture_then_paired_reading_and_delivery"}
            results[case["case"]] = stamp
            save(ROOT / "run-status.json", results)
            with (folder / "capture.log").open("wb") as log:
                process = await asyncio.create_subprocess_exec(*args, cwd=ROOT / "runtime", stdout=log,
                    stderr=asyncio.subprocess.STDOUT, env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"})
                try:
                    await asyncio.wait_for(process.wait(), timeout=2400)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
                    stamp["timeout"] = True
            stamp.update(state="captured" if process.returncode == 0 else "capture_failed",
                         return_code=process.returncode, finished=datetime.now(timezone.utc).isoformat())
            if pointer.exists():
                stamp.update(json.loads(pointer.read_text(encoding="utf8")))
                summary_path = Path(stamp["run_dir"]) / "summary.json"
                if summary_path.exists():
                    stamp["summary"] = json.loads(summary_path.read_text(encoding="utf8"))
            save(folder / "capture-result.json", stamp)
            save(ROOT / "run-status.json", results)
            print(json.dumps({"case": case["case"], "state": stamp["state"], "summary": stamp.get("summary")}, ensure_ascii=False), flush=True)
    await asyncio.gather(*(one(case) for case in cases))


if __name__ == "__main__":
    asyncio.run(main())
