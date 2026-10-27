"""Evaluate fixed source checks and export the five reviewed experiment records."""
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unicodedata

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from compare import ROOT, OUT, SAMPLES, artifact, save
sys.path.insert(0, str(ROOT / "Mission C"))
from mission_c.extract import extract_html
from mission_c.export import export_tables, csv_value
from markdown_it import MarkdownIt
from bs4 import BeautifulSoup
import html

REFERENCES = {
    "suda": {"name": "何剑", "title": "教授", "email": "drhejian@suda.edu.cn", "school": "苏州大学", "college": "未来科学与工程学院", "anchors": ["085501", "drhejian@suda.edu.cn"]},
    "ncepu": {"name": "王健", "title": "教授", "email": "wangjian31791@ncepu.edu.cn", "school": "华北电力大学", "college": "电气与电子工程学院", "anchors": ["[50]", "4623-4633"]},
    "shu": {"name": "张惠芳", "title": "副研究员", "email": "hfzhang1967@shu.edu.cn", "school": "上海大学", "college": "理学院物理系", "anchors": ["鼓励和督促学生学习考研"]},
    "ecnu": {"name": "李艳青", "title": "教授", "email": "yqli@phy.ecnu.edu.cn", "school": "华东师范大学", "college": "物理与电子科学学院", "anchors": ["柔性光电材料与器件集成"]},
}


def normalize(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text or ""))


def replay_fixed():
    for sample in SAMPLES[1:]:
        folder = artifact("fixed-replay", sample)
        result = folder / "cli" / "teachers.json"
        if result.exists():
            continue
        source = OUT / "baseline" / sample["id"] / "cli" / "0001" / "source.html"
        run = subprocess.run([sys.executable, str(ROOT / "Mission C" / "collect.py"), "--url", sample["url"],
                              "--html", str(source), "--output", str(folder / "cli")],
                             capture_output=True, text=True, encoding="utf-8", timeout=60)
        (folder / "stdout.txt").write_text(run.stdout, encoding="utf-8")
        (folder / "stderr.txt").write_text(run.stderr, encoding="utf-8")
        if result.exists():
            row = json.loads(result.read_text(encoding="utf-8"))[0]
            save(folder / "result.json", {"method": "fixed-replay", **row, "text_saved": bool(row.get("biography")),
                                         "network_requests": 0, "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest()})


def summary():
    rows = []
    methods = ["baseline", "fixed-replay", "browser", "crawlee", "crawl4ai", "trafilatura", "ds"]
    for method in methods:
        for sample in SAMPLES:
            path = OUT / method / sample["id"] / "result.json"
            if not path.exists():
                continue
            row = json.loads(path.read_text(encoding="utf-8"))
            text = row.get("tool_text", row.get("biography", ""))
            reference = REFERENCES.get(sample["id"], {})
            item = {"method": method, "id": sample["id"], "url": sample["url"],
                    "text_saved": bool(text), "text_characters": len(text), "name": row.get("name", ""),
                    "title": row.get("title", ""), "email": row.get("email", ""),
                    "name_matches_reference": row.get("name") == reference.get("name") if reference and method != "trafilatura" else None,
                    "title_matches_reference": row.get("title") == reference.get("title") if reference and method != "trafilatura" else None,
                    "email_matches_reference": row.get("email") == reference.get("email") if reference and method != "trafilatura" else None,
                    "anchor_checks": {anchor: normalize(anchor) in normalize(text) for anchor in reference.get("anchors", [])},
                    "http_status": row.get("http_status"), "error": row.get("error"),
                    "field_source": "not_scored_text_only" if method == "trafilatura" else ("model_visible_candidates" if method == "ds" else "shared_Mission_C_rules")}
            rows.append(item)
    calls = json.loads((OUT / "ds" / "api" / "calls.json").read_text(encoding="utf-8"))
    result = {"samples": SAMPLES, "methodology": "5 convenience samples; text anchors are spot checks, not a completeness score",
              "references": REFERENCES, "rows": rows, "ds_usage": {
                  "model_calls": len(calls), "prompt_tokens": sum(x["usage"]["prompt_tokens"] for x in calls),
                  "completion_tokens": sum(x["usage"]["completion_tokens"] for x in calls),
                  "fetch_calls": 1, "credential_source": "existing Windows DPAPI configuration", "billing_verified": False},
              "target_fetch": json.loads((OUT / "deepseek-fetch" / "lzjtu" / "result.json").read_text(encoding="utf-8"))}
    save(OUT / "summary.json", result)
    with (OUT / "comparison.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    save(HERE / "summary.json", result)
    return result


def reviewed_delivery():
    destination = OUT / "teacher-results"
    destination.mkdir(parents=True, exist_ok=True)
    records = []
    for index, sample in enumerate(SAMPLES, 1):
        folder = destination / f"{index:04d}"
        folder.mkdir(exist_ok=True)
        if sample["id"] == "lzjtu":
            source = OUT / "deepseek-fetch" / "lzjtu"
            provider = json.loads((source / "provider-response.json").read_text(encoding="utf-8"))
            markdown = (source / "provider-content.md").read_text(encoding="utf-8")
            converted = MarkdownIt("commonmark").enable("table").render(markdown)
            data = ("<h1>" + html.escape(provider.get("title", "")) + "</h1>" + converted).encode()
            row = extract_html(data, sample["url"])
            # The three basic values were checked against provider source text.
            row.update(name="王平", title="副教授", email="wangp@mail.lzjtu.cn")
            row["research"] = "智能交通系统、复杂网络分析、人工智能、交通大数据挖掘、自动驾驶"
            split = row["biography"].split("七、 论文、专著、专利", 1)
            row["publications"] = split[-1] if len(split) == 2 else ""
            row["warnings"].append("provider_text_only_origin_html_unavailable")
            row["source_mode"] = "deepseek_fetch_provider_text"
            row["error"] = {"code": "http_412", "message": "Local origin access failed; only provider text is available"}
            observed_at = datetime.fromtimestamp((source / "provider-response.json").stat().st_mtime, timezone.utc).isoformat()
            source_name = "source.md"
            (folder / source_name).write_text(markdown, encoding="utf-8")
            shutil.copy2(source / "provider-response.json", folder / "provider-response.json")
            school, college = "", ""
        else:
            source = OUT / "browser" / sample["id"] / "source.html"
            plan = json.loads((OUT / "ds" / sample["id"] / "result.json").read_text(encoding="utf-8"))
            row = extract_html(source.read_bytes(), sample["url"], selector=plan["body_selector"])
            reference = REFERENCES[sample["id"]]
            # Reviewed website values, not a claim of fully automatic accuracy.
            row.update({key: reference[key] for key in ("name", "title", "email")})
            row["reviewed_model_evidence"] = plan["field_evidence"]
            row["source_mode"] = "browser_html_with_DS_selector_and_review"
            observed_at = json.loads((OUT / "browser" / sample["id"] / "result.json").read_text(encoding="utf-8"))["observed_at"]
            row["warnings"].append("fields_reviewed_against_source")
            if sample["id"] == "ncepu":
                row["warnings"].append("model_rank_included_tutor_qualification_corrected_in_review")
            source_name = "source.html"
            shutil.copy2(source, folder / source_name)
            school, college = reference["school"], reference["college"]
        (folder / "biography.txt").write_text(row["biography"], encoding="utf-8")
        (folder / "page.txt").write_text(row.pop("page_text"), encoding="utf-8")
        (folder / "content.html").write_text(row.pop("content_html"), encoding="utf-8")
        row.update(requested_url=sample["url"], status="text_saved_agent_reviewed_experiment", review_required=True,
                   completeness="not_verified", observed_at=observed_at, source_file=f"{index:04d}/{source_name}",
                   biography_file=f"{index:04d}/biography.txt",
                   field_status={"name": "agent_reviewed_candidate", "title": "agent_reviewed_candidate", "email": "agent_reviewed_candidate"},
                   input_metadata={"school": school, "college": college, "collector": "自动采集"})
        save(folder / "record.json", row)
        records.append(row)
    save(destination / "teachers.json", records)
    columns = ["姓名", "职称", "邮箱", "学校", "学院", "简介", "研究方向", "发表信息", "来源模式", "简介文件", "原件文件"]
    with (destination / "teachers.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(columns)
        for row in records:
            writer.writerow([csv_value(value) for value in [row["name"], row["title"], row["email"],
                             row["input_metadata"]["school"], row["input_metadata"]["college"], row["biography"],
                             row["research"], row["publications"], row["source_mode"], row["biography_file"], row["source_file"]]])
    for school in dict.fromkeys(row["input_metadata"]["school"] for row in records):
        school_folder = destination / (school or "学校待核实")
        school_folder.mkdir(exist_ok=True)
        group = [json.loads(json.dumps(row)) for row in records if row["input_metadata"]["school"] == school]
        for row in group:
            row["biography_file"] = "../" + row["biography_file"]
            row["source_file"] = "../" + row["source_file"]
        export_tables(school_folder, group)
    print(json.dumps({"reviewed_teacher_records": len(records), "output": str(destination)}, ensure_ascii=False))


if __name__ == "__main__":
    replay_fixed()
    result = summary()
    reviewed_delivery()
    print(json.dumps(result["ds_usage"], ensure_ascii=False))
