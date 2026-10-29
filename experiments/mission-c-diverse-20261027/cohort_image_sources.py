"""Save only the four image-biography sources linked in the two fixed pages."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Mission C"))
from mission_c.fetch import Fetcher


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fetcher = Fetcher(timeout=15, delay=0.5)
    try:
        for sample_id, expected_count in (("n11_chnu_zhanghongyan", 3), ("n12_chnu_baoxiangzhi", 1)):
            folder = args.output / sample_id
            metadata = folder / "image-sources.json"
            if metadata.exists():
                continue
            run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
            soup = BeautifulSoup((folder / "cli/0001/source.html").read_bytes(), "html.parser")
            images = soup.select(".conTxt img")
            if len(images) != expected_count:
                raise ValueError("Current source differs from reviewed image count; inspect before reading")
            records = []
            for index, image in enumerate(images, 1):
                url = urljoin(run["url"], image["src"])
                row = {"url": url, "observed_at": datetime.now(timezone.utc).isoformat(), "state": "attempt_started"}
                records.append(row)
                metadata.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
                try:
                    data, response = fetcher.get(url, allowed_host=urlsplit(run["url"]).netloc)
                    target = folder / f"image-original-{index}{Path(urlsplit(url).path).suffix}"
                    target.write_bytes(data)
                    row.update(response, state="source_saved", source_file=target.name,
                               bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
                except Exception as error:
                    row.update(state="read_failed", error=getattr(error, "code", type(error).__name__))
                metadata.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        fetcher.close()


if __name__ == "__main__":
    main()
