"""A labelled faculty submenu can itself be an official roster."""
import re
from urllib.parse import urljoin,urlparse
from quality_fields import compact
from person_names import clean_name,is_person_name
from collection_guards import FACULTY,NON_FACULTY

# A faculty menu contains both people and organizational branches. A short
# Chinese label alone is not identity evidence (e.g. 历史系 / 法律系).
ORGANIZATIONAL_LABEL=re.compile(r'(?:系|学院|学部|学科|专业|教研室|研究所|研究院|实验室|中心|办公室|委员会|机构)(?:设置|概况|介绍)?$')
ROSTER_ENTRY=re.compile(r'师资队伍|教师队伍|专任教师|师资名录|教师名录|教职员工|教职工名录|导师名单|导师名录|硕导名单|博导名单|教练员(?:情况|名单|名录)|教练团队')

def explicit_roster_entries(soup,url):
    """Recover explicit roster navigation omitted by a model; never infer URLs."""
    result=[];seen=set()
    for a in soup.select('a[href]'):
        label=compact(a.get_text());target=urljoin(url,a['href'])
        if not ROSTER_ENTRY.fullmatch(label):continue
        if urlparse(target).hostname!=urlparse(url).hostname or urlparse(target).scheme not in ('http','https'):continue
        headings=[li.find('a',recursive=False) for li in a.parents if li.name=='li']
        if any(h is not None and h is not a and NON_FACULTY.search(compact(h.get_text())) for h in headings):continue
        if target not in seen:result.append({'url':target,'label':label,'evidence':str(a)});seen.add(target)
    return result

def faculty_navigation(soup,url):
    found={}
    # Definition-list sidebars use a single dt heading and dd person links.
    # Require an explicit faculty heading, not an arbitrary sidebar of names.
    for dl in soup.select('dl'):
        headings=dl.select('dt')
        if len(headings)!=1 or not ROSTER_ENTRY.fullmatch(compact(headings[0].get_text())):continue
        for dd in dl.find_all('dd',recursive=False):
            a=dd.find('a',recursive=False) or (dd.parent if dd.parent.name=='a' else None)
            if a is None or not a.get('href'):continue
            name=clean_name(a.get_text(' ',strip=True))
            name=re.sub(r'^(?:行业导师|兼职教师|外聘教师)[—－\-：:]\s*','',name)
            if not is_person_name(name) or name=='名师风采' or ROSTER_ENTRY.fullmatch(name) or ORGANIZATIONAL_LABEL.search(name) or FACULTY.search(name) or NON_FACULTY.search(name):continue
            target=urljoin(url,a['href'])
            if urlparse(target).hostname!=urlparse(url).hostname or urlparse(target).scheme not in ('http','https'):continue
            found[(name,target)]={'name':name,'url':target,'evidence':str(a),'section':compact(headings[0].get_text())}
        # Some valid HTML wraps each dd in its own anchor.
        for a in dl.find_all('a',recursive=False):
            dd=a.find('dd',recursive=False)
            if dd is None or not a.get('href'):continue
            name=clean_name(dd.get_text(' ',strip=True));name=re.sub(r'^(?:行业导师|兼职教师|外聘教师)[—－\-：:]\s*','',name)
            if not is_person_name(name) or name=='名师风采' or ROSTER_ENTRY.fullmatch(name) or ORGANIZATIONAL_LABEL.search(name) or FACULTY.search(name) or NON_FACULTY.search(name):continue
            target=urljoin(url,a['href'])
            if urlparse(target).hostname!=urlparse(url).hostname or urlparse(target).scheme not in ('http','https'):continue
            found[(name,target)]={'name':name,'url':target,'evidence':str(a),'section':compact(headings[0].get_text())}
    for li in soup.select('li'):
        label=li.find('a',recursive=False)
        menu=li.find('ul',recursive=False)
        if not label or not menu or not re.fullmatch(r'团队教师|师资队伍|教师队伍|专任教师|兼职教师|外聘教师',compact(label.get_text())):continue
        children=menu.find_all('li',recursive=False)
        # A mixed hierarchical menu is an organizational directory. Bare
        # siblings such as 书法学 must not become people just because their
        # label fits a Chinese-name shape. The roster planner follows branches.
        if any(child.find('ul',recursive=False) for child in children):continue
        for child in children:
            a=child.find('a',recursive=False)
            if not a or not a.get('href'):continue
            name=clean_name(a.get_text(' ',strip=True));target=urljoin(url,a['href'])
            if child.find('ul',recursive=False) or ORGANIZATIONAL_LABEL.search(name):continue
            if FACULTY.search(name) or NON_FACULTY.search(name):continue
            if not is_person_name(name) or re.search('研究|队伍|名单|名录|名册|教职工|其他|团队|简介|人才引进|名师风采',name):continue
            if urlparse(target).hostname!=urlparse(url).hostname or urlparse(target).scheme not in ('http','https'):continue
            found[(name,target)]={'name':name,'url':target,'evidence':str(a),'section':compact(label.get_text())}
    return list(found.values())
