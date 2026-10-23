"""Compare a completed API pilot to a prior saved acquisition, after collection only."""
import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main(out,baseline):
    summary=read(out/'summary.json')
    pages=read(out/'pages.json')
    observations=read(out/'observations.json')
    names=read(out/'name-index.json')
    original=read(baseline/'observations.json')
    old_pages={p['url']:p for p in read(baseline/'pages.json')}
    old_names={o['name'] for o in original}
    new_names={o['name'] for o in observations}
    diffs=[]
    body_equal=0
    for p in pages:
        raw=(out/p['directory']/'source.html').read_bytes()
        assert hashlib.sha256(raw).hexdigest()==p['sha256'],p['url']
        if p['kind']=='profile' and p.get('body_chars',0)>0 and p['url'] in old_pages:
            old=old_pages[p['url']]
            old_file=baseline/old['directory']/'body-text.txt'
            new_file=out/p['directory']/'body-text.txt'
            a=old_file.read_text(encoding='utf-8') if old_file.exists() else ''
            b=new_file.read_text(encoding='utf-8')
            if re.sub(r'\s+','',a)==re.sub(r'\s+','',b):
                body_equal+=1
            else:
                diffs.append({'url':p['url'],'old_chars':len(a),'new_chars':len(b)})
    by_branch=defaultdict(list)
    for r in read(out/'roster-pages.json'):
        by_branch[r['branch']].append(r)
    branch_checks=[]
    for branch,rows in by_branch.items():
        declared=[r['declared_total'] for r in rows if r['declared_total'] is not None]
        page_counts=[r['page_count'] for r in rows if r['page_count'] is not None]
        total=sum(r['entries'] for r in rows)
        pages_seen=sorted(r['page'] for r in rows if r['page'] is not None)
        expected=page_counts[0] if page_counts else None
        branch_checks.append({'branch':branch,'pages':len(rows),'entries':total,
                              'declared_total':declared[0] if declared else None,
                              'all_page_numbers_seen':pages_seen==list(range(1,expected+1)) if expected else None,
                              'total_matches':all(d==total for d in declared) if declared else None})
    old_profile_urls={p['url'] for p in old_pages.values() if p['kind']=='profile'}
    new_profile_urls={p['url'] for p in pages if p['kind']=='profile'}
    doc_hashes=[]
    for doc in read(out/'documents.json'):
        digest=hashlib.sha256((out/doc['path']/'source.pdf').read_bytes()).hexdigest()
        assert digest==doc['sha256']
        doc_hashes.append(digest)
    result={'baseline':str(baseline),'name_set_equal':old_names==new_names,
            'missing_names':sorted(old_names-new_names),'extra_names':sorted(new_names-old_names),
            'missing_profile_urls':sorted(old_profile_urls-new_profile_urls),
            'extra_profile_urls':sorted(new_profile_urls-old_profile_urls),
            'equal_body_texts_ignoring_whitespace':body_equal,'body_text_differences':diffs,
            'html_hashes_verified':len(pages),'pdf_hashes_verified':len(doc_hashes),
            'branches':branch_checks,
            'scope_note':'Agreement with one saved pilot is not independent whole-college completeness.'}
    (out/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    labels={'body_saved':'已取得对应正文','permission_denied':'链接无权访问','name_only':'仅名单信息','unresolved':'尚未解决'}
    records=['# API试采姓名索引','','重复来源保留；按姓名索引查阅，不作同名身份合并。','','| 姓名 | 获取情况 | 原始来源 | 本地正文 |','|---|---|---|---|']
    for row in sorted(names,key=lambda n:(n['status']=='body_saved',n['name'])):
        links=' / '.join(f'[来源{i+1}]({url})' for i,url in enumerate(row['sources']))
        bodies=' / '.join(f'[正文{i+1}]({url})' for i,url in enumerate(row['body_paths']))
        records.append(f'| {row["name"]} | {labels[row["status"]]} | {links} | {bodies} |')
    (out/'records.md').write_text('\n'.join(records),encoding='utf-8')
    status=summary['name_status']
    text=['# DeepSeek API驱动的学院试采','','输入：'+summary['university']+' / '+summary['college']+' / '+summary['homepage'],
          '',f'模型：`{summary["model"]}`；接口：`https://api.deepseek.com`；运行时长：{summary["seconds"]}秒。',
          '本轮从首页重新获取网页，API选择观察到的入口、生成名单/分页/正文选择器，并读取富文本与PDF姓名。程序执行受限的JSON计划，不执行模型生成的代码。',
          '旧名单只在本轮采集结束后用于离线对照，没有作为模型输入或补齐名单。','',
          '| 指标 | 结果 |','|---|---:|',
          f'| 不同姓名 | {summary["distinct_names"]} |',
          f'| 有对应正文的姓名 | {status.get("body_saved",0)} |',
          f'| 只有受限链接的姓名 | {status.get("permission_denied",0)} |',
          f'| 只有名单信息的姓名 | {status.get("name_only",0)} |',
          f'| 名单页 | {summary["roster_pages"]} |',
          f'| 已取得正文页面 | {summary["profile_bodies"]} |',
          f'| API调用 | {summary["api_calls"]} |',
          f'| 输入token | {summary["usage"]["prompt_tokens"]} |',
          f'| 输出token | {summary["usage"]["completion_tokens"]} |',
          f'| 按公布峰时价格估算的美元费用 | {summary["estimated_cost_usd_peak"]} |','',
          '费用按2026-10-14 [DeepSeek官方价格](https://api-docs.deepseek.com/quick_start/pricing/)估算：缓存命中输入每百万token $0.006，未命中输入 $0.30，输出 $1.20。实际扣费以平台账单为准；此表只含本轮，不含之前的连接测试与失败试验。','',
          '## 分支覆盖核对','','| 栏目 | 页面 | 条目 | 官网声明条数 | 全部页码已到达 |','|---|---:|---:|---:|---|']
    for row in branch_checks:
        text.append(f'| {row["branch"]} | {row["pages"]} | {row["entries"]} | {row["declared_total"] or "富文本无总数"} | {row["all_page_numbers_seen"] if row["all_page_numbers_seen"] is not None else "单页富文本"} |')
    text += ['', '## 与上一轮保存材料的对照', '',
             f'- 姓名集合相同：{result["name_set_equal"]}。缺少姓名：{result["missing_names"]}；新增姓名：{result["extra_names"]}。',
             f'- 个人URL少{len(result["missing_profile_urls"])}条、多{len(result["extra_profile_urls"])}条；详细差异见`audit.json`。',
             f'- {body_equal}份正文去除空白后与前次保存文本一致，{len(diffs)}份有差异。',
             f'- 核验了{len(pages)}份HTML和{len(doc_hashes)}份PDF的SHA256。', '',
             '## 边界与文件', '',
             '这验证了同一个已分析过的网站能由脚本调用API完成本轮入口选择、规则生成和采集，不是陌生网站泛化或服务器生产验收。当前保持同域、页数和API次数上限；HTTP页面为主，图片OCR与浏览器自动兜底尚未集成。',
             '姓名和原文保留；邮箱/职称仍是未逐条核验的候选值。当前任职、身份同一性及全院完整性未验证。空入口、无文本、权限提示、漏页均单列，不写成“无师资”。',
             '[逐姓名结果](records.md)；`pages.json`及页目录保留原始网页，`documents/`保留PDF，`api/`保留模型输入/输出与token用量，`code/`保留本轮代码版本。密钥不在这些文件中。']
    (out/'report.md').write_text('\n'.join(text),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('run',type=Path)
    parser.add_argument('baseline',type=Path)
    args=parser.parse_args()
    main(args.run.resolve(),args.baseline.resolve())
