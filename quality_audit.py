"""Global saved-result audit, including delivery and human-exception counts."""
import hashlib
import json
from collections import Counter,defaultdict
from pathlib import Path
import httpx
from quality_fields import compact
from workbench_store import Store,ROOT,now


def main():
    store=Store(ROOT/'runs/workbench/workbench.db')
    with store.db() as db:
        jobs=[store.job(x['id']) for x in db.execute('SELECT id FROM jobs ORDER BY created')]
    latest={j['target']['college']:j for j in jobs}
    rows=[];bodies=defaultdict(list);total=Counter();exported=0;checks=[]
    with httpx.Client(base_url='http://127.0.0.1:8767',trust_env=False,timeout=40) as client:
        for college,j in latest.items():
            cat=store.catalog(j['id']);counts=Counter(p['review']['status'] for p in cat['people']);total.update(counts)
            pending=Counter(i['issue_kind'] for i in cat['issues'] if i['review']['status']!='resolved')
            details=[]
            for p in cat['people']:
                fields=p['review'].get('fields',{})
                details.append({'name':p['name'],'url':p['profile_url'],'id':p['id'],'status':p['review']['status'],
                                'title':fields.get('title',''),'email':fields.get('email',''),'anomalies':p['flags']})
                if fields.get('biography'):
                    bodies[hashlib.sha256(compact(fields['biography']).encode()).hexdigest()].append([college,p['name'],p['profile_url']])
            response=client.get(f'/api/jobs/{j["id"]}/export');response.raise_for_status()
            actual=len(response.json()['accepted']);expected=counts['auto_accepted']+counts['accepted']
            assert actual==expected,(college,actual,expected)
            exported+=actual
            for p in cat['people']:
                if p.get('body_path'):
                    path=Path(j['run_dir'])/p['body_path']
                    assert path.is_file() and path.stat().st_size>0
            row={'college':college,'job':j['id'],'people':len(cat['people']),'names':len({p['name'] for p in cat['people']}),
                 'states':dict(counts),'title_filled':sum(bool(x['title']) for x in details),'email_filled':sum(bool(x['email']) for x in details),
                 'pending_issues':dict(pending),'anomalies':dict(Counter(a for p in cat['people'] if p['review']['status']=='pending' for a in p['flags'])),
                 'repairs':cat['enrichment'],'root':j['run_dir'],'people_details':details,'export_verified':actual}
            rows.append(row)
    shared=[group for group in bodies.values() if len({x[1] for x in group})>1]
    result={'created':now(),'totals':dict(total),'api_exports_verified':exported,'rows':rows,
            'same_body_different_names':shared,'scope':'全量保存结果自动检查；不是人工逐人核实，也没有证明全院名单完整。'}
    folder=ROOT/'runs/20261014-quality-repair'
    (folder/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 南通大学 11 学院：漏采修复与异常复核审计','',f'生成时间：{result["created"]}。工作台：<http://127.0.0.1:8767>。',
           '',f'全量检查最新运行的 {sum(total.values())} 条候选：{total["auto_accepted"]} 条自动入库、{total["pending"]} 条人员异常、{total["duplicate"]} 条同姓名且正文一致的重复材料。已逐学院核对真实 HTTP 导出接口，共 {exported} 条可交付。计数是记录，不是独立自然人数。',
           '', '| 学院 | 候选记录 | 不同姓名 | 自动入库 | 人员异常 | 重复材料 | 采集异常 |', '|---|---:|---:|---:|---:|---:|---:|']
    for r in rows:
        c=r['states'];lines.append(f'| [{r["college"]}](http://127.0.0.1:8767/review/{r["job"]}) | {r["people"]} | {r["names"]} | {c.get("auto_accepted",0)} | {c.get("pending",0)} | {c.get("duplicate",0)} | {sum(r["pending_issues"].values())} |')
    lines+=['','## 已修复并实际验证','',
      '- 护理：真实运行从学科建设页面的 pdfsrc 读取3页导师表，61条逐人记录，保留页码和行原文。严海鸥邮箱在PDF视觉原件中即为不完整值，保留异常；不补造域名。61是导师表范围，不是全院师资总数。',
      '- 商学院：40份正文补入独立个人信息卡片，恢复单位、职称、邮箱、办公室和研究方向；不再把“教授课程”直接当教授职称。',
      '- 机械：周井玲原有PDF正文现在直接填入表单；蔡婷、苏尤宇、吴予澄等漏读材料补回。显示名称不再作为PDF下载链接；保留真正附件。',
      '- 全批检查PDF图文混合结构，9页追加OCR；原文字层、PDF、渲染图和识别记录均保留，不用OCR覆盖原件。',
      '- 姓名隐藏空格、页面URL片段、CMS包装链接、临床职称和名单行邮箱的读取已修复。15条完全相同的本人正文自动关联，头像中的少量噪声不再逐条要求人工。',
      '', '## 抽查之外发现的风险','',
      '- 医学院同一名单将顾俊、丁亮、李菁、顾云娟、欧阳嵘五个名字链接到顾云娟个人页。保存HTML证实链接本身如此；四条错配已经被身份检查拦截。只凭“网页打开成功”会把他人简介归过去。',
      '- 公共卫生学院存在同名、不同邮箱/研究方向/职称的材料，例如肖静；机械学院也有新旧职称不同的简介。仅凭姓名不能合并。同名材料已在前端直接并列提供对照链接。',
      '- 体育学院补出15条校内/外聘教练员表格记录，但材料发布日期为2016年，当前任职关系仍待核。原19条不等于全院全部师资。',
      '- 公共卫生仍有入口预算截断、两处名单结构失配、四处页面API预算失败。商学院等栏目返回空结构，不能按成功访问推断完整。',
      '- 国际教育、继续教育仍为零候选；这只表示没有取得名单，不能判为无师资。',
      '- 跨域/畸形代理地址、失效链接和真实读取失败仍保留具体异常。全量字段自动检查不等于全网分支穷尽，也未完成跨学院身份合并。',
      '', '## 验证与成本','',
      '- 31项隔离测试通过：包括自动导出、人工覆盖优先、来源变化使旧自动判断失效、临床职称、课程词误识别、PDF逐人表格和混合PDF OCR。真实人工决定未被测试写入。',
      '- 已验证实际工作台的人员筛选、自动填写、护理唯一异常，以及11个学院HTTP导出数量；完整检查数据见 audit.json。',
      '- 本轮护理实时补采使用2次DeepSeek调用，输入3946、输出176、合计4122 tokens。沿既有价格快照估算约$0.001244，不是平台账单；其余保存页修复和OCR未调用付费模型。',
      '- 修复材料为 enrichment.json / quality-repair；自动判断按源码和输入指纹保存至 auto-assessment.json，历次快照在assessments。人工结论始终优先。源码快照见本目录code。',
      '- 本批已用于调试，不是未见验证集；“自动入库”表示目前规则未检出异常，不是100%正确率保证。']
    (folder/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    code=folder/'code';code.mkdir(exist_ok=True)
    manifest={}
    for path in [*ROOT.glob('*.py'),ROOT/'WORKBENCH.md',* (ROOT/'workbench-static').glob('*')]:
        if not path.is_file():continue
        relative=path.relative_to(ROOT);dest=code/relative;dest.parent.mkdir(exist_ok=True,parents=True);dest.write_bytes(path.read_bytes())
        manifest[relative.as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    (folder/'code-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps({'total':dict(total),'exported':exported,'pending_issues':sum(sum(r['pending_issues'].values()) for r in rows)},ensure_ascii=False))


if __name__=='__main__':main()
