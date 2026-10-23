"""Evidence-bound field selection. Scores rank evidence; they are not probabilities."""
import re
import unicodedata
from person_names import clean_name,HAN_CHARS,is_person_name

POLICY = 'evidence-auto-v1'
TITLES = sorted(set('正高级实验师 高级实验师 实验师 助理实验师 教授 副教授 讲师 助教 研究员 副研究员 助理研究员 研究实习员 主任医师 副主任医师 主治医师 住院医师 医师 主任护师 副主任护师 主管护师 护师 主任技师 副主任技师 主管技师 技师 主任药师 副主任药师 主管药师 药师 正高级工程师 高级工程师 工程师 助理工程师'.split()), key=len, reverse=True)
TITLES=sorted(set(TITLES+['校聘教授','校聘副教授','特聘教授','兼职教授','客座教授','教授级高级工程师','教授级高工','副高级实验员','国家级教练','高级教练','中级教练','助理教练']),key=len,reverse=True)
TITLES=sorted(set(TITLES+['助理副教授']),key=len,reverse=True)
TITLE = re.compile('|'.join(TITLES))
LAYOUT_TITLE = re.compile('|'.join(r'\s*'.join(re.escape(c) for c in title) for title in TITLES))
EMAIL = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}(?![A-Za-z])')


def compact(text):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', text or ''))


def profile_label_name(label):
    value=unicodedata.normalize('NFKC',label or '').strip()
    # A complete card label, not a sentence mentioning a professor or a dean.
    ranked=re.fullmatch(r'(.+?)\s+('+TITLE.pattern+r')\s*/\s*(?:副?院长|副?系主任|党委(?:副)?书记|(?:副)?书记)',value)
    if ranked and is_person_name(ranked[1]) and not re.search(r'欢迎|邀请|来校|讲座|报告',ranked[1]):
        return clean_name(ranked[1])
    office=re.fullmatch(r'(.+?)\s+(?:副?院长|副?系主任|党委(?:副)?书记|(?:副)?书记)',value)
    if office and is_person_name(office[1]) and not re.search(r'欢迎|邀请|来校|讲座|报告',office[1]):return clean_name(office[1])
    value=re.sub(r'\s+(?:教授|副教授|讲师|助教|研究员|副研究员)$','',value)
    value=clean_name(value)
    # A role-labelled profile title has one name after an explicit separator.
    # Do not trim arbitrary news headlines that merely mention a professor.
    labelled=re.fullmatch(r'(?:['+HAN_CHARS+r']{2,24}学院)?(?:研究生导师|硕士生导师|博士生导师|行业导师|兼职教师|外聘教师)\s*[—－\-：:]+\s*(.+)',value)
    if labelled and is_person_name(labelled[1]) and not re.search(r'来校|讲座|报告|交流|参加|获奖|名单|简介|介绍|团队|风采',labelled[1]):value=clean_name(labelled[1])
    value=clean_name(re.sub(r'^(?:(?:硕士生|博士生)?导师|教师|个人)简介\s*[—－\-：:]\s*','',value))
    name=re.sub(r'(?:个人|教师)?简介$','',value)
    if name!=value and re.fullmatch('['+HAN_CHARS+'·]{2,8}',name) and name not in {'学院','学校','师资','教师','个人','团队','机构','专业','学科','导师','教授'}:
        return name
    return value


def teaching_evidence(text):
    text=compact(text)
    return bool(re.search(r'主讲|讲授|授课|承担.{0,15}课程|(?:硕士|博士)(?:研究生|生)?导师|专任教师|兼职教师',text)
                or re.search(r'(?:现任|现为)[^。；]{0,30}(?:学院|学系|教研室)教师',text[:1200])
                or re.search(r'从事[^。；]{0,35}课程教学',text[:1200]))


def biography_identity_after_metadata(name,text):
    """Recognize an opening self-description after a short explicit CMS header."""
    lines=[line.strip() for line in unicodedata.normalize('NFKC',text).splitlines() if line.strip()]
    if len(lines)<4 or lines[0] not in ('个人简历','个人简介') or lines[1]!='标签:':return None
    if len(lines[2])>160 or not re.fullmatch(r'时间:\s*\d{4}-\d{2}-\d{2}\s+点击:\s*\d+\s+来源:\s*[^\n]+',lines[2]):return None
    if not re.match(re.escape(compact(name))+r'[,，][男女][,，]',compact(lines[3])):return None
    return {'rule':'named_biography_after_explicit_cms_header','evidence':'\n'.join(lines[:4])[:500]}

def administrative_only(text,title):
    text=compact(text)
    clerical=re.search(r'教学干事|教学秘书|教务秘书|科研秘书|行政秘书|办公室秘书|辅导员|教辅人员|行政管理人员',text)
    teaching=teaching_evidence(text)
    return bool(clerical and not title and not teaching)


def profile_card(soup,body=None,names=()):
    # Personal-site card is a sibling of the long CV on WebPlus teacher templates.
    card = soup.select_one('.topleft')
    if card and card.select_one('h1.arti_title'):
        return (card.find_parent(class_='artitop') or card.find_parent(class_='wztop') or card).get_text('\n', strip=True)
    # Another WebPlus layout places labelled personal fields beside the portrait,
    # outside the resume container. Bind that card to the roster/body identity.
    for card in soup.select('.news_box .news_con'):
        label=card.select_one('.news_title')
        if label is None:continue
        match=re.fullmatch(r'姓名[:：](.+)',compact(label.get_text()))
        if not match or not is_person_name(match[1]):continue
        name=match[1]
        bound=name in {compact(n) for n in names} or (body is not None and compact(body.get_text()).startswith(name))
        if bound:return card.get_text('\n',strip=True)
    # Some article templates publish the person's rank only in the heading,
    # outside .wp_articlecontent. Bind the whole heading to an observed name
    # and ranks, without pulling publication dates, hit counts or news titles.
    for heading in soup.select('.article h1.arti_title'):
        label=compact(heading.get_text())
        for name in names:
            person=compact(name)
            if not person or not label.startswith(person):continue
            # This is a missing-field fallback. Do not let an abbreviated
            # heading replace a more specific rank already bound in the CV.
            if body is not None and fields_from_text(name,body.get_text('\n',strip=True))['title']['value']:continue
            suffix=label[len(person):].strip('()（）:：')
            rank_group='(?:'+TITLE.pattern+')'
            if re.fullmatch(rank_group+'(?:[、,，/]'+rank_group+')*',suffix):
                return heading.get_text(' ',strip=True)
    return ''


def pdf_table_rows(text):
    """Conservative row segmentation, anchored by name + sex + birth date + title.

    This does not infer multi-column reading order. Unmatched rows remain issues.
    """
    rows = []
    page = 1
    for line in text.splitlines():
        if m := re.fullmatch(r'\[page (\d+)\]', line.strip()):
            page = int(m[1])
            continue
        m = re.match(r'^\s*(['+HAN_CHARS+r'·]{2,8})\s+([男女])\s+(\d{4}[.年/-]\d{1,2})\s+(.+)', line)
        if not m or not TITLE.match(m[4]):
            continue
        rows.append({'name': m[1], 'page': page, 'text': line.strip(), 'row': len(rows)+1})
    return rows


def fields_from_text(name, text, branch='', identity_bound=False):
    name=compact(name)
    source = unicodedata.normalize('NFKC', re.sub(r'[\u2000-\u200b\ufeff]', '', text))
    candidates = []
    def offer(value, score, quote, rule):
        if value:
            value=value.replace('教授级高工','教授级高级工程师')
            candidates.append({'value': value, 'score': score, 'evidence': quote[:500], 'rule': rule})
    def titles(value):
        return list(dict.fromkeys(m[0] for m in TITLE.finditer(value)
            if not value[max(0,m.start()-3):m.start()].endswith('博士后')
            if not re.match(r'(课程|课|法|学|资格|指导|的指导|团队)', value[m.end():])))

    # Explicit labeled field, stop at the next semantic field, even if CMS split lines.
    for m in re.finditer(r'(?:职\s*称\s*(?:[/／]\s*职\s*务\s*)?|职\s*务\s*[/／]\s*职\s*称\s*)[:：]?\s*([^\n]*(?:\n[^\n]*)?)', source[:1800]):
        q = re.split(r'个人简介|教育经历|专业研究|研究方向|联系方式|邮箱|电话|出生|学位|职务', m[1])[0].strip()
        # Join only characters within a known rank; keep field/newline boundaries.
        # Compacting the whole value would turn "助教\n学历" into "助教学历".
        ts = titles(LAYOUT_TITLE.sub(lambda match: compact(match[0]),q[:75]))
        if ts:
            offer('、'.join(ts), 100, m[0], 'explicit_title')
    # Tabular rows have a direct person -> title binding.
    for row in pdf_table_rows(source):
        if row['name'] == name:
            tail = re.sub(r'^\S+\s+[男女]\s+\S+\s+', '', row['text'])
            head = tail.split()[0]
            offer('、'.join(titles(head)), 100, row['text'], 'person_table_row')
    # A separate one-line rank below the name is a teacher card, not course text.
    lines = [x.strip() for x in source[:650].splitlines() if x.strip()]
    if len(lines)>1 and compact(lines[0])==name and re.match(r'^[男女][,，。]',lines[1]):
        introduction=re.split(r'曾任|历任|曾于|师从|毕业于|研究方向|主持|项目',lines[1],maxsplit=1)[0]
        ts=titles(introduction[:200])
        if ts:
            offer('、'.join(ts),90,introduction,'named_biography_intro')
    for i, line in enumerate(lines[:12]):
        if compact(line) == name and i+1 < len(lines):
            ts = titles(lines[i+1])
            if ts and len(lines[i+1]) < 40 and not re.match(r'^[男女][,，。]',lines[i+1]) and not re.search(r'曾任|历任|师从|导师为',lines[i+1]):
                offer('、'.join(ts), 95, '\n'.join(lines[i:i+2]), 'personal_card')
    # Opening self-description. Do not borrow a supervisor's or past appointment's rank.
    opening = re.split(r'教育经历|教育背景|工作经历|学习经历|科研项目|学术论文|主要成果|发表论文', source[:900])[0]
    # PDF reading order can place the named basic profile after courses/projects.
    whole = compact(source)
    # Inline HTML spans can split a single sentence into many text lines.
    # A title immediately following the person's opening name is still bound
    # to that person, and outranks unrelated later research-centre appointments.
    introduction = re.sub(r'^【?简[介历]】?[:：]?', '', whole)
    if identity_bound:
        opening_rank=re.match(r'(?P<who>['+HAN_CHARS+r']{2,20}人|男|女)[,，](?P<title>'+ '|'.join(TITLES)+r')(?=[,，。；;])',introduction)
        if opening_rank:offer(opening_rank['title'],88,opening_rank[0],'heading_bound_opening_title')
    direct = re.match(re.escape(name) + r'[,，:：](' + '|'.join(TITLES) + r')(?=[,，。；;])', introduction) if name else None
    if direct:
        offer(direct[1], 89, direct[0], 'named_opening_title')
    # A short degree sentence may precede the current institutional title.
    # Only the initial self-description is eligible; histories/supervisors are
    # excluded. Keep all original material and candidate evidence.
    institutional = None
    intro_only = re.split(r'教育经历|教育背景|工作经历|学习经历|科研项目|学术论文|主要成果|发表论文', introduction)[0]
    if name and intro_only.startswith(name):
        for sentence in re.split(r'[。；;]', intro_only[:400])[:2]:
            if re.search(r'曾|历任|师从|导师为|指导教师|访问|\d{4}[年.]', sentence):
                continue
            match = re.search(r'(?:大学|学院)[^。；;]{0,35}?(?P<title>' + '|'.join(TITLES) + r')(?=[,，、。；;/]|$)', sentence)
            if match:
                institutional = (match['title'], sentence)
                break
    for match in re.finditer(r'(?:现任|现为|校聘)[^。；;]{0,60}',whole[:1800]):
        preceding=re.split(r'[。；;]',whole[:match.start()])[-1]
        if match[0].startswith('校聘') and re.search(r'曾任|曾担任|历任|此前|过去|当时',preceding):continue
        if re.search(r'师从|导师为|指导教师',preceding):continue
        ts=titles(match[0])
        if ts:offer('、'.join(ts),92,match[0],'current_appointment')
    named = re.findall(re.escape(name)+r'[,:，：][^。；;]{0,200}', whole) if name else []
    opening += '\n' + '\n'.join(named)
    for sentence in re.split(r'[。；;\n]', opening):
        clean = re.split(r'师从|导师为|指导教师|跟随',compact(sentence),maxsplit=1)[0]
        if not clean or '教授课程' in clean or re.search(r'曾任|曾担任|担任过|访问学者|访问教授', clean):
            continue
        if name in clean or (len(clean) < 140 and any(clean.startswith(t) for t in TITLES)):
            ts = titles(clean)
            if ts:
                offer('、'.join(ts), 88 if name in clean else 75, sentence, 'opening_description')
    if compact(branch) in TITLES:
        offer(compact(branch), 80, branch, 'roster_rank')
    if institutional and not any(c['score'] >= 88 for c in candidates):
        offer(institutional[0], 88, institutional[1], 'opening_institutional_title')
    candidates.sort(key=lambda x: -x['score'])
    selected = candidates[0] if candidates else {'value': '', 'score': 0, 'evidence': '', 'rule': 'not_stated'}
    anomalies = []
    top=[c for c in candidates if c['score']==selected['score']]
    if top:
        # A heading may abbreviate the same person's full named description.
        # Select an existing superset, never construct a union of contradictions.
        fuller=max(top,key=lambda c:len(set(c['value'].split('、'))))
        if all(set(c['value'].split('、'))<=set(fuller['value'].split('、')) for c in top):
            selected=fuller
        else:
            anomalies.append('同等依据的职称不一致')
    # Keep original text, normalize layout whitespace only in candidate values.
    email_text = re.sub(r'\s*@\s*', '@', source)
    # Recover layout-split addresses only inside an explicitly labelled email
    # field. Never append a guessed suffix or join somebody else's prose.
    wrapped = re.compile(r'((?:电子邮箱|联系邮箱|邮箱|[Ee]-?[Mm]ail)\s*[:：]\s*)([A-Za-z0-9._%+\-]+(?:[ \t]*\r?\n[ \t]*[A-Za-z0-9._%+\-]+)*\s*@\s*(?:[A-Za-z0-9\-]+\s*\.\s*)+[A-Za-z]{2,})(?![A-Za-z])')
    def join_labelled(match):
        value = re.sub(r'\s+', '', match[2])
        return match[1] + value if EMAIL.fullmatch(value) else match[0]
    email_text = wrapped.sub(join_labelled, email_text)
    # When a complete address is explicitly present elsewhere in this same
    # personal material, join an identical layout-split copy. Do not guess a
    # domain suffix or discard an independently printed shorter address.
    full_addresses=set(EMAIL.findall(email_text))
    for address in sorted(full_addresses,key=len,reverse=True):
        pattern=re.escape(address).replace(r'\.',r'\.\s*')
        email_text=re.sub(pattern,lambda match:address,email_text)
    emails = list(dict.fromkeys(EMAIL.findall(email_text)))
    email_candidates = []
    for value in emails:
        pos = email_text.find(value)
        quote = email_text[max(0, pos-35):pos+len(value)+20]
        public = bool(re.search(r'学院邮箱|办公室邮箱|招生邮箱|联系编辑|通讯作者|通信作者', quote))
        email_candidates.append({'value': value, 'score': 40 if public else 90, 'evidence': quote,
                                 'rule': 'public_or_publication_contact' if public else 'personal_body'})
    personal = [x for x in email_candidates if x['score'] >= 90]
    # Incomplete official values are exceptions; do not invent a missing .com.
    for match in re.finditer(r'\S*@\S*', email_text):
        token=match[0]
        context=email_text[max(0,match.start()-30):match.end()]
        # SRW@ACL2023). is a conference marker, not a malformed email address.
        likely_mail=('.' in token.split('@')[-1] and not re.search(r'@[^\s.]+[)）\]】]',token)) or bool(re.search(r'邮箱|邮件|[Ee]-?[Mm]ail',context))
        if likely_mail and not EMAIL.search(token):
            anomalies.append('邮箱格式不完整')
    return {'title': selected, 'title_candidates': candidates,
            'email': {'value': '; '.join(x['value'] for x in personal), 'score': 90 if personal else 0,
                      'evidence': '\n'.join(x['evidence'] for x in personal), 'rule': 'personal_body'},
            'email_candidates': email_candidates, 'anomalies': list(dict.fromkeys(anomalies))}
