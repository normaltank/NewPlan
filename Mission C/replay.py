"""Recommended strictly offline combination entry point; no paid/live options."""
import argparse
from pathlib import Path

from mission_c.cli import main


def replay(argv=None):
    parser = argparse.ArgumentParser(description="离线组合回放：本地原件 + Fetch 补充 + 模型证据辅助")
    parser.add_argument("--cache-manifest", type=Path, default=Path(__file__).resolve().parent / "examples/assisted-cache/manifest.json")
    parser.add_argument("--output", type=Path, help="尚不存在的结果目录")
    parser.add_argument("--url", action="append", default=[], help="仅回放清单中的指定 URL，可重复")
    args = parser.parse_args(argv)
    options = ["--cache-manifest", str(args.cache_manifest), "--fetch-mode", "supplement", "--model-mode", "assist"]
    if args.output:
        options += ["--output", str(args.output)]
    for url in args.url:
        options += ["--url", url]
    return main(options)


if __name__ == "__main__":
    raise SystemExit(replay())
