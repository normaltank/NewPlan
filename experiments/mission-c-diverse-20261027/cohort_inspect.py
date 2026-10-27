"""Independent source inventory, deliberately not using mission_c.extract.

Counts are structural clues, never claims of dynamic rendering or completeness.
"""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inventory = []
    for sample in json.loads(args.manifest.read_text(encoding="utf-8"))["samples"]:
        folder = args.output / sample["id"]
        source = folder / "cli/0001/source.html"
        row = {"id": sample["id"], "url": sample["url"], "original_available": source.exists()}
        if source.exists():
            data = source.read_bytes()
            soup = BeautifulSoup(data, "html.parser")
            row.update(source_sha256=hashlib.sha256(data).hexdigest(), source_bytes=len(data),
                title=soup.title.get_text(" ", strip=True) if soup.title else "",
                counts={tag: len(soup.select(tag)) for tag in ["table", "iframe", "script", "img", "[role=tab]", "h1", "h2", "h3"]},
                headings=[{"tag": h.name, "text": h.get_text(" ", strip=True)} for h in soup.select("h1,h2,h3,h4")],
                links=[{"text": a.get_text(" ", strip=True), "url": urljoin(sample["url"], a["href"])}
                       for a in soup.select("a[href]")],
                media=[{"tag": a.name, "src": urljoin(sample["url"], a.get("src") or a.get("data") or a.get("pdfsrc") or ""),
                        "alt": a.get("alt", ""), "id": a.get("id", "")} for a in soup.select("img,iframe,embed,object")])
            for tag in soup.select("script,style"):
                tag.decompose()
            (folder / "independent-source-text.txt").write_text(soup.get_text("\n", strip=True), encoding="utf-8")
        (folder / "source-inventory.json").write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
        inventory.append(row)
    (args.output / "source-inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
