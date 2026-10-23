"""Explicit department/member tables, including names without personal links."""
import re
import hashlib
from urllib.parse import urljoin,urlparse
from bs4 import BeautifulSoup
from person_names import clean_name,is_person_name,HAN_CHARS
from quality_fields import compact

VERSION='department-member-table-v1'
ADMIN=re.compile(r'党总支|党委|党务|办公室|辅导员|行政|教辅|学生|校友|退休|历任')

def grouped_members(soup,url):
    title=soup.title.get_text() if soup.title else ''
    if re.search(r'新闻|通知|招聘|学生名单|校友|退休|公示',title):return [],[],[]
    if not re.search(r'师资|教师|教职员工|教职工',title):return [],[],[]
    rows=[];excluded=[];errors=[]
    for ti,table in enumerate(soup.select('.v_news_content table,.wp_articlecontent table,#fontzoom table,[id^="vsb_content"] table')):
        trs=table.find_all('tr')
        if not trs:continue
        header=[compact(c.get_text()) for c in trs[0].find_all(['td','th'],recursive=False)]
        if len(header)!=2 or header[0] not in ('专业','系部','部门','教研室') or header[1] not in ('教职员工','教职工','教师姓名','教师'):continue
        for ri,tr in enumerate(trs[1:],1):
            cells=tr.find_all(['td','th'],recursive=False)
            if len(cells)!=2 or any(str(c.get('rowspan','1'))!='1' or str(c.get('colspan','1'))!='1' for c in cells):
                errors.append({'table':ti,'row':ri,'reason':'merged_or_missing_cells'});continue
            category=compact(cells[0].get_text())
            if not category:errors.append({'table':ti,'row':ri,'reason':'missing_department'});continue
            if ADMIN.search(category):
                excluded.append({'table':ti,'row':ri,'category':category,'evidence':str(tr)});continue
            cell=BeautifulSoup(str(cells[1]),'html.parser');members=[]
            for a in cell.select('a[href]'):
                name=clean_name(a.get_text(' ',strip=True));target=urljoin(url,a['href'])
                if is_person_name(name) and urlparse(target).scheme in ('http','https'):
                    members.append((name,target));a.replace_with(' / ')
            for br in cell.select('br'):br.replace_with(' / ')
            # Nonbreaking spaces and separators are actual name boundaries.
            # Preserve single Latin word spaces inside a linked/explicit name.
            for chunk in re.split(r'\s*[/、,，;；|\n\r\t\u00a0]+\s*| {2,}',cell.get_text()):
                name=clean_name(chunk)
                if not name:continue
                if is_person_name(name):members.append((name,''))
                else:errors.append({'table':ti,'row':ri,'text':chunk,'reason':'unrecognized_name_token'})
            for name,target in dict.fromkeys(members):
                rows.append({'name':name,'url':target,'category':category,'table':ti,'row':ri,'evidence':str(tr)})
    return rows,excluded,errors

def verified_member(soup,url,observation,name):
    if observation.get('source_kind')!='department_member':return None
    for row in grouped_members(soup,url)[0]:
        if row['name']==name and row['table']==observation.get('member_table') and row['row']==observation.get('member_row'):
            return row
    return None

def apply_source_exclusions(cat,root,items):
    """Keep false candidates and their originals visible, with proven exclusions."""
    pages={p['url']:p for p in cat['pages']};cache={}
    rosters={r['url'] for r in cat['rosters'] if r.get('source_qualification')=='faculty_roster'}
    for p in cat['people']:
        if p['review'].get('revision'):continue
        if p['name']!='名师风采' and (p['profile_url'] or items[p['id']]['fields']['biography']):continue
        proofs=[]
        for o in p['observations']:
            page=pages.get(o['source_url'])
            if not page or o['source_url'] not in rosters:break
            if page['url'] not in cache:
                path=root/page['directory']/'source.html'
                if not path.is_file():break
                raw=path.read_bytes();soup=BeautifulSoup(raw,'html.parser')
                cache[page['url']]=(soup,hashlib.sha256(raw).hexdigest(),str(path.relative_to(root)),grouped_members(soup,page['url'])[1])
            soup,digest,path,excluded=cache[page['url']];quote=None;kind=None
            if p['name']=='名师风采' and o.get('source_kind')=='faculty_submenu':
                anchor=next((a for a in soup.select('a[href]') if compact(a.get_text())==p['name'] and urljoin(page['url'],a['href'])==p['profile_url']),None)
                if anchor is not None:quote=str(anchor);kind='faculty_column_label'
            elif not p['profile_url'] and not items[p['id']]['fields']['biography']:
                for row in excluded:
                    cells=BeautifulSoup(row['evidence'],'html.parser').find('tr').find_all(['td','th'],recursive=False)
                    value=cells[1].get_text(' ',strip=True)
                    if re.search(r'(?<!['+HAN_CHARS+r'A-Za-z])'+re.escape(p['name'])+r'(?!['+HAN_CHARS+r'A-Za-z])',value):
                        quote=row['evidence'];kind='administrative_table_membership_only';break
            if not quote:break
            proofs.append({'source_url':page['url'],'path':path,'sha256':digest,'quote':quote,'rule':kind})
        else:
            if proofs:
                message='正式师资栏目名称，不是人员' if proofs[0]['rule']=='faculty_column_label' else '仅列于办公、党务或辅导员行，未取得教师任职依据'
                items[p['id']].update(status='excluded',anomalies=[],reason=message,source_exclusions=proofs)
