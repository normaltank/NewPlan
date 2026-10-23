"""One official image, one named biography. Keep OCR evidence independently verifiable."""
import hashlib
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from person_names import clean_name,is_person_name,HAN_CHARS
from quality_fields import TITLE,compact,EMAIL

VERSION='named-image-biography-v1'
HEAD=re.compile(r'^(['+HAN_CHARS+r'·・\s]{2,12})[，,:：]\s*(?:(?:博士|硕士)[，,]\s*)?(?:副教授|教授|讲师|助教|研究员|副研究员)')

def image_biography(media):
    text=media.get('text','').strip();lines=[x for x in media.get('lines',[]) if x.get('text','').strip()]
    if not lines:return None
    heading=HEAD.match(lines[0]['text'])
    if not heading:return None
    name=clean_name(heading[1])
    if not is_person_name(name) or not text.startswith(lines[0]['text'].strip()):return None
    if any(HEAD.match(x['text']) for x in lines[1:]):return None
    if len(compact(text))<35 or sum(bool(re.search(k,text)) for k in ('开设课程','研究领域|研究方向','联系方式|邮箱'))<2:return None
    return {'name':name,'text':text,'confidence':min(x.get('confidence',0) for x in lines),
            'media_directory':media['directory'],'sha256':media['sha256']}

def verify_observation(cat,root,o):
    media=next((m for m in cat['media'] if m['directory']==o.get('person_image')),None)
    card=image_biography(media) if media else None
    if not card or card['name']!=o['name']:return ['图片简介姓名与保存的识别原文不一致']
    source=(root/media['directory']/media['source_file']).resolve();body=(root/o.get('person_body_path','')).resolve()
    if (not source.is_relative_to(root.resolve()) or not source.is_file() or
        hashlib.sha256(source.read_bytes()).hexdigest()!=media['sha256'] or
        not body.is_relative_to(root.resolve()) or not body.is_file() or body.read_text(encoding='utf8')!=card['text']):
        return ['图片简介原件或分人正文校验失败']
    page=next((p for p in cat['pages'] if p['url']==o['source_url']),None)
    roster=next((r for r in cat['rosters'] if r['url']==o['source_url'] and r.get('source_qualification')=='faculty_roster'),None)
    if not page or not roster:return ['图片简介缺少正式师资名单来源']
    raw=root/page['directory']/'source.html'
    soup=BeautifulSoup(raw.read_bytes(),'html.parser') if raw.is_file() else None
    try:owner=soup.select_one(o.get('image_body_selector') or 'codex-no-match') if soup else None
    except Exception:owner=None
    if owner is None or not any(urljoin(page.get('loaded_url',page['url']),n.get('src') or n.get('data-src') or '')==media['source_url'] for n in owner.select('img')):
        return ['图片简介未能与保存的师资正文对应']
    problems=[]
    if card['confidence']<.95:problems.append('图片简介存在低置信度文字，需对照原图')
    # A contact line resembling a damaged email is evidence of uncertainty,
    # not evidence that the teacher has no email. Never insert a guessed @.
    contact=re.search(r'(?:联系方式|邮箱)\s*[:：]\s*([^\n]*(?:\n[^\n]+)?)',card['text'])
    if contact:
        value=compact(contact[1])
        if re.search(r'(?i)\.(?:com|cn|edu|net|org)\b',value) and not EMAIL.search(value):
            problems.append('图片联系方式疑似邮箱但识别格式不完整')
        if re.match(r'\d\s*\n',contact[1]):problems.append('图片邮箱附近有分离字符，需对照原图')
        if any(re.match(r'[10][A-Za-z]{2}',m[0]) for m in EMAIL.finditer(value)):
            problems.append('图片邮箱开头的数字与字母易混淆，需对照原图')
    return problems
