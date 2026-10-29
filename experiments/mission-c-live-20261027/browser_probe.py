"""Bounded normal-browser probe for the user-supplied public homepage."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Mission C"))
from mission_c.fetch import Fetcher
from mission_c.render import render_page
from mission_c.extract import extract_html

URL = "https://jtys.lzjtu.edu.cn/info/1113/4365.htm"
OUT = Path(r"D:\Agent Workspace\Intern\MyPlan\OpenSource\Mission C\outputs\live-tools-20261027\lzjtu-browser-original")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    result_file = OUT / "probe.json"
    if result_file.exists():
        result = json.loads(result_file.read_text(encoding="utf-8"))
    else:
        fetcher = Fetcher()
        try:
            fetcher.check_robots(URL)
            data, metadata = render_page(URL, OUT, fetcher)
            result = {"url": URL, **metadata, "sha256": hashlib.sha256(data).hexdigest(),
                      **extract_html(data, URL)}
        except Exception as error:
            result = {"url": URL, "error_type": type(error).__name__,
                      "error_code": getattr(error, "code", ""), "message": str(error)}
        finally:
            fetcher.close()
        result_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: result.get(key) for key in ("name", "title", "email", "warnings", "content_selection", "error_type", "error_code", "message")}, ensure_ascii=False))
    text = result.get("biography", "")
    print(json.dumps({"characters": len(text), "start": text[:350], "end": text[-350:]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
