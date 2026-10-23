"""Evidence-bound consolidation at university delivery, leaving observations intact."""
import re
from collections import defaultdict
from cross_college_identity import appointment_bridge

POLICY='university-identity-v1'
MERGE_HEADERS=['学校','姓名','学院关联','原记录数','合并依据','待核字段','官方来源','复核路径']

def norm(value):
    return re.sub(r'\s+','',value or '')

def urlkey(value):
    return (value or '').split('#')[0].replace('http://','https://',1).rstrip('/')

def emails(record):
    return set(re.findall(r'[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}',record.get('email','').lower()))

def consolidate(records):
    owners=defaultdict(set)
    for r in records:
        for key in [('email',v) for v in emails(r)]+[('url',urlkey(r.get('profile_url')))]:
            if key[1]:owners[(r['university'],*key)].add(norm(r.get('name')))
    buckets=defaultdict(list)
    for index,r in enumerate(records):buckets[(r['university'],norm(r.get('name')))].append(index)
    parent=list(range(len(records)));proofs=[]
    def root(i):
        while parent[i]!=i:i=parent[i]
        return i
    for (university,name),indices in buckets.items():
        if not name:continue
        for offset,i in enumerate(indices):
            a=records[i]
            for j in indices[offset+1:]:
                b=records[j];reason=None
                shared=emails(a)&emails(b)
                safe=sorted(e for e in shared if len(owners[(university,'email',e)])==1)
                link=urlkey(a.get('profile_url'))
                body=norm(a.get('biography'))
                if safe:reason={'rule':'same_name_personal_email','value':safe}
                elif link and link==urlkey(b.get('profile_url')) and len(owners[(university,'url',link)])==1:
                    reason={'rule':'same_name_personal_page','value':link}
                elif len(body)>=100 and body==norm(b.get('biography')) and name in body[:250]:
                    reason={'rule':'same_name_identical_full_biography','value':'normalized full biography'}
                else:reason=appointment_bridge(a,b)
                if reason:
                    parent[root(j)]=root(i);proofs.append({'left':i,'right':j,**reason})
    groups=defaultdict(list)
    for i in range(len(records)):groups[root(i)].append(i)
    result=[]
    for indices in groups.values():
        members=[records[i] for i in indices];p=dict(members[0])
        p['members']=members;p['identity_policy']=POLICY
        p['merge_evidence']=[e for e in proofs if e['left'] in indices and e['right'] in indices]
        p['college']='；'.join(dict.fromkeys(r['college'] for r in members))
        p['sources']=list(dict.fromkeys(u for r in members for u in r.get('sources',[])))
        p['profile_url']='\n'.join(dict.fromkeys(r['profile_url'] for r in members if r.get('profile_url')))
        p['collected_date']='；'.join(dict.fromkeys(r.get('collected_date','') for r in members))
        p['field_conflicts']={}
        for field in ('title','email'):
            variants={}
            for r in members:
                value=r.get(field,'').strip()
                if value:
                    key=tuple(sorted(set(re.split(r'[、,，;；/\s]+',value)))) if field=='title' else tuple(sorted(emails(r)))
                    variants.setdefault(key,value)
            values=list(variants.values())
            if len(values)>1:
                p[field]='';p['field_conflicts'][field]=[{'value':r.get(field),'college':r['college'],
                    'source':r.get('profile_url'),'run_id':r['run_id'],'person_id':r.get('person_id')} for r in members if r.get(field)]
            else:p[field]=values[0] if values else ''
        bodies=list(dict.fromkeys(r.get('biography','') for r in members if r.get('biography')))
        if len(bodies)>1:
            p['biography']='\n\n'.join('【'+ '；'.join(dict.fromkeys(r['college'] for r in members if r.get('biography')==body))+'】\n'+body for body in bodies)
        else:p['biography']=bodies[0] if bodies else ''
        result.append(p)
    return result

def merge_rows(records):
    return [[p['university'],p.get('name',''),p['college'],len(p['members']),
             '；'.join(dict.fromkeys(e['rule'] for e in p['merge_evidence'])),
             '\n'.join(('职称' if f=='title' else '邮箱')+'待核：'+'；'.join(v['college']+' = '+v['value'] for v in values)
                       for f,values in p['field_conflicts'].items()) or '无字段冲突',
             '\n'.join(dict.fromkeys(u for r in p['members'] for u in [r.get('profile_url'),*r.get('sources',[])] if u)),
             '\n'.join('/review/'+r['run_id']+'?item='+r.get('person_id','') for r in p['members'])]
            for p in records if len(p['members'])>1]
