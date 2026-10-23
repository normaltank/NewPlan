"""Prepare bounded local-tool comparisons without changing existing runs."""
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent.parent
PREVIOUS = ROOT.parent / 'tool-comparison-20261018'

def read(p):
    return json.loads(p.read_text(encoding='utf-8'))

def save(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def baseline():
    files = [*SOURCE.glob('*.py'), SOURCE/'requirements.txt', SOURCE/'requirements.lock', SOURCE/'.venv/pyvenv.cfg']
    files += list((SOURCE/'workbench-static').rglob('*'))
    files += list((SOURCE.parent/'server').glob('*.py'))
    files += list((SOURCE.parent/'server').glob('*.md'))
    files += list((SOURCE/'.venv/Lib/site-packages').glob('*.dist-info/METADATA'))
    with sqlite3.connect((SOURCE/'runs/workbench/workbench.db').as_uri()+'?mode=ro', uri=True) as con:
        decisions = list(con.execute('SELECT * FROM decisions ORDER BY job_id,item_id'))
    return {'timestamp': datetime.now(timezone.utc).isoformat(), 'python': sys.version,
            'files': {str(p.relative_to(SOURCE.parent)): sha(p) for p in files if p.is_file()},
            'human_decisions': len(decisions),
            'human_decisions_sha256': hashlib.sha256(json.dumps(decisions, ensure_ascii=False).encode()).hexdigest(),
            'git_head': subprocess.check_output(['git','rev-parse','HEAD'], cwd=SOURCE, text=True).strip(),
            'git_status': subprocess.check_output(['git','status','--short'], cwd=SOURCE, text=True)}

def main():
    if (ROOT/'baseline-before.json').exists():
        raise RuntimeError('Already prepared; preserve the existing baseline.')
    save(ROOT/'baseline-before.json', baseline())
    samples = read(PREVIOUS/'reference-checks.json')
    for s in samples:
        source = PREVIOUS/'sources'/s['id']/'original.html'
        if not source.exists():
            source = PREVIOUS/'results/native'/f"{s['id']}.html"
        destination = ROOT/'sources'/f"{s['id']}.html"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        s['frozen_html'] = str(destination.relative_to(ROOT))
        s['frozen_sha256'] = sha(destination)
    save(ROOT/'samples.json', samples)
    save(ROOT/'scope.json', {
        'html_samples': len(samples),
        'retrieval': ['scrapy_http', 'scrapling_http', 'scrapling_browser'],
        'retrieval_max_requests_per_arm': 26,
        'scrapegraph_cases': ['p01','p06','p07','p10','p18','p23','p24','p25'],
        'scrapegraph_initial_model_call_cap': 24,
        'scrapegraph_model': 'deepseek-flash',
        'limits': 'Fixed page evidence retention and bounded field extraction; no whole-college completeness claim; no paid new-provider subscription.'})
    print(json.dumps({'prepared': str(ROOT), 'samples':len(samples)}, ensure_ascii=False))

if __name__ == '__main__':
    main()
