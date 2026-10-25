"""Interpret directory rows identically during collection and saved-run replay."""
from dataclasses import dataclass
import re
from urllib.parse import urljoin

from person_names import is_person_name
from quality_fields import TITLE, TITLES, profile_label_name
from roster_sections import directory_section

VERSION='nested-directory-card-v1'
PARSER_VERSION='directory-interpretation-v1'


def title_name(label):
    value=profile_label_name(label)
    value=re.sub(r'^硕士生导师[—－\-：:\s]*','',value)
    value=re.split(r'[（(]',value,maxsplit=1)[0]
    value=re.sub(r'[—－\-]\s*(?:学术学业导师|学业导师|学术导师|导师|教授|副教授|讲师).*$', '',value)
    value=profile_label_name(value)
    if value in TITLES or value in {'教职员工','教职工','外籍教师','兼职教师','专任教师','名师风采'}:return None
    if value in {'师资队伍','教师队伍','教授','副教授','讲师','助教','博士','硕士','系主任','副主任','教学团队','研究方向','姓名','职称','学院简介','学校简介','师资简介','教师简介','个人简介','团队简介','专业简介','学科简介'}:
        return None
    return value if is_person_name(value) else None


def selected(node,selector):
    if not selector or selector=='SELF':
        return node
    if not isinstance(selector,str) or len(selector)>300:
        raise ValueError('Invalid selector')
    return node.select_one(selector)


@dataclass
class DirectoryItem:
    person: dict | None = None
    document: dict | None = None
    issue: dict | None = None


@dataclass
class ParsedDirectory:
    row_count: int
    items: list[DirectoryItem]
    recovery: dict | None

    @property
    def people(self):
        return [item.person for item in self.items if item.person is not None]


def parse_directory(soup, plan, base_url):
    """Return evidence and row outcomes; no model calls, queueing or file writes.

    Person dictionaries contain arguments for recording an observation. Source,
    branch, URL scope and subsequent acquisition remain the caller's decisions.
    """
    rows, recovery = directory_rows(soup, plan, title_name)
    result = ParsedDirectory(len(rows), [], recovery)
    if not rows:
        result.items.append(DirectoryItem(issue={'kind': 'roster_structure_mismatch'}))
    for row in rows:
        selector = plan.get('label_selector')
        node = selected(row, selector)
        link = selected(row, plan.get('href_selector'))
        # Word tables can put an empty formatting anchor before the real name.
        if node is not None and not node.get_text(strip=True) and selector not in (None, '', 'SELF'):
            choices = {re.sub(r'[\s\u200b\ufeff]+', '', n.get_text(' ', strip=True)): n
                       for n in row.select(selector) if n.get_text(strip=True)}
            if len(choices) == 1:
                node = next(iter(choices.values()))
        if not node:
            if row.get_text(strip=True) or row.select('a[href],img'):
                result.items.append(DirectoryItem(issue={'kind': 'roster_label_missing'}))
            continue
        label = node.get_text(' ', strip=True)
        url = urljoin(base_url, link.get('href', '')) if link and link.get('href') else ''
        name = title_name(label)
        if name:
            section = directory_section(row)
            result.items.append(DirectoryItem(person={
                'name': name, 'url': url, 'evidence': label,
                **({'directory_section': section} if section else {})}))
        elif url:
            result.items.append(DirectoryItem(
                document={'url': url, 'label': label},
                issue={'kind': 'non_person_directory_entry', 'label': label, 'document_url': url}))
        else:
            result.items.append(DirectoryItem(issue={'kind': 'unclassified_roster_row', 'label': label}))
    return result

def directory_rows(soup,plan,name_from_label):
    selector=plan.get('row_selector','')
    original=soup.select(selector) if selector else []
    if plan.get('source_qualification')!='faculty_roster':return original,None
    match=re.fullmatch(r'([^,]+)>\s*(li(?:[.#][\w-]+)*)\s*',selector)
    if not match:return original,None
    containers=soup.select(match[1].strip())
    if len(containers)!=1 or containers[0].name not in ('ul','ol'):return original,None
    container=containers[0];expanded=container.select(match[2])
    if not original or not len(original)<len(expanded)<=5000:return original,None
    for row in expanded:
        # A real nested list is a different group, not malformed sibling cards.
        for parent in row.parents:
            if parent is container:break
            if parent.name in ('ul','ol'):return original,None
        label_selector=plan.get('label_selector');href_selector=plan.get('href_selector')
        if not label_selector or not href_selector or 'SELF' in (label_selector,href_selector):return original,None
        labels=[n for n in row.select(label_selector) if n.find_parent('li') is row]
        links=[n for n in row.select(href_selector) if n.name=='a' and n.get('href') and n.find_parent('li') is row]
        if len(labels)!=1 or len({a['href'] for a in links})!=1:return original,None
        label=labels[0].get_text(' ',strip=True)
        if not name_from_label(label) or not TITLE.search(label):return original,None
    return expanded,{'mechanism':VERSION,'selector':selector,'before_rows':len(original),'recovered_rows':len(expanded)}
