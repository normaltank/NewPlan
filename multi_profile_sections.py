"""Read full biographies separated by standalone name headings on one roster page."""
import re
from bs4 import BeautifulSoup
from quality_fields import compact

def split_biographies(body):
    paragraphs=body.find_all(['p','h2','h3','h4'],recursive=True)
    # Nested paragraphs/headings are not a supported segmentation structure.
    if any(n.find(['p','h2','h3','h4']) for n in paragraphs):return []
    heads=[]
    for i,p in enumerate(paragraphs):
        name=compact(p.get_text(' ',strip=True))
        if re.fullmatch(r'[\u4e00-\u9fff]{2,5}',name) and (p.name!='p' or p.find(['strong','b'])):
            heads.append((i,name))
    if len(heads)<2:return []
    rows=[]
    for j,(start,name) in enumerate(heads):
        end=heads[j+1][0] if j+1<len(heads) else len(paragraphs)
        pieces=paragraphs[start:end]
        text='\n'.join(n.get_text(' ',strip=True) for n in pieces)
        following=compact('\n'.join(n.get_text(' ',strip=True) for n in pieces[1:]))
        if not re.match(r'^(?:男|女)[,，。]|^(?:男|女)(?:\d{4}|[，,]?中共)|^性别[：:]',following):continue
        if len(compact(text))<25 or any(n.select('img,iframe,object') for n in pieces):continue
        # Preserve only the person's entire DOM section, never neighbouring CVs.
        rows.append({'name':name,'text':text,'html':'\n'.join(str(n) for n in pieces),
                     'start_paragraph':start,'end_paragraph_exclusive':end})
    return rows
