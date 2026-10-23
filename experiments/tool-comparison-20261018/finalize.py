"""Finalize evidence manifests and usage; refuses incomplete benchmark arms."""
import hashlib
import json
import math
import statistics
from datetime import datetime,timezone
from pathlib import Path

from prepare import ROOT, SOURCE, baseline_state, read, save, sha
from evaluate import payload

def finite(value):
    if isinstance(value,float) and not math.isfinite(value):return None
    if isinstance(value,dict):return {k:finite(v) for k,v in value.items()}
    if isinstance(value,list):return [finite(v) for v in value]
    return value

def main():
    for arm in ('native','jina','firecrawl','jina_full'):
        paths=list((ROOT/'results'/arm).glob('*.json'))
        assert len(paths)==27,(arm,len(paths))
    assert all((ROOT/'results/docling'/f'd{i:02}.json').exists() for i in range(1,6))
    before=read(ROOT/'baseline-before.json');after=baseline_state()
    save(ROOT/'baseline-after.json',after)
    changed=[k for k,v in before['files'].items() if after['files'].get(k)!=v]
    new=[k for k in after['files'] if k not in before['files']]
    isolation={'checked_files':len(before['files']),'changed_existing_files':changed,'new_baseline_files':new,
        'human_decisions_before':before['human_decisions'],'human_decisions_after':after['human_decisions'],
        'human_decisions_unchanged':before['human_decisions_sha256']==after['human_decisions_sha256'],
        'original_git_head_unchanged':before['git_head']==after['git_head'],
        'scope':'Checks OpenSource source/static/dependency metadata and MyPlan/server Python/runtime Markdown. Database accessed read-only; only legacy workbench decisions are hashed.'}
    save(ROOT/'isolation-check.json',isolation)
    versions=read(ROOT/'versions.json')
    versions.update(docling_actual=read(ROOT/'results/docling/setup.json')['versions'],
        model_manifest={str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'models').rglob('*') if p.is_file() and '.cache' not in p.parts},
        experiment_code_sha256={p.name:sha(p) for p in ROOT.glob('*.py')},
        lock_sha256={p.name:sha(p) for p in ROOT.glob('requirements-*.lock')},
        completed_at=datetime.now(timezone.utc).isoformat())
    versions['jina']['tested_variants']={
        'jina':'automatic readable content, 27 URLs',
        'jina_body':'x-target-selector: body, 6 targeted follow-up URLs',
        'jina_full':'x-respond-with: markdown, 27 URLs',
        'jina_html':'x-respond-with: html, one embedded PDF landing page'}
    versions['firecrawl']['tool_schema_sha256']=sha(ROOT/'firecrawl-tool-schema.txt')
    save(ROOT/'versions.json',versions)
    usage={}
    for arm in ('native','firecrawl','jina','jina_body','jina_full','jina_html'):
        records=[read(p) for p in sorted((ROOT/'results'/arm).glob('*.json'))]
        latencies=[x['elapsed_seconds'] for x in records]
        entry={'saved_requests':len(records),'request_seconds_total':round(sum(latencies),3),
            'median_seconds':round(statistics.median(latencies),3) if latencies else None}
        if arm=='firecrawl':
            entry['reported_credits_saved_calls']=sum(payload(x).get('metadata',{}).get('creditsUsed',0) for x in records)
            entry['unpersisted_successful_initial_calls']=4
            entry['unpersisted_ids']=['p02','p03','p04','p05']
            entry['reason']='Initial result subdirectory absent. Writes failed; four calls repeated after folder creation. Repeat costs included; missing first responses excluded from quality scoring.'
            entry['total_attempts']=len(records)+4
            entry['credit_balance_before']=read(ROOT/'firecrawl-credit-before.json')['remainingCredits']
            entry['credit_balance_after']=read(ROOT/'firecrawl-credit-after.json')['structuredContent']['remainingCredits']
            entry['observed_balance_change']=entry['credit_balance_before']-entry['credit_balance_after']
        if arm.startswith('jina'):
            entry['reported_output_tokens']=sum(payload(x).get('data',{}).get('usage',{}).get('tokens',0) for x in records)
            entry['authentication']='anonymous, no API key supplied'
        usage[arm]=entry
    usage['deepseek_model_calls']=0
    usage['docling']={'local_conversions':5,'remote_model_api_calls':0,
        'model_download_seconds':read(ROOT/'results/docling/setup.json')['model_download_seconds'],
        'conversion_seconds_total':sum(read(ROOT/'results/docling'/f'd{i:02}.json')['elapsed_seconds'] for i in range(1,6)),
        'local_model_bytes':sum(p.stat().st_size for p in (ROOT/'models').rglob('*') if p.is_file())}
    usage['billing_note']='Firecrawl credits are not dollars; no account currency bill independently reconciled. Jina token counters are response usage, not DeepSeek tokens.'
    save(ROOT/'usage.json',usage)
    artifacts={}
    for folder in ('sources','results'):
        for p in (ROOT/folder).rglob('*'):
            if p.is_file():artifacts[str(p.relative_to(ROOT))]=sha(p)
    save(ROOT/'evidence-sha256.json',artifacts)
    summary={'scope':'26 pages plus one direct PDF URL in both web providers; five local document cases including one derived scan. No college-wide collection or production integration.',
        'isolation':isolation,'usage':usage,'documents':finite(read(ROOT/'document-comparison.json')),
        'web':read(ROOT/'web-comparison.json')}
    save(ROOT/'summary.json',summary)
    print(json.dumps({'isolation':isolation,'usage':usage},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
