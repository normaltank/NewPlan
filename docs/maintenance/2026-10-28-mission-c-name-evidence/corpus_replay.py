import argparse, hashlib, json, subprocess, sys
from pathlib import Path
p=argparse.ArgumentParser(); p.add_argument("--before",required=True); p.add_argument("--after",required=True); p.add_argument("--output",required=True); p.add_argument("--manifest",required=True); a=p.parse_args()
out=Path(a.output); out.mkdir(parents=True,exist_ok=False)
base=Path(r"D:\Agent Workspace\Intern\MyPlan\OpenSource\Mission C\outputs")
new=base/"diverse-pages-20261027/cohort"; old=base/"live-tools-20261027/browser"
cases=[(x["id"],x["url"],"Zhi-Hua Zhou" if x["id"]=="n03_nju_zhouzh" else x["expected_name"],new/x["id"]/"cli/0001/source.html") for x in json.loads(Path(a.manifest).read_text(encoding="utf-8"))["samples"]]
cases += [("old_suda","https://web.suda.edu.cn/hj1/","何剑",old/"suda/source.html"),("old_ncepu","https://electric.ncepu.edu.cn/szdw/jsxx/gdyyjyjsyjs/a207300faea944298a27ba0a6d0c6c7b.htm","王健",old/"ncepu/source.html"),("old_shu","https://physics.shu.edu.cn/info/1082/5653.htm","张惠芳",old/"shu/source.html"),("old_ecnu","https://faculty.ecnu.edu.cn/_s41/lyq2/main.psp","李艳青",old/"ecnu/source.html")]
rows=[]
for sid,url,want,source in cases:
 if not source.exists(): continue
 digest=hashlib.sha256(source.read_bytes()).hexdigest()
 records={}
 for phase,collector in [("before",a.before),("after",a.after)]:
  run=subprocess.run([sys.executable,collector,"--url",url,"--html",str(source),"--output",str(out/phase/sid)],capture_output=True,text=True,encoding="utf-8",timeout=30)
  (out/(phase+"-"+sid+".txt")).write_text(run.stdout+"\n"+run.stderr,encoding="utf-8")
  records[phase]=json.loads((out/phase/sid/"teachers.json").read_text(encoding="utf-8"))[0]
 b,n=records["before"],records["after"]
 row={"id":sid,"reference_name":want,"before":b["name"],"after":n["name"],"name_regression":b["name"]==want and n["name"]!=want,"biography_unchanged":b["biography"]==n["biography"],"source_sha256":digest}
 assert hashlib.sha256(source.read_bytes()).hexdigest()==digest
 rows.append(row); print(json.dumps(row,ensure_ascii=False),flush=True)
(out/"comparison.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")
raise SystemExit(int(any(x["name_regression"] or not x["biography_unchanged"] for x in rows)))
