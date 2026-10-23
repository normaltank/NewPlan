"""Re-read identified mixed PDFs into new evidence paths, preserving old originals."""
import json
from collections import defaultdict
from pathlib import Path
from shutil import copyfile
from ocr_media import read_pdf
from workbench_store import Store,ROOT,read_json
from quality_pipeline import build


def main():
    store=Store(ROOT/'runs/workbench/workbench.db')
    groups=defaultdict(set)
    for item in read_json(ROOT/'runs/20261014-quality-repair/mixed-pdf-candidates.json',[]):
        groups[item['job']].add(item['path'])
    for key,paths in groups.items():
        cat=store.catalog(key,apply_auto=False);root=Path(cat['job']['run_dir'])
        enrichment=read_json(root/'enrichment.json',{})
        for path in sorted(paths):
            doc=next(d for d in cat['documents'] if d['path']==path)
            dest=root/'quality-repair/mixed-pdf'/Path(path).name;dest.mkdir(parents=True,exist_ok=True)
            copyfile(root/path/'source.pdf',dest/'source.pdf')
            parsed=read_pdf((dest/'source.pdf').read_bytes(),dest)
            (dest/'text.txt').write_text(parsed['text'],encoding='utf-8')
            replacement={**doc,'path':dest.relative_to(root).as_posix(),'text_chars':len(parsed['text']),
                         'ocr_pages':parsed['ocr_pages'],'supersedes_path':path}
            enrichment['documents'].append(replacement)
            for page in cat['pages']:
                if path not in page.get('profile_pdfs',[]):continue
                body=root/(page.get('body_path') or page['directory']+'/body-text.txt')
                old=body.read_text(encoding='utf-8');new=old+'\n\n[混合 PDF 补充识别]\n'+parsed['text']
                output=root/'quality-repair'/('mixed-'+Path(page['directory']).name+'.txt')
                output.write_text(new,encoding='utf-8')
                enrichment['pages'].setdefault(page['url'],{}).update(body_path=output.relative_to(root).as_posix(),body_chars=len(new),
                    profile_pdfs=[replacement['path'] if p==path else p for p in page['profile_pdfs']])
            enrichment['report']['repairs'].append({'kind':'mixed_pdf','url':doc['url'],'ocr_pages':parsed['ocr_pages']})
            print(doc['source_page'],parsed['ocr_pages'],flush=True)
        (root/'enrichment.json').write_text(json.dumps(enrichment,ensure_ascii=False,indent=2),encoding='utf-8')
        print(build(store,key)['counts'],flush=True)

if __name__=='__main__':main()
