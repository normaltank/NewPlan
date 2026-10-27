"""CLI inputs and outputs are the supported public interface."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import uuid

from .extract import extract_html, refresh_fields
from .export import export_tables
from .fetch import Fetcher, SourceError, valid_url
from .media import collect_media


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description="任务 C：从教师个人主页保存基本字段与完整原文")
    parser.add_argument("--url", action="append", default=[], help="教师个人主页 URL，可重复")
    parser.add_argument("--urls-file", type=Path, help="UTF-8 文本，每行一个个人主页 URL")
    parser.add_argument("--html", type=Path, help="离线保存的 HTML，配合一个 --url；不会联网")
    parser.add_argument("--output", type=Path, help="新的结果目录；默认 outputs 下的新目录")
    parser.add_argument("--selector", help="明确指定唯一正文 CSS 容器")
    parser.add_argument("--name", help="预期姓名；与页面冲突时不强行采用")
    parser.add_argument("--render", action="store_true", help="使用本机浏览器读取动态页面，需要可选依赖")
    parser.add_argument("--ocr", action="store_true", help="本地识别图片与扫描 PDF，结果为待复核候选")
    parser.add_argument("--school", default="", help="调用者提供的学校，另存为输入元数据")
    parser.add_argument("--college", default="", help="调用者提供的学院，另存为输入元数据")
    parser.add_argument("--timeout", type=float, default=30, help="单次网络超时秒数")
    parser.add_argument("--delay", type=float, default=0.5, help="请求间隔秒数，至少 0.5")
    args = parser.parse_args(argv)
    try:
        urls = args.url[:]
        if args.urls_file:
            urls.extend(line.strip() for line in args.urls_file.read_text(encoding="utf-8-sig").splitlines()
                        if line.strip() and not line.lstrip().startswith("#"))
        urls = list(dict.fromkeys(valid_url(url) for url in urls))
        if not urls or ((args.html or args.name) and len(urls) != 1):
            raise ValueError("请提供 URL；--html 和 --name 仅用于单个 URL")
        if args.timeout <= 0 or args.delay < 0.5:
            raise ValueError("--timeout 必须大于 0；--delay 至少为 0.5")
        if args.html and args.render:
            raise ValueError("离线 --html 不执行脚本；不能同时使用 --render")
        offline_data = args.html.read_bytes() if args.html else None
        output = args.output or Path(__file__).resolve().parents[1] / "outputs" / (
            datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8])
        output.mkdir(parents=True, exist_ok=False)
        fetcher = Fetcher(args.timeout, args.delay) if not args.html else None
        records = []
        try:
            for index, url in enumerate(urls, 1):
                folder = output / f"{index:04d}"
                folder.mkdir()
                record = {"requested_url": url, "final_url": url, "name": "", "title": "", "email": "",
                          "biography": "", "research": "", "publications": "", "status": "not_extracted",
                          "review_required": True, "completeness": "not_verified", "warnings": [],
                          "field_status": {"name": "not_read", "title": "not_read", "email": "not_read"},
                          "source_file": "", "biography_file": "",
                          "source_mode": "saved_html" if args.html else "http",
                          "observed_at": datetime.now(timezone.utc).isoformat(),
                          "input_metadata": {"school": args.school, "college": args.college,
                                             "collector": "自动采集", "expected_name": args.name}}
                try:
                    if offline_data is None:
                        data, metadata = fetcher.get(url)
                        record.update(metadata)
                    else:
                        data = offline_data
                    (folder / "source.html").write_bytes(data)
                    record.update(sha256=hashlib.sha256(data).hexdigest(), source_file=f"{index:04d}/source.html")
                    if not args.html and "html" not in record["content_type"] and not data.lstrip().startswith(b"<"):
                        raise SourceError("unsupported_content", "个人页不是 HTML；源文件已保留")
                    if args.render:
                        from .render import render_page
                        data, rendering = render_page(record["final_url"], folder, fetcher)
                        record.update(rendering)
                    record.update(extract_html(data, record["final_url"], args.selector, args.name))
                    if record.get("browser_blocked_requests"):
                        record["warnings"].append("browser_resources_not_fully_loaded")
                    if args.render:
                        record["warnings"].append("dynamic_tabs_and_pagination_not_verified")
                    record["media"] = collect_media(record["content_html"], record["final_url"], folder, fetcher, args.ocr)
                    for medium in record["media"]:
                        if medium["text"]:
                            label = "OCR 待复核" if medium["status"] == "ocr_candidate" else "个人页附件原文"
                            record["biography"] += f"\n\n[{label}：{medium['url']}]\n" + medium["text"]
                    if any(item["status"] != "text_saved" for item in record["media"]):
                        record["warnings"].append("media_not_fully_read")
                    if any(medium["text"] for medium in record["media"]):
                        refresh_fields(record)
                    (folder / "page.txt").write_text(record.pop("page_text"), encoding="utf-8")
                    (folder / "content.html").write_text(record.pop("content_html"), encoding="utf-8")
                    (folder / "biography.txt").write_text(record["biography"], encoding="utf-8")
                    record.update(biography_file=f"{index:04d}/biography.txt",
                                  status="text_saved" if record["biography"] else "not_extracted")
                except (SourceError, ValueError) as error:
                    record["error"] = {"code": getattr(error, "code", "extraction_error"), "message": str(error)}
                write_json(folder / "record.json", record)
                records.append(record)
                write_json(output / "teachers.json", records)
                print(f"[{index}/{len(urls)}] {record['status']}")
        finally:
            if fetcher:
                fetcher.close()
        export_tables(output, records)
        print(f"已保存 {len(records)} 条个人页记录：{output.resolve()}")
        return int(any(record["status"] != "text_saved" for record in records))
    except (ValueError, OSError) as error:
        parser.exit(2, f"任务 C 未完成：{error}\n")
