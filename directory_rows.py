"""Recover malformed, nested rank-labelled cards inside one selected roster list."""
import re
from quality_fields import TITLE

VERSION='nested-directory-card-v1'

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
