"""Read-only baseline inventory and immutable, bounded provider test inputs."""
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent.parent
PREVIOUS = ROOT.parent / 'deepseek-fetch-20261018'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf8')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def baseline_state():
    files = [*SOURCE.glob('*.py'), SOURCE/'requirements.txt', SOURCE/'requirements.lock', SOURCE/'.venv/pyvenv.cfg']
    files += list((SOURCE/'workbench-static').rglob('*'))
    files += list((SOURCE.parent/'server').glob('*.py'))
    files += list((SOURCE.parent/'server').glob('*.md'))
    files += list((SOURCE/'.venv/Lib/site-packages').glob('*.dist-info/METADATA'))
    hashes = {str(p.relative_to(SOURCE.parent)): sha(p) for p in files if p.is_file()}
    db = SOURCE/'runs/workbench/workbench.db'
    with sqlite3.connect(db.as_uri()+'?mode=ro', uri=True) as con:
        decisions = list(con.execute('SELECT * FROM decisions ORDER BY job_id,item_id'))
    return {'timestamp': datetime.now(timezone.utc).isoformat(), 'files': hashes,
            'human_decisions': len(decisions),
            'human_decisions_sha256': hashlib.sha256(json.dumps(decisions, ensure_ascii=False).encode()).hexdigest(),
            'python': sys.version,
            'git_head': subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip(),
            'git_status': subprocess.check_output(['git','status','--short'],cwd=SOURCE,text=True)}


def run_path(case):
    name = 'continued-pointer.json' if case == 'seu' else 'capture-pointer.json'
    return Path(read(PREVIOUS/'runs'/case/name)['run_dir'])


def main():
    if (ROOT/'baseline-before.json').exists():
        raise RuntimeError('Prepared already. Use a new experiment directory; do not overwrite evidence.')
    save(ROOT/'baseline-before.json', baseline_state())
    samples = []
    for row in read(PREVIOUS/'spot-checks.json'):
        sid = f'p{len(samples)+1:02}'
        folder = ROOT/'sources'/sid
        folder.mkdir(parents=True)
        original = Path(row['source'])
        shutil.copy2(original, folder/'original.html')
        body = original.parent/'body-text.txt'
        if body.exists(): shutil.copy2(body, folder/'native.txt')
        shutil.copy2(row['fetch_response'], folder/'deepseek.json')
        expected = {'name': row['name'], 'email': row['email_checked'],
                    'biography_marker': (row.get('biography_item_check') or {}).get('item')}
        samples.append({'id':sid,'kind':'profile','group':'known_diagnostic',
                        'url':row['url'],'case':row['case'],'expected':expected,
                        'source_sha256':sha(folder/'original.html'), 'previous_source':str(original)})
    run = run_path('fynu')
    pages = read(run/'pages.json')
    for page in pages:
        url = page['url']
        if '/szdw/sssds' not in url and not url.endswith('/szdw/jstd.htm'): continue
        sid=f'p{len(samples)+1:02}'
        folder=ROOT/'sources'/sid
        folder.mkdir(parents=True)
        original=run/page['directory']/'source.html'
        shutil.copy2(original,folder/'original.html')
        soup=BeautifulSoup(original.read_text(encoding='utf8'),'html.parser')
        anchors=soup.select('dd[id^="line_"] a.fl[href]')
        if not anchors: anchors=soup.select('.vsb_content a[href], #vsb_content a[href], .v_news_content a[href]')
        expected=[{'name':a.get_text('',strip=True),'url':urljoin(url,a['href'])} for a in anchors if a.get_text(strip=True)]
        samples.append({'id':sid,'kind':'roster','group':'known_diagnostic','case':'fynu','url':url,
                        'expected':{'rows':expected},'source_sha256':sha(original),'previous_source':str(original)})
    samples.append({'id':f'p{len(samples)+1:02}','kind':'attachment_landing','group':'known_diagnostic',
                    'case':'ntu','url':'https://ntdxhk.ntu.edu.cn/xkjs/list.htm','expected':{}})
    for name,email,url in [('唐豪','htang2015@sjtu.edu.cn','https://www.physics.sjtu.edu.cn/jsml/tanghao.html'),
                           ('谢应明','yingming.xie@sjtu.edu.cn','https://www.physics.sjtu.edu.cn/jsml/xieyingming.html')]:
        samples.append({'id':f'p{len(samples)+1:02}','kind':'profile','group':'new_validation',
                        'case':'sjtu','url':url,'expected':{'name':name,'email':email,'title':'教授' if name=='唐豪' else '副教授'}})
    save(ROOT/'samples.json',samples)
    # Inventory likely useful real attachments; selection and visual ground truth follow.
    candidates=[]
    for p in (SOURCE/'runs').glob('*/media/*/ocr.json'):
        d=read(p)
        if len(d.get('text',''))>350:
            candidates.append({'path':str(p),'source_url':d.get('source_url'), 'chars':len(d['text']),
                               'preview':d['text'][:220], 'width':d.get('width'),'height':d.get('height')})
    save(ROOT/'attachment-candidates.json',candidates[:100])
    ntu_doc=next(run_path('ntu').glob('documents/*/source.pdf'))
    folder=ROOT/'sources'/'d01'
    folder.mkdir(parents=True)
    shutil.copy2(ntu_doc,folder/'source.pdf')
    shutil.copy2(ntu_doc.parent/'pdf-text.json',folder/'native.json')
    save(ROOT/'documents.json',[{'id':'d01','kind':'multi_person_pdf','source':str(folder/'source.pdf'),
        'previous_source':str(ntu_doc),'sha256':sha(ntu_doc),'expected_rows':61,
        'url':'https://ntdxhk.ntu.edu.cn/_upload/article/files/c7/73/fccafbe54f0eb873fe38fdcaabf2/f4503ae9-8dfe-4d99-abf5-c4ef981c9998.pdf'}])
    save(ROOT/'versions.json',{'prepared_at':datetime.now(timezone.utc).isoformat(),
        'docling_requested':'2.140.0','firecrawl':{'transport':'MCP hosted','version':'server version not exposed',
            'config':{'formats':['markdown','rawHtml','links'],'onlyMainContent':False,'maxAge':0}},
        'jina':{'transport':'https://r.jina.ai','version':'server version not exposed',
            'config':{'Accept':'application/json','x-no-cache':'true','x-retain-links':'all','x-with-links-summary':'all'}},
        'isolation':'Local packages/models/output isolated; remote versions cannot be pinned. No production imports or DB writes.'})
    print(json.dumps({'samples':len(samples),'document_candidates':len(candidates),'directory':str(ROOT)},ensure_ascii=False))


if __name__=='__main__':main()
