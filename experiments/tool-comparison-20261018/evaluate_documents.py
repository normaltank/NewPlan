"""Read table cells including continuation-page 'headers'; keep source positions."""
import re
from collections import Counter
from evaluate import ROOT, read, save, compact, norm, payload, from_md, doc_reference

def table_cell_rows(document):
    rows=[]
    for ti,table in enumerate(document.get('tables',[])):
        data=table['data']
        grid=[['']*data['num_cols'] for _ in range(data['num_rows'])]
        header_rows=set()
        for cell in data['table_cells']:
            ri=cell['start_row_offset_idx'];ci=cell['start_col_offset_idx']
            grid[ri][ci]=cell['text']
            if cell.get('column_header'):header_rows.add(ri)
        for ri,cells in enumerate(grid):
            # A semantic column heading is not an employee, even when the parser
            # marks a continuation page's first employee as a column header.
            joined='|'.join(cells)
            if '姓名' in joined and '职称' in joined and '邮箱' in joined:continue
            rows.append({'cells':cells,'table':ti,'row':ri,'parser_marks_header':ri in header_rows,
                         'page':(table.get('prov') or [{}])[0].get('page_no')})
    return rows

def row_check(reference,rows):
    by_name={compact(x['cells'][0]):x for x in rows if x['cells']}
    result=[]
    for expected in reference:
        found=by_name.get(compact(expected['name']))
        cells=found['cells'] if found else []
        result.append({'name':expected['name'],'found':bool(found),
            'title_correct':norm(expected['title'])==norm(cells[3]) if len(cells)>3 else False,
            'email_correct':compact(expected['email'])==compact(cells[6]) if expected['email'] and len(cells)>6 else None,
            'incomplete_email_preserved':compact(expected['incomplete_email'])==compact(cells[6]) if expected['incomplete_email'] and len(cells)>6 else None,
            'actual_title':cells[3] if len(cells)>3 else None,'actual_email':cells[6] if len(cells)>6 else None,
            'evidence':{k:v for k,v in (found or {}).items() if k!='cells'}})
    return {'expected':len(reference),'names':sum(x['found'] for x in result),
        'titles':sum(x['title_correct'] for x in result),
        'expected_complete_emails':sum(bool(x['email']) for x in reference),
        'complete_emails':sum(x['email_correct'] is True for x in result),
        'checks':result,'unexpected_first_cells':[x for x in by_name if x not in {compact(r['name']) for r in reference}]}

def markdown_rows(text):
    rows=[]
    for line in text.splitlines():
        if not line.startswith('|'):continue
        cells=[re.sub(r'<[^>]*>','',x).strip() for x in line.strip().strip('|').split('|')]
        if len(cells)<7:continue
        rows.append({'cells':cells})
    return rows

def plain_pdf_rows(text):
    """Recognize this declared table schema despite page joins without newlines."""
    pattern=r'([\u3400-\u9fff]{2,4})\s+([男女])\s+(\d{4}[.．]\d{1,2})\s*'
    matches=list(re.finditer(pattern,text));rows=[]
    titles=r'(主任医师[，,、]\s*教授|副主任医师[，,、]\s*教授|副主任护师|主任护师|副主任医师|主任医师|副教授|副研究员|教授|研究员)'
    for i,m in enumerate(matches):
        tail=text[m.end():matches[i+1].start() if i+1<len(matches) else len(text)]
        title=re.match(titles,tail)
        if not title:continue
        normalized=compact(tail)
        emails=re.findall(r'[A-Za-z0-9_.+\-]+@[A-Za-z0-9.\-]+(?:\.[A-Za-z]{2,})?',normalized)
        rows.append({'cells':[m[1],m[2],m[3],title[1],'','',emails[-1] if emails else ''],
                     'source_span':[m.start(),matches[i+1].start() if i+1<len(matches) else len(text)]})
    return rows

def main():
    reference=doc_reference();out={}
    for sample in read(ROOT/'documents.json'):
        sid=sample['id'];path=ROOT/'results/docling'/(sid+'-document.json')
        if not path.exists():continue
        doc=read(path);meta=read(ROOT/'results/docling'/(sid+'.json'))
        text=(ROOT/'results/docling'/(sid+'.md')).read_text(encoding='utf8')
        data={'status':meta['status'],'seconds':meta['elapsed_seconds'],'tables':len(doc['tables']), 'text_chars':len(text)}
        if sid in ('d01','d05'):
            rows=table_cell_rows(doc)
            data['raw_dataframe_rows']=sum(len(x) for x in meta['table_rows'])
            data['cell_rows']=len(rows)
            data['preserved_header_people']=[x['cells'][0] for x in rows if x['parser_marks_header']]
            data['comparison']=row_check(reference if sid=='d01' else reference[:24],rows)
            save(ROOT/'results/docling'/(sid+'-normalized-rows.json'),rows)
        else:
            expected=sample['expected']
            data['name_retained']=compact(expected['name']) in compact(text) if expected.get('name') else None
            data['title_retained']=compact(expected['title']) in compact(text) if expected.get('title') else None
            data['markers']=[{'text':v,'retained':norm(v) in norm(text)} for v in expected.get('markers',[])]
            data['email_candidates']=re.findall(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}',text)
            data['scope']='Selected image only; continuation images and full biography completeness not certified.'
            if sid=='d04':data['scope']='OCR reads restaurant wall text; output alone does not determine whether it is a faculty biography.'
        out[sid]=data
    for provider in ['firecrawl','jina','jina_full']:
        if not (ROOT/'results'/provider/'d01.json').exists():continue
        record=read(ROOT/'results'/provider/'d01.json')
        data=payload(record)
        if provider.startswith('jina'):data=data.get('data',{})
        text=data.get('markdown',data.get('content',''))
        rows=markdown_rows(text)
        parsed=row_check(reference,rows)
        parsed['scope']='Generic seven-column Markdown table reader. A zero row result means this reader is incompatible, not that the provider necessarily omitted names.'
        plain,_=from_md(text,'')
        parsed['name_strings_in_text']=sum(compact(x['name']) in compact(plain) for x in reference)
        parsed['complete_email_strings_in_text']=sum(compact(x['email']) in compact(plain) for x in reference if x['email'])
        if provider.startswith('jina'):
            parsed['plain_table_adapter']=row_check(reference,plain_pdf_rows(plain))
        out[provider+'_pdf']=parsed
    save(ROOT/'document-comparison.json',out)
    for k,v in out.items():
        print(k,{a:b for a,b in v.items() if a not in ('comparison','checks')})
        if 'comparison' in v:
            print({a:b for a,b in v['comparison'].items() if a!='checks'})
            print('mismatches',[x for x in v['comparison']['checks'] if not x['found'] or not x['title_correct'] or x['email_correct'] is False])

if __name__=='__main__':main()
