"""Conservative OCR relevance checks; original images and OCR are never removed."""
import re
import hashlib
from collections import Counter
from urllib.parse import urljoin
from bs4 import BeautifulSoup, Tag

from PIL import Image
from quality_fields import TITLE, compact


def named_image_title(root, page, media, name):
    """An exact named rank card in the saved personal body, with original bytes."""
    if not page or not page.get('body_selector') or not page.get('directory'):
        return None
    candidates=[]
    for item in media:
        lines=[line for line in item.get('lines',[]) if compact(line.get('text',''))]
        if not 2<=len(lines)<=12 or compact(lines[0]['text'])!=compact(name):continue
        rank=compact(lines[1]['text'])
        if not TITLE.fullmatch(rank) or any(line.get('confidence',0)<.98 for line in lines[:2]):continue
        path=(root/item['directory']/item['source_file']).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():continue
        if hashlib.sha256(path.read_bytes()).hexdigest()!=item.get('sha256'):continue
        source=root/page['directory']/'source.html'
        if not source.is_file():continue
        raw=source.read_bytes();soup=BeautifulSoup(raw,'html.parser')
        try:body=soup.select_one(page['body_selector'])
        except Exception:continue
        if body is None:continue
        urls={urljoin(page.get('loaded_url') or page['url'],i.get('src') or i.get('data-src') or '') for i in body.select('img')}
        if item.get('source_url') not in urls:continue
        candidates.append({'value':rank,'score':95,'rule':'named_original_image_card',
                           'evidence':'\n'.join(line['text'] for line in lines[:2]),
                           'image_path':str(path.relative_to(root.resolve())),'image_sha256':item['sha256'],
                           'page_path':str(source.relative_to(root)),'page_sha256':hashlib.sha256(raw).hexdigest()})
    if len({item['value'] for item in candidates})==1:return candidates[0]
    return None

VERSION = 'image-relevance-v1'
BIO = re.compile(r'姓名|职称|简历|简介|研究方向|研究领域|教育经历|工作经历|联系方式|'
                 r'邮箱|电话|手机|邮件|电子信箱|毕业|任职|现任|从事|主持|发表|承担|'
                 r'博士|硕士|学士|出生|生于|获奖|论文|专利|著作|课题|项目|课程|'
                 r'@|\b(?:e-?mail|professor|research|biography|curriculum|education|phone)\b', re.I)
SCENE = re.compile(r'研讨会|学术会议|会议现场|培训.{0,6}基地|大学|学院|医院|'
                   r'\b(?:university|college|hospital|conference)\b', re.I)


def native_biography(root, person, text):
    """Use the pre-OCR body, never let background OCR validate itself."""
    if person.get('body_path'):
        path = (root / person['body_path']).parent / 'native-text.txt'
        if path.is_file():
            return path.read_text(encoding='utf-8')
    return text.split('[图片文字 / OCR', 1)[0].split('[个人页 PDF 附件全文]', 1)[0]


def photo_texture(root, media):
    # This is a weak visual signal, not a face detector. It is used only alongside
    # sparse scene text, no personal-data cues, and an independent native biography.
    try:
        path = root / media['directory'] / media['source_file']
        with Image.open(path) as original:
            if original.width * original.height > 40_000_000:
                return None
            sample = original.convert('RGB').resize((128, 128))
            pixels = sample.tobytes()
            colors = Counter(tuple(channel // 32 for channel in pixels[i:i+3])
                             for i in range(0, len(pixels), 3))
        return round(max(colors.values()) / (128 * 128), 4)
    except (OSError, ValueError, KeyError):
        return None


ART_HEADING = re.compile(r'^(?:个人作品|代表作品|代表作|作品展示|作品欣赏|书法作品|绘画作品|设计作品)[:：]?$')
RESUME_IMAGE = re.compile(r'简历|简介|履历|职称|教授|讲师|助教|研究员|邮箱|联系方式|教育经历|工作经历|研究方向|电子信箱|@|\b(?:biography|curriculum|professor|e-?mail)\b', re.I)


def artwork_context(root, page, images):
    """Prove image membership in an explicitly headed artwork section of the saved body."""
    if not page or not page.get('body_selector') or not page.get('directory'):
        return {}
    path = root/page['directory']/'source.html'
    if not path.is_file():
        return {}
    raw = path.read_bytes()
    soup = BeautifulSoup(raw.decode('utf8', errors='replace'), 'html.parser')
    try:
        body = soup.select_one(page['body_selector'])
    except Exception:
        return {}
    if body is None:
        return {}
    by_url = {m.get('source_url'):m for m in images.values()}
    active = None; found = {}
    for node in body.descendants:
        if not isinstance(node, Tag):
            continue
        if node.name == 'img':
            url = urljoin(page['url'], node.get('src') or node.get('data-src') or '')
            media = by_url.get(url, {})
            lines = media.get('lines', [])
            label = compact(media.get('text',''))
            # A graphic section title is evidence only when every word is clear.
            if ART_HEADING.fullmatch(label) and lines and all(x.get('confidence',0)>=.98 for x in lines):
                active = {'heading':label,'heading_image':media['directory']}
                found[url] = {**active,'path':str(path.relative_to(root)),
                              'sha256':hashlib.sha256(raw).hexdigest(),'image_url':url}
            elif len(label)<=20 and RESUME_IMAGE.search(label):
                active = None
            elif active:
                found[url] = {**active,'path':str(path.relative_to(root)),
                              'sha256':hashlib.sha256(raw).hexdigest(),'image_url':url}
        elif node.name in ('p','h1','h2','h3','h4','h5','h6','figcaption','td') and not node.find(['p','h1','h2','h3','h4','h5','h6','td']):
            label = compact(node.get_text(' ',strip=True))
            if ART_HEADING.fullmatch(label):
                active = {'heading':label}
            elif label and (RESUME_IMAGE.search(label) or len(label)>60 or node.name.startswith('h')):
                active = None
    return found


def without_artwork_ocr(text, media, assessments):
    """Filter delivery text only; all raw body/OCR files remain intact."""
    excluded = {m['directory'] for m in assessments if m['role']=='artwork'}
    marker = '[图片文字 / OCR 待复核]'
    if not excluded or marker not in text:
        return text
    prefix, tail = text.split(marker,1)
    _, pdf, pdf_text = tail.partition('[个人页 PDF 附件全文]')
    kept = '\n\n'.join(m.get('text','') for m in media if m['directory'] not in excluded and m.get('text'))
    return prefix.rstrip()+ ('\n\n'+marker+'\n'+kept if kept else '')+ ('\n\n'+pdf+pdf_text if pdf else '')


def triage_image(media, root, name, native, page_title='', artwork=None):
    lines = [line for line in media.get('lines', []) if compact(line.get('text', ''))]
    text = compact(media.get('text') or '\n'.join(line['text'] for line in lines))
    native = compact(native)
    # Some templates put the name only in the native page heading; a concise
    # clinical biography can also be valid. Neither alone proves image relevance.
    native_identity = bool(name) and (compact(name) in native[:220] or compact(name) in compact(page_title))
    native_ok = len(native) >= 25 and native_identity and bool(BIO.search(native) or TITLE.search(native))
    personal = bool(BIO.search(text) or TITLE.search(text) or (name and compact(name) in text))
    dense = len(lines) >= 8 or len(text) >= 160
    low = [line for line in lines if line.get('confidence', 0) < .85]
    low_quality = bool(lines and len(low) / len(lines) > .1)
    # Even one uncertain email/title line matters, whatever the total line count.
    critical_low = any(BIO.search(compact(line['text'])) or TITLE.search(compact(line['text']))
                       or (name and compact(name) in compact(line['text'])) for line in low)
    result = {'directory': media['directory'], 'policy': VERSION,
              'signals': {'native_biography': native_ok, 'personal_text': personal,
                          'line_count': len(lines), 'text_chars': len(text),
                          'low_confidence_lines': len(low)}}

    def finish(role, review, reason):
        return {**result, 'role': role, 'review_required': review, 'reason': reason}

    if artwork and native_ok and not RESUME_IMAGE.search(text):
        result['section_evidence'] = artwork
        return finish('artwork', False, '官网明确作品栏目中的图片，且已取得独立个人简介；作品原图保留，书画 OCR 不作为简历字段')
    if personal or dense:
        return finish('material_text', low_quality or critical_low or not lines,
                      '疑似个人资料文字，存在低置信度识别，需要对照原图' if low_quality or critical_low or not lines
                      else '疑似个人资料文字，OCR 质量检查通过；原图可抽查')
    if not native_ok:
        return finish('uncertain', True, '尚无足够的独立个人简介，不能确定图片是否承载简历正文')
    if not text:
        return finish('no_text', False, '未识别出图片文字，已取得独立个人简介；原图保留可抽查')
    if len(lines) < 8 and len(text) < 160 and SCENE.search(text):
        dominant = photo_texture(root, media)
        result['signals']['dominant_color_fraction'] = dominant
        if dominant is not None and dominant < .45:
            return finish('scene_text', False, '少量场景或标牌文字，具有照片纹理；已取得独立个人简介，无个人字段线索，无需单独复核')
    if len(text) < 20 and all(len(compact(line['text'])) < 12 for line in lines):
        return finish('fragment', False, '仅有零碎文字且无个人字段线索，已取得独立个人简介，无需单独复核')
    return finish('uncertain', low_quality or not lines,
                  '图片文字用途不明确且识别不稳定，需要对照原图' if low_quality or not lines
                  else '图片文字 OCR 质量检查通过；用途未确定，原图可抽查')
