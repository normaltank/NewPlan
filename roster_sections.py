"""Keep explicit directory group headings, including administrative-only groups."""
import hashlib
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from quality_fields import compact,profile_label_name

ADMIN={'行政教辅','行政人员','行政管理','党政管理','党政办公室','辅导员','办公室'}
VERSION='directory-section-v1'

def directory_section(row):
    for parent in list(row.parents)[:5]:
        if parent.name in ('body','html'):break
        headings=parent.find_all(['h1','h2','h3','h4','h5','h6'],recursive=False)
        if len(headings)==1:
            label=compact(headings[0].get_text())
            if len(label)<=30:return label
        if len(headings)>1:break
    return ''

def administrative_roster_proof(cat,root,person,cache):
    observations=person.get('observations',[])
    if not observations or any(o.get('source_kind')!='directory_link' or o.get('directory_section') not in ADMIN for o in observations):return None
    evidence=[]
    for observation in observations:
        url=observation['source_url']
        page=next((p for p in cat['pages'] if p['url']==url),None)
        if not page:return None
        if url not in cache:
            path=root/page['directory']/'source.html'
            if not path.is_file():return None
            data=path.read_bytes();cache[url]=(BeautifulSoup(data,'lxml'),hashlib.sha256(data).hexdigest(),str(path.relative_to(root)))
        soup,digest,path=cache[url];found=[]
        for anchor in soup.select('a[href]'):
            if profile_label_name(anchor.get_text(' ',strip=True))!=person['name']:continue
            if urljoin(page.get('loaded_url',url),anchor['href'])!=observation.get('profile_url'):continue
            row=anchor.find_parent('li')
            if row is not None:found.append(directory_section(row))
        if not found or any(label!=observation['directory_section'] for label in found):return None
        evidence.append({'url':url,'path':path,'sha256':digest,'section':observation['directory_section']})
    return {'mechanism':VERSION,'sources':evidence}
