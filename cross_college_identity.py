"""Identity evidence from a named personal CV explicitly bridging two colleges."""
import re
import unicodedata
from difflib import SequenceMatcher

def compact(text):return re.sub(r'\s+','',unicodedata.normalize('NFKC',text or ''))

def appointment_bridge(a,b):
    if a['university']!=b['university'] or compact(a['name'])!=compact(b['name']):return None
    if a['college']==b['college'] or not all(r.get('profile_url') and r.get('biography') for r in (a,b)):return None
    name=compact(a['name']);left=compact(a['biography']);right=compact(b['biography'])
    for target,source,text in ((a,b,right),(b,a,left)):
        intro=re.split(r'主讲课程|研究方向|主要成果|联系方式|代表性论文|专著|研究领域',text,maxsplit=1)[0][:800]
        pos=intro.find(name)
        if pos<0:continue
        intro=intro[pos:]
        # An explicit personal leadership appointment, not a generic college
        # mention, education, supervisor, or a similarly named person in papers.
        claim=re.search(re.escape(compact(target['university']+target['college']))+r'(?:常务)?(?:副)?院长',intro)
        if not claim or re.search(r'师从|导师为|指导教师|跟随',intro[max(0,claim.start()-20):claim.start()]):continue
        shared=[]
        for match in SequenceMatcher(None,left[:1800],right[:1800],autojunk=False).get_matching_blocks():
            quote=left[match.a:match.a+match.size]
            if match.size>=8 and re.search(r'学会|专委会|注册结构师|注册建筑师',quote):shared.append(quote)
        if not shared:continue
        return {'rule':'named_cross_college_appointment_with_corroboration',
                'value':{'appointment':claim[0],'source':source['profile_url'],'target':target['profile_url'],
                         'shared_details':shared}}
    return None
