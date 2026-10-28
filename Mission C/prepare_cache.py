"""Copy a read-only historical inventory into a relative, portable cache manifest."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil


def main(argv=None):
    parser = argparse.ArgumentParser(description="只读导入历史缓存；复制原字节和文件时间，生成相对路径清单")
    parser.add_argument("--inventory", type=Path, required=True, help="含 entries 的库存 JSON；格式见 README")
    parser.add_argument("--output", type=Path, required=True, help="尚不存在的便携缓存目录")
    args = parser.parse_args(argv)
    try:
        inventory = json.loads(args.inventory.read_text(encoding="utf-8-sig"))
        if not isinstance(inventory, dict) or not isinstance(inventory.get("entries"), list) or not inventory["entries"]:
            raise ValueError("库存必须含非空 entries 列表")
        from mission_c.fetch import valid_url
        entries, provenance, copies, urls = [], [], [], set()

        def asset(item, destination, expected=True):
            path = Path(item["path"])
            if not path.is_absolute():
                path = args.inventory.resolve().parent / path
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if expected and digest != item["sha256"]:
                raise ValueError(f"库存 SHA256 不匹配：{path}")
            copies.append((path, destination, digest))
            stat = path.stat()
            provenance.append({"path": destination, "original_path": str(path.resolve()), "sha256": digest,
                               "bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns})
            return {"path": destination, "sha256": digest}

        def metadata(path, destination, url):
            if not path:
                return {}
            asset({"path": path}, destination, False)
            value = json.loads(copies[-1][0].read_text(encoding="utf-8-sig"))
            if value.get("url", value.get("requested_url", url)) != url:
                raise ValueError("历史元数据 URL 与库存不一致")
            return value

        for number, row in enumerate(inventory["entries"], 1):
            url = valid_url(row["url"])
            if url in urls:
                raise ValueError("库存 URL 重复")
            urls.add(url)
            prefix = f"{number:04d}/"
            entry = {"url": url}
            source_meta = metadata(row.get("source_metadata"), prefix + "source-metadata.json", url)
            state = row.get("source_status", {})
            source = {key: source_meta[key] for key in ("observed_at", "final_url", "content_type") if key in source_meta}
            source.setdefault("observed_at", None)
            source["http_status"] = state.get("http_status")
            if row.get("source"):
                source.update(asset(row["source"], prefix + "source.html"))
            else:
                if row.get("rejected_source"):
                    source.update(asset(row["rejected_source"], prefix + "failed-source.html"))
                code = f"http_{state['http_status']}" if state.get("http_status") else "source_missing"
                source["error"] = state.get("error") or {"code": code, "message": "历史未取得可用原站 HTML；未重发请求"}
            entry["source"] = source
            fetch = row.get("fetch")
            if fetch:
                meta = metadata(fetch.get("metadata"), prefix + "fetch-metadata.json", url)
                entry["fetch"] = {**asset(fetch["response"], prefix + "fetch-response.json"),
                                  "provider_http_status": fetch["provider_http_status"],
                                  "observed_at": meta.get("observed_at")}
            model = row.get("model")
            if model:
                meta = metadata(model.get("legacy_result"), prefix + "model-metadata.json", url)
                entry["model"] = {**asset(model["response"], prefix + "model-response.json"),
                                  "source_sha256": model["source_sha256"],
                                  "source_kind": model.get("source_kind", "html"),
                                  "observed_at": meta.get("observed_at")}
            entries.append(entry)
        args.output.mkdir(parents=True, exist_ok=False)
        for path, destination, digest in copies:
            target = args.output / destination
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                raise ValueError("复制期间原件变化；保留未完成目录供核查")
        (args.output / "manifest.json").write_text(json.dumps({"version": 1, "entries": entries},
                                                            ensure_ascii=False, indent=2), encoding="utf-8")
        (args.output / "import-provenance.json").write_text(json.dumps({
            "imported_at": datetime.now(timezone.utc).isoformat(), "inventory_sha256": hashlib.sha256(args.inventory.read_bytes()).hexdigest(),
            "files": provenance, "note": "original_path 仅为历史溯源；运行只使用 manifest 相对路径"},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已导入 {len(entries)} 条：{(args.output / 'manifest.json').resolve()}")
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(2, f"缓存导入未完成：{error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
