"""Explicit faculty tables: bind cells/boxes to rows, never call a row a CV."""
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from person_names import clean_name,is_person_name
from quality_fields import compact,TITLE

VERSION='faculty-row-table-v1'
BODY='#fontzoom, .wp_articlecontent, .v_news_content, [id^="vsb_content"], .article-content'
CRUMB='.breadcrumb,.col_path,.column_path,.wp_breadcrumb,.path,.tarrtrr'
EXCLUDE=re.compile(r'新闻|通知|公示|招聘|招生|学生|校友|历任|退休|师德师风|获奖|活动')

def faculty_body(soup):
    title=soup.title.get_text(' ',strip=True) if soup.title else ''
    crumbs=' '.join(n.get_text(' ',strip=True) for n in soup.select(CRUMB))
    if EXCLUDE.search(title+crumbs):return None
    if not re.search(r'师资队伍|教师队伍|专任教师|教师名录|师资名录',title+crumbs):return None
    return soup.select_one(BODY)

def html_rows(body):
    result=[];unresolved=[]
    for ti,table in enumerate(body.select('table')):
        trs=table.find_all('tr')
        if not trs:continue
        header=[compact(c.get_text()) for c in trs[0].find_all(['td','th'],recursive=False)]
        if '姓名' not in header or '职称' not in header:continue
        for ri,tr in enumerate(trs[1:],1):
            cells=tr.find_all(['td','th'],recursive=False)
            values=[c.get_text(' ',strip=True) for c in cells]
            if len(values)!=len(header) or any(c.get('rowspan') or c.get('colspan') for c in cells):
                unresolved.append({'table':ti,'row':ri,'reason':'merged_or_missing_cells'});continue
            name=clean_name(values[header.index('姓名')])
            if not is_person_name(name):
                unresolved.append({'table':ti,'row':ri,'reason':'unrecognized_name'});continue
            if cells[header.index('姓名')].select('a[href]'):continue
            fields=dict(zip(header,values));fields['姓名']=name
            result.append({'name':name,'fields':fields,'text':'；'.join(k+'：'+v for k,v in fields.items() if v),
                           'table':ti,'row':ri,'confidence':1.0,'evidence':str(tr)})
    return result,unresolved

def image_rows(media):
    lines=[]
    for i,line in enumerate(media.get('lines',[])):
        box=line.get('box',[])
        if len(box)!=4:continue
        xs=[p[0] for p in box];ys=[p[1] for p in box]
        lines.append({**line,'index':i,'x':sum(xs)/4,'y':sum(ys)/4,'height':max(ys)-min(ys)})
    headers={}
    for label in ('姓名','性别','职称','备注'):
        hits=[l for l in lines if compact(l['text'])==label]
        if len(hits)==1:headers[label]=hits[0]
    if not {'姓名','性别','职称'}<=headers.keys():return [],[{'reason':'table_headers_missing'}]
    ordered=sorted(headers.items(),key=lambda x:x[1]['x'])
    height=max(l['height'] for l in headers.values());hy=sum(l['y'] for l in headers.values())/len(headers)
    if max(abs(l['y']-hy) for l in headers.values())>height:return [],[{'reason':'headers_not_aligned'}]
    columns={k:[] for k in headers}
    for line in lines:
        if line['y']<=hy+height*.7:continue
        nearest=min(ordered,key=lambda h:abs(line['x']-h[1]['x']))
        spacing=min(abs(nearest[1]['x']-h['x']) for k,h in ordered if k!=nearest[0])
        if abs(line['x']-nearest[1]['x'])>spacing/2:continue
        columns[nearest[0]].append(line)
    names=sorted(columns['姓名'],key=lambda l:l['y']);result=[];unresolved=[]
    for ri,name_line in enumerate(names):
        name=clean_name(name_line['text']);lower=(names[ri-1]['y']+name_line['y'])/2 if ri else hy+height*.7
        upper=(names[ri+1]['y']+name_line['y'])/2 if ri+1<len(names) else media.get('height',1e9)
        cells={'姓名':name};indices=[name_line['index']];scores=[name_line['confidence']];valid=is_person_name(name)
        for label in ('性别','职称','备注'):
            hits=[l for l in columns.get(label,[]) if lower<l['y']<upper]
            cells[label]=' '.join(l['text'] for l in sorted(hits,key=lambda l:l['x']))
            indices.extend(l['index'] for l in hits)
            if label in ('性别','职称'):
                valid=valid and len(hits)==1 and abs(hits[0]['y']-name_line['y'])<=height
                scores.extend(l['confidence'] for l in hits)
        valid=valid and cells['性别'] in ('男','女') and bool(TITLE.fullmatch(compact(cells['职称'])))
        if not valid:
            unresolved.append({'row':ri+1,'reason':'row_alignment_or_fields_uncertain','name':name,'line_indices':indices});continue
        result.append({'name':name,'fields':cells,'text':'；'.join(k+'：'+v for k,v in cells.items() if v),
                       'row':ri+1,'confidence':min(scores),'line_indices':indices,'image_sha256':media['sha256'],
                       'media_directory':media['directory'],'source_url':media['source_url']})
    # Every sex/rank cell must belong to an identified row; missing OCR names
    # must remain an explicit completeness issue.
    used={i for row in result for i in row['line_indices']}
    if any(l['index'] not in used for k in ('性别','职称') for l in columns[k]):
        unresolved.append({'reason':'unmatched_row_cells'})
    return result,unresolved

def verified_row(cat,root,observation):
    relative=observation.get('table_row_path','');path=(root/relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():return None
    row=json.loads(path.read_text(encoding='utf8'))
    page=next((p for p in cat['pages'] if p['url']==observation['source_url']),None)
    if not page:return None
    from bs4 import BeautifulSoup
    raw=root/page['directory']/'source.html'
    if not raw.is_file():return None
    body=faculty_body(BeautifulSoup(raw.read_text(encoding='utf8'),'html.parser'))
    if body is None:return None
    if observation['source_kind']=='html_faculty_table':reproduced,_=html_rows(body)
    else:
        media=next((m for m in cat['media'] if m['directory']==row.get('media_directory')),None)
        if not media:return None
        source=root/media['directory']/media['source_file']
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest()!=row.get('image_sha256'):return None
        reproduced,_=image_rows(media)
    return row if row in reproduced else None

def apply_table_rows(cat,root,items):
    duplicates={}
    for person in cat['people']:
        observations=[o for o in person['observations'] if o.get('source_kind') in ('html_faculty_table','image_faculty_table')]
        if not observations or person.get('profile_url') or person['review'].get('revision'):continue
        observation=observations[0];relative=observation.get('table_row_path','')
        row=verified_row(cat,root,observation)
        if not row or row['name']!=person['name']:continue
        item=items[person['id']];fields=item['fields'];rank=row['fields'].get('职称','')
        # Unrecognized rank labels stay visible as candidates, not guessed ranks.
        if TITLE.fullmatch(compact(rank)):fields['title']=rank;fields['missing'].pop('title',None)
        fields['biography']=''
        for field in ('biography','profile_url','email'):
            if not fields.get(field):fields['missing'][field]='not_stated_in_source'
        low=observation['source_kind']=='image_faculty_table' and row['confidence']<.95
        message='正式师资表中的人员；本表仅列名单字段，未列个人主页和完整简介'
        item.update(status='pending' if low else 'auto_accepted',material_status='roster_only',
                    anomalies=['图片名单姓名或职称识别置信度较低'] if low else [],
                    reason='图片名单姓名或职称识别置信度较低，请对照原图该行' if low else message,
                    table_row_evidence={**row,'path':relative},
                    delivery_notes=[{'code':'roster_only','message':message}])
        item['selection']['title']={'value':fields['title'],'score':100 if not low else 0,
                                   'rule':VERSION,'evidence':row['text']}
        key=(person['name'],row.get('image_sha256') or observation['source_url'],row['row'])
        if key in duplicates:
            item.update(status='duplicate',canonical_id=duplicates[key],reason='同一师资表原件的同一行已保留',anomalies=[])
        else:duplicates[key]=person['id']
    by_name=defaultdict(list)
    for p in cat['people']:
        if items[p['id']]['status']!='duplicate':by_name[p['name']].append(p)
    for group in by_name.values():
        if len(group)>1:
            for p in group:
                item=items[p['id']]
                if item.get('table_row_evidence'):
                    item.update(status='pending',anomalies=['同名不同材料，身份关联待核'],reason='同名师资表与其他材料尚未建立身份关联')
