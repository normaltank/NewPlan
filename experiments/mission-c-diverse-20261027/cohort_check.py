"""Compare independent hand-read source anchors with the unmodified CLI output.

Passing anchors shows only those passages survived; it cannot certify full text.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

from bs4 import BeautifulSoup


def compact(text):
    return re.sub(r"\s+", "", text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--references", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    checks = []
    for reference in json.loads(args.references.read_text(encoding="utf-8"))["samples"]:
        folder = args.output / reference["id"]
        row = {"id": reference["id"], "basis": reference["basis"], "gaps": reference["gaps"]}
        source = folder / "cli/0001/source.html"
        if source.exists() and reference["basis"] == "cli/0001/source.html":
            raw = source.read_bytes()
            soup = BeautifulSoup(raw, "html.parser")
            for tag in soup.select("script,style"):
                tag.decompose()
            source_text = compact(soup.get_text(" ", strip=True))
            record = json.loads((folder / "cli/teachers.json").read_text(encoding="utf-8"))[0]
            row.update(source_sha256=hashlib.sha256(raw).hexdigest(), final_url=record["final_url"],
                source_verified=True, fields={key: {"expected": value, "observed": record.get(key),
                    "matches": record.get(key) == value} for key, value in reference["expected_fields"].items()},
                anchors=[{**anchor, "present_in_source": compact(anchor["text"]) in source_text,
                    "preserved_in_biography": compact(anchor["text"]) in compact(record["biography"])}
                    for anchor in reference["anchors"]],
                visual_references=[{**anchor, "preserved_in_biography": compact(anchor["text"]) in compact(record["biography"])}
                    for anchor in reference.get("visual_references", [])])
        else:
            row.update(source_verified=False, fields={}, anchors=[], status="no_local_original")
        checks.append(row)
    destination = args.output / "reference-checks.json"
    destination.write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding="utf-8")
    for row in checks:
        print(json.dumps({"id": row["id"], "source_verified": row["source_verified"],
            "fields": row["fields"], "anchors": row["anchors"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
