"""Bound personal cards and repeated CV sections; no institution/URL exceptions."""
import re
from .person_names import HAN_CHARS,is_person_name

def normalized(value):
    return re.sub(r'\s+','',value or '')

SECTION_LABELS={'个人简介','学术兼职','教学课程','科研、教改项目','论文和专著','专利、软件著作权','荣誉和奖励','指导学生'}

def opening_alias_card(text,names,page_title=''):
    if len(names)!=1:return ''
    name=next(iter(names))
    if not is_person_name(name) or len(name.split())<2 or normalized(name) in normalized(page_title):return ''
    # The biography explicitly equates a Chinese transliteration with the
    # roster's full Latin name at its opening, not in a coauthor/reference list.
    pattern=r'^['+HAN_CHARS+r'·・]{2,25}[（(]'+re.escape(normalized(name))+r'[）)]'
    return name if re.match(pattern,normalized(text[:250])) else ''

def structured_profile(soup,names):
    names={normalized(n) for n in names if n}
    if len(names)!=1:return None
    # A CMS article heading and its sibling CV share one owner. The page title
    # may contain only the college name, so bind the exact visible person label.
    for article in soup.select('.in-det'):
        heading=article.select_one(':scope > .in-det-bt > .s1')
        body=article.select_one(':scope > .in-det-det > #vsb_content')
        if body is None:body=article.select_one(':scope > .in-det-det .v_news_content')
        label=normalized(heading.get_text()) if heading else ''
        labelled=label in names or any(re.fullmatch(re.escape(n)+r'[（(][A-Za-z.\-\x27]+[）)]',label) for n in names)
        if heading and labelled and body is not None:
            return {'body':body,'card':heading.get_text(strip=True),
                    'selector':'.in-det > .in-det-det > #vsb_content, .in-det > .in-det-det .v_news_content',
                    'rule':'named_heading_sibling_cv_v1'}
    # Same mechanism in a modern article layout: a named field card owns one
    # sibling CV container. News article titles or cards for others do not bind.
    for article in soup.select('.article'):
        card=article.select_one(':scope > .arti_top .news_wz')
        label=card.select_one('h1.news_title') if card else None
        body=article.select_one(':scope > .arti_bottom')
        if (label and normalized(label.get_text()) in names and card.select('.news_info .news_field')
                and body is not None and body.select('.entry')):
            return {'body':body,'card':card.get_text('\n',strip=True),'selector':'.article > .arti_bottom',
                    'rule':'named_article_card_and_cv_v1'}
    # A single CMS news widget owns both its name/contact card and long CV.
    # The bilingual copy belongs to a separate widget; do not combine it twice.
    for body in soup.select('.tearchContainer'):
        container=body.parent
        card=container.select_one(':scope > .top .carrer')
        label=card.select_one('.title .jsbt') if card else None
        if label and normalized(label.get_text()) in names:
            sections=body.select('.news_box .con')
            return {'body':body,'card':card.get_text('\n',strip=True),'selector':'.tearchContainer',
                    'rule':'named_widget_card_and_cv_v1',
                    'empty_cv':bool(sections) and not any(s.get_text(strip=True) or s.select('img,iframe,[pdfsrc]') for s in sections)}
    # Legacy table layout: an isolated name card and contact card precede one
    # repeated-section CV table. Require a single bound identity and one group.
    groups=[t for t in soup.select('table.wp_article_list_table') if t.select('.szpost-21')]
    if len(groups)!=1:return None
    body=groups[0];blocks=body.select('.szpost-21')
    labels=[b.select_one('.biaoti1') for b in blocks]
    if len(blocks)<2 or any(l is None or normalized(l.get_text()) not in SECTION_LABELS for l in labels):return None
    if '个人简介' not in {normalized(l.get_text()) for l in labels}:return None
    owner=body.find_parent('td')
    if owner is None:return None
    name_nodes=[n for n in owner.select('td.huizi') if normalized(n.get_text())]
    if len(name_nodes)!=1 or normalized(name_nodes[0].get_text()) not in names:return None
    contact=[t for t in owner.select('table.wp_article_list_table') if t is not body and not t.select('.szpost-21')
             and re.search(r'通讯方式|电子邮箱|联系邮箱',t.get_text()) and len(t.get_text())<1500]
    if len(contact)>1:return None
    card=name_nodes[0].get_text('\n',strip=True)
    if contact:card+='\n'+contact[0].get_text('\n',strip=True)
    return {'body':body,'card':card,'selector':'table.wp_article_list_table:has(.szpost-21)',
            'rule':'named_table_card_and_cv_sections_v1'}
