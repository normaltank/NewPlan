"""Associate saved college roster rows with an unambiguous personal record.

This is scoped to one college run, requires both saved official roster evidence
and a personal-page link, and never infers identity between different profiles.
"""
import hashlib
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from quality_fields import compact, profile_label_name, TITLES
from person_names import HAN_CHARS

POLICY = 'saved-college-roster-v1'
FACULTY = re.compile(r'师资|教师|名师|教授|研究员|讲师|导师|博士后|教学团队')
EXCLUDED = re.compile(r'行政|党政|学生|校友|退休|离休|历任|新闻|招聘|招生|下载')
CONTENT = '.wp_articlecontent, .v_news_content, [id^="vsb_content"], .article-content, .entry-content, .tlls, #fontzoom'


def urlkey(url):
    return (url or '').split('#')[0].replace('http://', 'https://', 1).rstrip('/')


class RosterEvidence:
    def __init__(self, cat, root):
        host = urlparse(cat['job']['target']['url']).hostname
        pages = {urlkey(p['url']): p for p in cat['pages']}
        rosters = {urlkey(r['url']): r for r in cat['rosters']
                   if r.get('source_qualification') in (None, 'faculty_roster')}
        rejected = {urlkey(i['url']) for i in cat['issues'] if i['issue_kind'] == 'source_not_faculty_roster'}
        soups = {}
    
        def evidence(person, profile_link=False):
            for observation in person['observations']:
                if observation.get('historical_roster'):
                    continue
                url = observation['source_url']; key = urlkey(url)
                roster = rosters.get(key); page = pages.get(key)
                if not roster or not page or key in rejected or urlparse(url).hostname != host:
                    continue
                label = compact(roster.get('branch', '') + ' ' + page.get('title', ''))
                if EXCLUDED.search(label):
                    continue
                path = root/page['directory']/'source.html'
                if key not in soups:
                    if not path.is_file():
                        continue
                    raw = path.read_bytes()
                    soup = BeautifulSoup(raw.decode('utf8', errors='replace'), 'html.parser')
                    for node in soup.select('script,style,nav,footer,header'):
                        node.decompose()
                    soups[key] = soup, hashlib.sha256(raw).hexdigest()
                soup, digest = soups[key]
                breadcrumb = ' '.join(n.get_text(' ',strip=True) for n in soup.select('.col_path,.breadcrumb,.column_path,.wp_breadcrumb,.tarrtrr'))
                if not FACULTY.search(label) and not FACULTY.search(breadcrumb):
                    continue
                if roster.get('source_qualification') is None:
                    # Legacy runs predate the qualification field. Require the
                    # saved document's own title as well as the roster metadata.
                    title = compact(soup.title.get_text() if soup.title else '')
                    if not (FACULTY.search(title) or FACULTY.search(breadcrumb)) or EXCLUDED.search(title):
                        continue
                name = person['name']; quote = None; row_text = ''
                if not profile_link and observation.get('source_kind')=='department_member':
                    from grouped_roster import verified_member
                    member=verified_member(soup,url,observation,name)
                    if member and not member['url']:
                        return {'source_url':url,'path':str(path.relative_to(root)),'sha256':digest,
                                'quote':member['evidence'],'row_text':'','branch':member['category']}
                if not profile_link:
                    for card in soup.select('.fc0 a.aa0'):
                        label_node=card.select_one(':scope > .dv1')
                        if (label_node and compact(label_node.get_text())==compact(name)
                                and not card.get('href','').strip() and len(compact(card.get_text()))<180):
                            return {'source_url':url,'path':str(path.relative_to(root)),'sha256':digest,
                                    'quote':str(card),'row_text':'','branch':roster.get('branch',''),
                                    'mechanism':'unlinked_named_faculty_card'}
                # A role-labelled personal biography is not a roster of every
                # coauthor, supervisor or commemorated person mentioned in it.
                own_label=re.split(r'[-_](?=[^-_]*(?:大学|学院))',page.get('title',''),maxsplit=1)[0]
                own_name=profile_label_name(own_label)
                if own_name!=own_label and re.search(r'研究生导师|行业导师|兼职教师|外聘教师',own_label) and own_name!=name:
                    continue
                if not profile_link and observation.get('table_row_path'):
                    from roster_tables import verified_row
                    row=verified_row(cat,root,observation)
                    if row and row['name']==name and row['confidence']>=.95:
                        return {'source_url':url,'path':str(path.relative_to(root)),'sha256':digest,
                                'quote':row['text'],'row_text':row['text'],'branch':roster.get('branch',''),
                                'table_row_path':observation['table_row_path']}
                    continue
                if profile_link:
                    for anchor in soup.select('a[href]'):
                        anchor_name = profile_label_name(re.sub(r'[\u200b\ufeff]', '', anchor.get_text(' ', strip=True)))
                        named = anchor_name == name or re.fullmatch(re.escape(name)+r'[（(][^()（）]{1,100}[)）]',anchor_name)
                        # The link owns an exact name label and rank/discipline
                        # text. Never accept a name merely mentioned in prose.
                        card_label=anchor.select_one(':scope > .dv1')
                        if card_label and compact(card_label.get_text())==compact(name) and len(anchor_name)<180:
                            named=True
                            row_text=anchor.get_text(' ',strip=True)
                        if named and not EXCLUDED.search(anchor_name) and urlkey(urljoin(url, anchor['href'])) == urlkey(person['profile_url']):
                            row = anchor.find_parent(['p','tr','li'])
                            if row:
                                value = row.get_text(' ', strip=True)
                                if re.search(r'行政|联系人|退休|离休|校友', value):
                                    continue
                                if len(compact(value)) <= 220 and len(row.select('a[href]')) == 1:
                                    row_text = value
                            quote = str(anchor); break
                else:
                    # Only names in saved article/roster content count, not a menu,
                    # a substring of somebody else's name, or an administrative row.
                    content = soup.select_one(CONTENT)
                    if content is None:
                        continue
                    section = ''
                    for block in content.select('tr,p,li'):
                        value = block.get_text(' ', strip=True)
                        clean = compact(value)
                        if len(clean) < 35 and re.fullmatch(r'[^：:]{1,18}[：:]\d*人?', clean):
                            section = clean
                        # A faculty card may describe teaching students. This
                        # is not the same as a student roster or contact row.
                        faculty_card = (block.name=='tr' and len(block.select('td'))==1 and block.find('img') is not None
                                        and any(compact(re.sub(r'[\u200b\ufeff]','',n.get_text()))==compact(name) for n in block.select('div,span,a')))
                        excluded_row = re.search(r'行政|辅导员|联系人|校友',value) or (not faculty_card and '学生' in value)
                        if EXCLUDED.search(section) or excluded_row or re.search(r'学生(?:名单|姓名|信息)|学生[:：]',value):
                            continue
                        pattern=r'(?<!['+HAN_CHARS+r'A-Za-z])'+r'\s*'.join(re.escape(c) for c in compact(name))+r'(?!['+HAN_CHARS+r'A-Za-z])'
                        if re.search(pattern, value):
                            quote = value
                            if len(compact(value))<=220:
                                # Only a single person's line may supply fields.
                                if re.match(r'^\s*'+r'\s*'.join(re.escape(c) for c in name)+r'\s*[：:,，]',value) and len(re.findall('[：:]',value))<=1:
                                    row_text=value
                            break
                if quote:
                    if not profile_link and not row_text:
                        for cell in content.select('td'):
                            if compact(cell.get_text())!=compact(name):continue
                            tr=cell.find_parent('tr');table=cell.find_parent('table')
                            if tr is None or table is None:continue
                            rows=table.find_all('tr');index=rows.index(tr)
                            for earlier in range(index,-1,-1):
                                first=rows[earlier].find(['td','th'],recursive=False)
                                if first is None:continue
                                rank=compact(first.get_text())
                                try:span=int(first.get('rowspan',1))
                                except (ValueError,TypeError):span=1
                                if rank in TITLES and earlier+span>index:
                                    row_text=f'{name}，{rank}。'
                                    quote=str(first)+'\n'+str(cell)
                                    break
                            if row_text:break
                    return {'source_url': url, 'path': str(path.relative_to(root)),
                            'sha256': digest, 'quote': quote, 'row_text': row_text, 'branch': roster.get('branch', ''),
                            'breadcrumb': breadcrumb}
            return None
    
        self.evidence = evidence


def associate(cat, root, items):
    evidence = RosterEvidence(cat, root).evidence
    groups = {}
    for person in cat['people']:
        groups.setdefault(person['name'], []).append(person)
    for name, group in groups.items():
        unlinked = [p for p in group if not p['profile_url'] and not items[p['id']]['fields']['biography']
                    and not p['review'].get('revision')]
        if not unlinked:
            continue
        profiles = [p for p in group if p['profile_url'] and items[p['id']]['status'] != 'duplicate']
        if len(profiles) != 1:
            continue
        canonical = profiles[0]; assessment = items[canonical['id']]
        if canonical['review'].get('revision') and canonical['review']['status'] != 'accepted':
            continue
        if any(any(word in a for word in ('身份', '姓名归属', '任职关系', '旧名单')) for a in assessment['anomalies']):
            continue
        if len(compact(assessment['fields']['biography'])) < 25:
            continue
        profile_proof = evidence(canonical, profile_link=True)
        if not profile_proof:
            continue
        for person in unlinked:
            item = items[person['id']]
            if any(o.get('historical_roster') for o in person['observations']):
                continue
            roster_proof = evidence(person)
            if not roster_proof:
                continue
            proof = {'policy': POLICY, 'name': name, 'university': cat['job']['target']['university'],
                     'college': cat['job']['target']['college'], 'canonical_id': canonical['id'],
                     'roster': roster_proof, 'personal_link': profile_proof}
            item.update(status='duplicate', canonical_id=canonical['id'], identity_link=proof,
                        anomalies=[], reason='本学院正式名单与唯一的本人主页相互佐证，已关联保留条目')
            assessment.setdefault('roster_associations', []).append({'person_id': person['id'], **proof})
