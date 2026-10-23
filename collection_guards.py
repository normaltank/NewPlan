"""Bounded official-resource redirects and DOM navigation scope checks."""
import re
from urllib.parse import urljoin,urlparse

FACULTY=re.compile(r'师资|教师|教授|研究员|讲师|博士后|导师|教练员|专任|教学团队')
NON_FACULTY=re.compile(r'学院概况|学院简介|党[务群政]|党建|招生|招聘|新闻|通知|下载|学生工作|人才培养|科学研究|学术科研|国际交流|学科建设|行政|历任|名誉院长|院系领导')

def rendered_content_text(soup):
    # Menu libraries insert these decorative arrows after loading. They are not
    # newly loaded biography text and must not trigger a second paid plan.
    return re.sub(r'[\s»«›‹→←↑↓]+','',soup.get_text(' ',strip=True))

def branch_scope(link):
    label=link.get_text(' ',strip=True)
    if FACULTY.search(label) and not NON_FACULTY.search(label):
        return True,'faculty_label: '+label
    # A broad selector can match every menu. Inspect the enclosing menu's own
    # heading, not all descendants (which would mix unrelated site navigation).
    for ancestor in link.parents:
        if ancestor.name!='li':continue
        heading=ancestor.find('a',recursive=False)
        if heading is None or heading is link:continue
        title=heading.get_text(' ',strip=True)
        if NON_FACULTY.search(title):return False,'outside_faculty_menu: '+title
        if FACULTY.search(title):return True,'faculty_menu: '+title
    if NON_FACULTY.search(label):return False,'non_faculty_label: '+label
    if FACULTY.search(label):return True,'faculty_label: '+label
    return None,'unverified_branch_context: '+label

async def robots_response(client,url,host):
    """Follow only same-host redirects; never treat a redirect as robots denial."""
    for _ in range(4):
        parsed=urlparse(url)
        if parsed.scheme not in ('http','https') or parsed.netloc.lower()!=host or parsed.username or parsed.password:
            raise ValueError('Robots redirect outside official host')
        response=await client.get(url)
        if response.status_code not in (301,302,303,307,308):return response
        location=response.headers.get('location')
        if not location:raise ValueError('Robots redirect without location')
        url=urljoin(url,location)
    raise ValueError('Robots redirect limit')
