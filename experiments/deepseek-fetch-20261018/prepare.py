"""Freeze existing implementation and cases without touching the live workbench."""
import hashlib
import json
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent.parent
RUNTIME = ROOT / "runtime"


def main():
    RUNTIME.mkdir(exist_ok=True)
    manifest = {}
    for path in sorted(SOURCE.glob("*.py")):
        if path.name.startswith(("test_", "github-")):
            continue
        data = path.read_bytes()
        destination = RUNTIME / path.name
        if destination.exists() and destination.read_bytes() != data:
            raise RuntimeError("Existing snapshot differs; create another experiment instead")
        destination.write_bytes(data)
        manifest[path.name] = hashlib.sha256(data).hexdigest()
    for name in ("requirements.txt", "requirements.lock"):
        shutil.copyfile(SOURCE / name, RUNTIME / name)
        manifest[name] = hashlib.sha256((SOURCE / name).read_bytes()).hexdigest()
    for name in ("workbench-static",):
        shutil.copytree(SOURCE / name, RUNTIME / name, dirs_exist_ok=True)
    cases = [
        {"case": "fynu", "university": "阜阳师范大学", "college": "化学与材料工程学院",
         "url": "https://www.fynu.edu.cn/hxycl/", "entries": [], "reason": "常规多分支名单、PDF和受限个人页"},
        {"case": "ntu", "university": "南通大学", "college": "护理与康复学院",
         "url": "https://ntdxhk.ntu.edu.cn/", "entries": ["https://ntdxhk.ntu.edu.cn/xkjs/list.htm"], "reason": "特殊师资页面、多人材料"},
        {"case": "seu", "university": "东南大学", "college": "吴健雄学院",
         "url": "https://wjx.seu.edu.cn/", "entries": ["https://wjx.seu.edu.cn/xyds/list.htm"], "reason": "跨学院教师主页、分散的联系方式"},
    ]
    db = SOURCE / "runs/workbench/workbench.db"
    with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as con:
        con.row_factory = sqlite3.Row
        rows = [dict(row) for row in con.execute("SELECT id,target,state,run_dir,created FROM jobs ORDER BY created")]
        human_rows = [tuple(row) for row in con.execute("SELECT * FROM decisions ORDER BY job_id,item_id")]
    for case in cases:
        matches = [row for row in rows if json.loads(row["target"]).get("college") == case["college"]
                   and row["run_dir"] and row["state"] == "finished"]
        case["historical_comparison"] = matches[-1] if matches else None
    snapshot = {"created": datetime.now(timezone.utc).isoformat(), "source": str(SOURCE),
                "runtime": str(RUNTIME), "files": manifest, "python": sys.version,
                "live_decisions_count": len(human_rows),
                "live_decisions_sha256": hashlib.sha256(json.dumps(human_rows, ensure_ascii=False).encode()).hexdigest()}
    (ROOT / "source-manifest.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf8")
    (ROOT / "cases.json").write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps({"snapshot_files": len(manifest), "cases": len(cases), "human_decisions": len(human_rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
