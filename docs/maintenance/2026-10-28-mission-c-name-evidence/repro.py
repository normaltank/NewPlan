import argparse, hashlib, json, subprocess, sys
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument("--collector", required=True)
p.add_argument("--output", required=True)
a=p.parse_args()
root=Path(a.output); root.mkdir(parents=True, exist_ok=False)
sources=Path(r"D:\Agent Workspace\Intern\MyPlan\OpenSource\Mission C\outputs\diverse-pages-20261027\cohort")
cases=[("n01_ustc_weizian","https://faculty.ustc.edu.cn/weizian/zh_CN/index.htm","卫子安"),("n03_nju_zhouzh","https://cs.nju.edu.cn/zhouzh/","Zhi-Hua Zhou")]
results=[]
for sid,url,want in cases:
    source=sources/sid/"cli/0001/source.html"
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    run=subprocess.run([sys.executable,a.collector,"--url",url,"--html",str(source),"--output",str(root/sid)],capture_output=True,text=True,encoding="utf-8",timeout=30)
    (root/(sid+"-cli.txt")).write_text(run.stdout+"\n"+run.stderr,encoding="utf-8")
    row=json.loads((root/sid/"teachers.json").read_text(encoding="utf-8"))[0]
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before
    item={"id":sid,"expected":want,"actual":row["name"],"passed":row["name"]==want,"source_sha256":before,"cli_exit":run.returncode}
    results.append(item); print(json.dumps(item,ensure_ascii=False))
(root/"repro.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
raise SystemExit(0 if all(r["passed"] for r in results) else 1)
