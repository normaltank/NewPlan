"""Offline audit and readable exports for the FYNU pilot; never modifies raw records."""
import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from bs4 import BeautifulSoup


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


def main(out):
    pages=read(out/'pages.json')
    observations=read(out/'observations.json')
    summary=read(out/'summary.json')
    source_by_url={p['url']:p for p in pages}
    roster_audit=[]
    label_dates={}
    for p in pages:
        raw=(out/p['directory']/'source.html').read_bytes()
        assert hashlib.sha256(raw).hexdigest()==p['sha256'],p['url']
        if p['kind']!='roster':
            continue
        soup=BeautifulSoup(raw,'lxml')
        for row in soup.select('div.new_list3 dl dd'):
            a=row.select_one('a.fl')
            if a:
                match=re.search(r'\d{4}-\d{2}-\d{2}',row.get_text(' ',strip=True))
                label_dates[(p['url'],a.get_text(' ',strip=True))]=match[0] if match else ''
        # Offline correction: the collection's pager metadata omitted disabled last-page controls.
        pager=next((t for t in soup.select('.container_right table')
                    if t.select('a.Next,span.PrevDisabled,span.NextDisabled')),None)
        text=pager.get_text(' ',strip=True) if pager else ''
        match=re.search(r'共\s*(\d+)\s*条\s*(\d+)\s*/\s*(\d+)',text)
        roster_audit.append({'url':p['url'],'branch':p['branch'],'pager_text':text,
                             'declared_total':int(match[1]) if match else None,
                             'page':int(match[2]) if match else 1,
                             'page_count':int(match[3]) if match else 1,
                             'next_disabled':bool(pager and pager.select('span.NextDisabled')),
                             'next_link_count':len([a for a in soup.select('.container_right a.Next[href]')
                                                   if a.get_text(strip=True)=='下页'])})
    for branch in ['硕士生导师','博士团队','教师队伍']:
        rows=[r for r in roster_audit if r['branch']==branch]
        assert sorted(r['page'] for r in rows)==list(range(1,rows[0]['page_count']+1)),branch
        tail=next(r for r in rows if r['page']==r['page_count'])
        assert tail['next_disabled'] and not tail['next_link_count'],branch
    observed=defaultdict(list)
    by_profile=defaultdict(list)
    for i,o in enumerate(observations,1):
        o=dict(o,observation_id=i,listed_date=label_dates.get((o['source_url'],o['label']),''))
        observed[o['name']].append(o)
        if o['profile_url']:
            by_profile[o['profile_url']].append(o)
    profile_records=[]
    for p in pages:
        if p['kind']!='profile':
            continue
        textpath=out/p['directory']/'body-text.txt'
        text=textpath.read_text(encoding='utf-8') if textpath.exists() else ''
        if p['body_chars'] if 'body_chars' in p else 0:
            assert len(text)==p['body_chars']
        page_text=(out/p['directory']/'page-text.txt').read_text(encoding='utf-8')
        status='已保存正文' if text else ('官网提示无权访问' if '您无权访问此页面' in page_text else '未取得正文')
        names=sorted({o['name'] for o in by_profile[p['url']]})
        title_hit=[name for name in names if name in re.sub(r'\s+','',p['title'])]
        profile_records.append({'names':names,'status':status,'chars':len(text),'page_title':p['title'],
                                'title_name_match':title_hit,'profile_url':p['url'],
                                'loaded_url':p['loaded_url'],'http_status':p['status'],
                                'raw_path':str((out/p['directory']/'source.html').resolve()),
                                'body_path':str(textpath.resolve()) if text else '',
                                'email_candidates':p.get('email_candidates',[]),
                                'title_candidates':p.get('title_candidates',[]),
                                'source_rosters':sorted({o['source_url'] for o in by_profile[p['url']]}),
                                'sha256':p['sha256'],'retrieved_at':p['retrieved_at']})
    profiles_by_url={p['profile_url']:p for p in profile_records}
    name_index=[]
    for name,rows in observed.items():
        urls=sorted({r['profile_url'] for r in rows if r['profile_url']})
        records=[profiles_by_url[u] for u in urls if u in profiles_by_url]
        valid=[p for p in records if p['chars'] and name in p['title_name_match']]
        denied=[p for p in records if p['status']=='官网提示无权访问']
        status='有对应标题的正文' if valid else ('链接无权访问' if denied else '仅名单姓名')
        name_index.append({'name':name,'status':status,'branches':sorted({r['branch'] for r in rows}),
                           'profile_urls':urls,'body_pages':len(valid),'denied_pages':len(denied),
                           'observations':len(rows),'source_urls':sorted({r['source_url'] for r in rows}),
                           'listed_dates':sorted({r['listed_date'] for r in rows if r['listed_date']}),
                           'body_paths':[p['body_path'] for p in valid]})
    name_index.sort(key=lambda r:({'链接无权访问':0,'仅名单姓名':1,'有对应标题的正文':2}[r['status']],r['name']))
    profiles_status=Counter(p['status'] for p in profile_records)
    names_status=Counter(n['status'] for n in name_index)
    pdf_names={n for n,rows in observed.items() if any(o['source_kind']=='pdf_name' for o in rows)}
    html_names={n for n,rows in observed.items() if any(o['source_kind']!='pdf_name' for o in rows)}
    branch_counts=Counter(o['branch'] for o in observations)
    audit={'raw_page_hashes_checked':len(pages),'profile_status_counts':dict(profiles_status),
           'name_index_status_counts':dict(names_status),'branch_observations':dict(branch_counts),
           'distinct_names':len(name_index),'pdf_only_names':sorted(pdf_names-html_names),
           'html_only_names':sorted(html_names-pdf_names),
           'profiles_with_unmatched_title':[p['profile_url'] for p in profile_records if p['chars'] and not p['title_name_match']],
           'roster_pages':roster_audit,'identity_merge_performed':False,
           'whole_college_completeness':'unverified'}
    write(out/'audit.json',audit)
    write(out/'name-index.json',name_index)
    write(out/'profile-records.json',profile_records)
    enriched=[o for rows in observed.values() for o in rows]
    enriched.sort(key=lambda r:r['observation_id'])
    write(out/'observations-enriched.json',enriched)
    report=[
        '# 阜阳师范大学化学与材料工程学院：开源采集试验', '',
        '采集日期：2026-10-14。入口：https://www.fynu.edu.cn/hxycl/ 。采集输出独立保存，未写入生产库。', '',
        f'取得 {len(name_index)} 个不同姓名的名单观察，其中 {names_status["有对应标题的正文"]} 个姓名至少有一份标题对应的公开正文。这里的姓名索引用于查阅，不代表已确认当前在职人数；不按同名合并简介或字段。', '',
        '| 来源 | 取得的范围 | 核对依据 |', '|---|---|---|',
        '| 教授团队 | 1页，34个姓名 | 逐段保留文本，9个条目在该页没有链接 |',
        '| 硕士生导师 | 6页，51条个人链接 | 官网共51条，6/6末页，下一页禁用 |',
        '| 博士团队 | 7页，65条文章：64条个人链接、1条汇总名单 | 官网共65条，7/7末页，下一页禁用 |',
        '| 教师队伍 | 2页，18条文章：17条姓名、1条2016年考核公示 | 官网共18条，2/2末页，下一页禁用；不是18名新教师 |',
        '| 博士汇总PDF | 1页，113个姓名 | 原件写明“数据统计至2025年9月”，已渲染核对 |', '',
        f'四个栏目共16个名单页面。原始名单观察{len(observations)}条，保留重复来源。PDF补充了{len(pdf_names-html_names)}个未出现在HTML姓名条目中的姓名。', '',
        '## 个人页拿到了什么', '',
        f'- 跟进{len(profile_records)}个不同个人链接：{profiles_status["已保存正文"]}页保存正文，{profiles_status["官网提示无权访问"]}页返回官网“您无权访问此页面”。',
        f'- 按姓名索引看：{names_status["有对应标题的正文"]}个姓名有对应标题正文，{names_status["链接无权访问"]}个姓名只有受限链接，{names_status["仅名单姓名"]}个姓名只有名单信息。',
        f'- 保存原始HTML、来源、抓取时间、SHA256、正文HTML与全文文本。已逐文件复核{len(pages)}份集合内HTML哈希。正文“完整”仅指保留选中容器全文，不等于人工核验了完整个人履历。',
        '- 图片URL保留，但头像、个人页图片及其他附件未逐一下载；本轮单独下载并解析的是博士汇总PDF。',
        '- 邮箱和职称只做候选提取，未逐字段核验归属，不作为最终交付字段。', '',
        '## 访问限制与缺口', '',
        '受限页面在普通HTTP下最终返回200，但实际跳转到学校的权限提示页，因此不计作取得简介。Crawl4AI + Edge抽查郝扶影受限链接，仍出现相同权限提示；公开的凡素华页面作为对照可读取。Crawl4AI将小型错误页标作anti-bot，是工具启发式，不能据此断定学校部署了反爬。没有尝试登录或绕过权限。', '',
        '“教师队伍”栏目还包含2016年考核公示，其正文补查同样提示无权访问。历史栏目日期保留在来源观察中；栏目出现某姓名不单独证明当前任职。', '',
        f'本轮未取得对应正文的姓名：{ "、".join(n["name"] for n in name_index if n["status"]!="有对应标题的正文") }。', '',
        '学院概况写145名教职工，博士PDF写113人且日期为2025年9月，几个栏目的范围和更新时间不同。不能将这些总数直接相减作为漏采人数。全院完整性未验证。', '',
        '## 这次试验说明什么', '',
        '常规HTML、链接翻页和文本型PDF可以用现有开源模块组合取得；本例不需要为每个姓名调用模型。真正需要补充的获取路径是无链接姓名、权限受限内容及可能存在的其他公开来源。增加正文清理规则不会解决这些缺口。', '',
        '本轮由agent确认首页入口、名单选区、富文本姓名分隔方式和PDF链接，脚本按真实分页运行。它是单站适配试验，不是跨学院自动发现能力验证。', '',
        f'Crawlee 1.10.4负责HTTP队列；Crawl4AI 0.9.4负责CSS规则提取和浏览器抽查；Trafilatura 2.3.1保留作正文提取对照。主批次{summary["seconds"]}秒（复用8份预采页面，另抓143页），串行、请求前等待2秒、启用robots规则及ThrottlingRequestManager。采集脚本没有调用LLM；不包括本次agent阅读/适配的成本。', '',
        '## 文件', '',
        '- `name-index.json`：姓名查阅索引；`profile-records.json`：每个链接的实际获取状态。',
        '- `observations.json`：原始名单观察；`observations-enriched.json`：增加列表日期的离线结果。',
        '- `pages.json`、每页目录：原件与来源；`doctor-pdf/`：PDF原件、提取文本和渲染图。',
        '- `audit.json`：哈希、姓名/链接对应、分页核对；`records.md`：可点击姓名及本地正文。',
        '- 原始`summary.json`、`roster-pages.json`保留运行时事实；末页控件状态在`audit.json`依据原件补核。原运行的末页识别漏了`NextDisabled`，未漏翻页或条目；适配器已修正。',
    ]
    (out/'report.md').write_text('\n'.join(report),encoding='utf-8')
    records=['# 姓名查阅索引','','姓名相同只用于查阅聚合，不合并不同个人页的身份、正文或字段。','','| 姓名 | 状态 | 来源栏目 | 个人页与正文 |','|---|---|---|---|']
    for row in name_index:
        links=[]
        for i,url in enumerate(row['profile_urls'],1):
            p=profiles_by_url.get(url)
            links.append(f'[官网{i}]({url})')
            if p and p['body_path']:
                path=Path(p['body_path']).relative_to(out).as_posix()
                links.append(f'[正文{i}]({path})')
        records.append(f'| {row["name"]} | {row["status"]} | {"、".join(row["branches"])} | {" / ".join(links) or "名单文字，无个人链接"} |')
    (out/'records.md').write_text('\n'.join(records),encoding='utf-8')
    print(json.dumps({k:v for k,v in audit.items() if k!='roster_pages'},ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('run',type=Path)
    main(parser.parse_args().run.resolve())
