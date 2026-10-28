"""Reproduce the controlled inventory replay without network or paid requests.

Run with the documented independent Python, --package, --inventory, --baseline,
and a new --output directory. Inputs are never modified. Real evidence stays local.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


GUARD = '''import atexit, json, os, socket
from pathlib import Path
counts = {"http_requests": 0, "socket_connects": 0, "dns_queries": 0}
def deny_http(*args, **kwargs):
    counts["http_requests"] += 1
    raise RuntimeError("offline verification blocked HTTP")
def deny_connect(*args, **kwargs):
    counts["socket_connects"] += 1
    raise RuntimeError("offline verification blocked socket")
def deny_dns(*args, **kwargs):
    counts["dns_queries"] += 1
    raise RuntimeError("offline verification blocked DNS")
socket.socket.connect = deny_connect
socket.socket.connect_ex = deny_connect
socket.create_connection = deny_connect
socket.getaddrinfo = deny_dns
import httpx
httpx.Client.send = deny_http
httpx.AsyncClient.send = deny_http
atexit.register(lambda: Path(os.environ["MISSION_C_AUDIT_FILE"]).write_text(json.dumps(counts), encoding="utf-8"))
'''


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("package", "inventory", "baseline", "output"):
        parser.add_argument("--" + option, type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    output = args.output.resolve()
    guard = output / "network-guard"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text(GUARD, encoding="utf-8")
    inventory = json.loads(args.inventory.read_text(encoding="utf-8-sig"))
    commands = []

    def run(label, command, expected):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(guard)
        env["MISSION_C_AUDIT_FILE"] = str(output / (label + "-network.json"))
        result = subprocess.run([sys.executable, *map(str, command)], cwd=output, env=env,
                                capture_output=True, text=True, encoding="utf-8")
        (output / (label + ".log")).write_text(result.stdout + result.stderr, encoding="utf-8")
        counts = json.loads(Path(env["MISSION_C_AUDIT_FILE"]).read_text(encoding="utf-8"))
        commands.append({"label": label, "command": [sys.executable, *map(str, command)],
                         "exit_code": result.returncode, "network": counts})
        write(output / "commands.json", commands)
        if result.returncode != expected or any(counts.values()):
            raise RuntimeError(f"{label}: exit={result.returncode}, network={counts}; see log")

    # Preparation does not load providers, but it is guarded too.
    run("import", [args.package / "prepare_cache.py", "--inventory", args.inventory,
                   "--output", output / "prepared"], 0)
    package = output / "portable/Mission C"
    shutil.copytree(args.package, package, ignore=shutil.ignore_patterns("outputs", ".venv", "__pycache__", "*.pyc"))
    shutil.move(str(output / "prepared"), str(package / "cache"))
    manifest = json.loads((package / "cache/manifest.json").read_text(encoding="utf-8"))
    provenance = json.loads((package / "cache/import-provenance.json").read_text(encoding="utf-8"))
    # The actual public command runs solely from the moved, independent package.
    run("combination20", [package / "replay.py", "--cache-manifest", package / "cache/manifest.json",
                          "--output", output / "combination20"], 1)
    rows = json.loads((output / "combination20/teachers.json").read_text(encoding="utf-8"))
    comparisons = []
    for index, (item, row) in enumerate(zip(inventory["entries"], rows), 1):
        comparison = {"id": item["id"], "url": item["url"], "source_available": bool(item.get("source")),
                      "status": row["status"], "name": row["name"], "title": row["title"], "email": row["email"],
                      "field_status": row["field_status"], "origin_error": row.get("error"),
                      "fetch_status": row["fetch"]["status"], "fetch_error": row["fetch"].get("error"),
                      "model_status": row["model"]["status"], "model_error": row["model"].get("error"),
                      "model_candidates": row["model"].get("candidates"), "model_selector": row["model"].get("selector"),
                      "historical_usage": row["model"].get("usage"), "biography_characters": len(row["biography"]),
                      "media": row.get("media", []), "warnings": row["warnings"], "completeness": row["completeness"]}
        if item.get("source"):
            source = package / "cache" / manifest["entries"][index - 1]["source"]["path"]
            baseline_out = output / "baseline" / f"{index:04d}"
            run(f"baseline-{index:04d}", [args.baseline / "collect.py", "--url", item["url"],
                                        "--html", source, "--output", baseline_out], 0)
            before = json.loads((baseline_out / "teachers.json").read_text(encoding="utf-8"))[0]
            comparison["baseline"] = {key: before[key] for key in ("name", "title", "email", "field_status")}
            comparison["baseline_biography_characters"] = len(before["biography"])
            comparison["biography_equal_baseline"] = before["biography"] == row["biography"]
            comparison["biography_preserves_baseline"] = before["biography"] in row["biography"]
            comparison["baseline_biography_sha256"] = hashlib.sha256(before["biography"].encode()).hexdigest()
            comparison["biography_sha256"] = hashlib.sha256(row["biography"].encode()).hexdigest()
            comparison["source_copy_equal"] = digest(source) == digest(output / "combination20" / row["source_file"])
            content_file = row["fetch"].get("content_file")
            if content_file:
                fetch_text = (output / "combination20" / content_file).read_text(encoding="utf-8")
                comparison["fetch_characters"] = len(fetch_text)
                comparison["baseline_only_lines"] = [line for line in before["biography"].splitlines() if line.strip() and line not in fetch_text]
                comparison["fetch_only_lines"] = [line for line in fetch_text.splitlines() if line.strip() and line not in before["biography"]]
        comparisons.append(comparison)
    input_checks = [{"path": item["path"], "original_unchanged": digest(Path(item["original_path"])) == item["sha256"],
                     "copied_unchanged": digest(package / "cache" / item["path"]) == item["sha256"],
                     "mtime_preserved": (package / "cache" / item["path"]).stat().st_mtime_ns == item["mtime_ns"]}
                    for item in provenance["files"]]
    checks = {"entry_count": len(rows), "local_html_count": sum(item["source_available"] for item in comparisons),
              "statuses": dict(Counter(row["status"] for row in rows)),
              "fetch_statuses": dict(Counter(row["fetch"]["status"] for row in rows)),
              "model_statuses": dict(Counter(row["model"]["status"] for row in rows)),
              "baseline_all_preserved": all(item.get("biography_preserves_baseline", True) for item in comparisons),
              "baseline_all_equal": all(item.get("biography_equal_baseline", True) for item in comparisons),
              "source_copies_all_equal": all(item.get("source_copy_equal", True) for item in comparisons),
              "input_checks": input_checks, "current_network": {key: sum(command["network"][key] for command in commands)
                                                               for key in ("http_requests", "socket_connects", "dns_queries")},
              "current_paid_calls": sum(command["network"]["http_requests"] for command in commands),
              "usage_note": "网络阻断边界 HTTP 请求总数为零，因此付费调用为零；model usage 来自历史响应",
              "baseline": str(args.baseline.resolve()), "portable_package": str(package), "comparisons": comparisons}
    write(output / "verification.json", checks)
    if len(rows) != len(inventory["entries"]) or not checks["baseline_all_preserved"] or not checks["source_copies_all_equal"] or not all(
            all(item[key] for key in ("original_unchanged", "copied_unchanged", "mtime_preserved")) for item in input_checks):
        raise RuntimeError("回放验证失败；检查 verification.json")
    print(json.dumps({key: value for key, value in checks.items() if key not in ("comparisons", "input_checks")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
