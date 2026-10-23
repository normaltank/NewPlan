"""Audit captured evidence and summarize latest runs without accepting faculty identities."""
import hashlib
import json
from collections import Counter
from pathlib import Path
from workbench_store import ROOT,Store,read_json,now


def report():
    store=Store(ROOT/'runs'/'workbench'/'workbench.db')
    overview=store.listing()
    batch=next(b for b in overview['batches'] if '11' in b['name'])
    jobs=[j for j in overview['jobs'] if j['batch_id']==batch['id']]
    latest=[j for j in jobs if not any(k['parent_id']==j['id'] for k in jobs)]
    total=Counter();calls=0;missing_usage=0;failed_calls=0
    run_usage=[]
    for job in jobs:
        if not job['run_dir']:continue
        entries=read_json(Path(job['run_dir'])/'api'/'calls.json',[])
        calls+=len(entries)
        usage=Counter()
        for entry in entries:
            failed_calls+=int(entry.get('status')!=200)
            missing_usage+=int(not entry.get('usage'))
            usage.update({k:v for k,v in entry.get('usage',{}).items() if isinstance(v,int)})
        total.update(usage)
        run_usage.append({'job':job['id'],'college':job['target']['college'],'run_dir':job['run_dir'],'calls':len(entries),'usage':dict(usage)})
    cost=(total['prompt_cache_hit_tokens']*.006+total['prompt_cache_miss_tokens']*.30+total['completion_tokens']*1.20)/1e6
    records=[];mismatches=[];checks=Counter();body_blank=[]
    for job in latest:
        cat=store.catalog(job['id'])
        root=Path(job['run_dir']) if job['run_dir'] else None
        for kind,items in [('html',cat['pages']),('image',cat['media']),('pdf',cat['documents'])]:
            for item in items:
                file=root/item['directory']/'source.html' if kind=='html' else (root/item['directory']/item['source_file'] if kind=='image' else root/item['path']/'source.pdf')
                actual=hashlib.sha256(file.read_bytes()).hexdigest() if file.is_file() else None
                checks[kind]+=1
                if actual!=item.get('sha256'):mismatches.append({'job':job['id'],'path':str(file),'expected':item.get('sha256'),'actual':actual})
        statuses=Counter(p.get('body_status','not_read') for p in cat['pages'] if p['kind']=='profile')
        bodies=sum(p.get('body_chars',0)>0 for p in cat['pages'] if p['kind']=='profile')
        for p in cat['pages']:
            if p.get('body_chars',0)>0:
                file=root/p['directory']/'body-text.txt'
                if not file.is_file() or not file.read_text(encoding='utf8').strip():body_blank.append(str(file))
        counts=Counter(i['issue_kind'] for i in cat['issues'])
        records.append({'job_id':job['id'],'college':job['target']['college'],'state':job['state'],
            'different_names':len({p['name'] for p in cat['people']}),'candidate_records':len(cat['people']),
            'html_pages':len(cat['pages']),'roster_pages':len(cat['rosters']),'body_pages':bodies,
            'images':len(cat['media']),'pdfs':len(cat['documents']),
            'scanned_pdf_pages':sum(d.get('ocr_pages',0) for d in cat['documents']),
            'body_status':dict(statuses),'issues':dict(counts),'review_url':'http://127.0.0.1:8767/review/'+job['id'],
            'run_dir':job['run_dir'],'completeness':'unverified'})
    result={'created_at':now(),'batch':batch,'latest':records,'all_runs':run_usage,'api_calls':calls,
            'failed_api_calls':failed_calls,'calls_without_usage':missing_usage,'usage':dict(total),
            'estimated_usd_peak':round(cost,6),'actual_bill_checked':False,
            'pricing_snapshot':'2026-10-14: hit .006/million; miss .30/million; output 1.20/million USD',
            'raw_sha256_checked':dict(checks),'raw_sha256_mismatches':mismatches,'missing_or_blank_bodies':body_blank,
            'all_latest_runs_stopped':all(j['state'] not in ('running','queued') for j in latest),
            'whole_college_completeness':'unverified','cross_college_identity_merge_performed':False}
    folder=ROOT/'runs'/'nantong-workbench-report';folder.mkdir(exist_ok=True)
    (folder/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    lines=['# 南通大学11学院试采与工作台验证','',
        '本批用于开发、发现问题和复跑，不是冻结版本后的未见验证集。所有真实人员尚未由实习生复核；全院完整性未验证。不同姓名数不等于确认教师人数，同名不同个人URL保留独立候选。',
        '', '| 学院 | 运行 | 不同姓名 | 候选记录 | 正文页 | 图片 | PDF | 复核入口 |','|---|---|---:|---:|---:|---:|---:|---|']
    for r in records:
        lines.append(f"| {r['college']} | {r['state']} | {r['different_names']} | {r['candidate_records']} | {r['body_pages']} | {r['images']} | {r['pdfs']} | [打开]({r['review_url']}) |")
    lines+=['','正文页指已保存文本的个人页面，可能含OCR候选或PDF全文，不说明身份、归属或全文准确性已人工确认。图片数包含照片，不能将照片上的少量识别文字当作图片简历验收。纯图片简介通过隔离图像样本测试；本批机械工程学院实际取得3份单页扫描PDF并完成OCR，原图、逐行坐标和置信度已保存。',
        '', '## 本批API用量',f'- 全部运行累计 {calls} 次 chat/completions 调用，输入 {total["prompt_tokens"]} token，输出 {total["completion_tokens"]} token，合计 {total["total_tokens"]} token。',
        f'- 按2026-10-14记录的峰时价格估算 ${cost:.6f}；实际账单未核对。包括失败、调试和恢复运行；OCR在本地执行，没有另调用视觉API。',
        f'- 无 usage 返回的调用 {missing_usage} 次，HTTP非200或尚未结束 {failed_calls} 次；各次用量见 audit.json。',
        '', '## 原件验证',f'- SHA256核对：{dict(checks)}；不匹配 {len(mismatches)}；标为有正文但文件空白/缺失 {len(body_blank)}。',
        '- 原始HTTP字节、图片、PDF分别核验。渲染HTML是独立DOM材料；早期版本的rendered_sha256基于规范化UTF-8文本，Windows换行转换后不应冒充文件字节哈希，后续代码已统一写UTF-8字节。',
        '', '## 本轮暴露并处理的问题',
        '- 三学院同时启动时微秒时间戳重名：运行目录追加随机标识，保留失败历史并重跑。',
        '- 读取界面与原子JSON写入触发Windows短暂文件锁：增加有界重试。医学院另建恢复运行，复用原件并补读达到图片上限或未完成的页面。',
        '- 商学院名单通过JavaScript加载：空列表转浏览器渲染，保留原始HTML和渲染DOM。',
        '- 机械、张謇个人页为PDF阅读器：解析实际PDF地址并读取全文，支持扫描页OCR。播放器HTML误当PDF请求的旧记录仍保留；实际PDF已保存的对应事件不计为人工待办。',
        '- 姓名附带导师身份或邮箱说明：提取姓名后保留原始标签，不能丢掉该条人员。',
        '- 继续教育“任课老师”栏目实际是文件下载：增加入口导航语境与页面用途核对，旧表格标题误识别名单保留，新结果不把表格当作教师。',
        '- HTTP/HTTPS重复URL统一到学院首页的HTTPS；不同个人URL的同名记录仍分开，不进行无证据身份合并。',
        '', '## 仍需复核的范围']
    for r in records:
        lines += [f"### {r['college']}",f"原件目录：`{r['run_dir']}`。",f"待核类型：`{json.dumps(r['issues'],ensure_ascii=False)}`。",'']
    lines+=['护理与康复的师资页给出约150名专兼职教职工的概况，但本轮未取得逐人名录。国际教育未发现可靠师资入口。继续教育的下载分类被识别为非师资用途。三个零人员结果都需要人工找入口或依据官网确认范围，不能等同于无师资。',
        '', '## 工作台验证与部署状态',
        '- 22项隔离测试覆盖来源资格、翻页失效、纯图片下载/OCR/原件保存、扫描PDF、身份和归属确认、空字段原因、同名分离、并发版本冲突、结论失效、重采保留、原件越界和CSV公式转义。',
        '- 浏览器隔离样本走通确认人员、学院对账保存、补充人员后撤回学院完整性、筛选、问题表单和390px窄屏显示。未给真实学院批量写入人工确认。',
        '- 最新页面和复核后端运行在 http://127.0.0.1:8767（review-only，不启动第二组采集进程）；原8765服务继续负责采集队列，两个服务连接同一数据库。原服务重启被自动审批拦截，采用新增复核服务的方式完成更新。夜间CLI和可选定时入口已提供；没有启用每日计划、部署远程服务器或接入外部推送。当前署名不是登录认证，服务器多人部署仍需配置。',
        '- 运行资料和凭据目录被Git忽略。本轮没有提交、推送或部署NewPlan仓库。']
    (folder/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    print(json.dumps({'report':str(folder/'report.md'),'stopped':result['all_latest_runs_stopped'],
                      'calls':calls,'cost':round(cost,6),'hash_mismatches':len(mismatches),'checks':dict(checks)},ensure_ascii=False))

if __name__=='__main__':report()
