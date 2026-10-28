"""Treat model output as quoted proposals, never as replacement biography text."""
import json
import re

from bs4 import BeautifulSoup
from soupsieve import SelectorSyntaxError

from .extract import text_of, section_text

from .fetch import SourceError
from .person_names import clean_name, is_person_name
from .quality_fields import compact, EMAIL, TITLE


def parse_response(raw, url):
    try:
        response = json.loads(raw)
        choice = response['choices'][0]
        if choice['finish_reason'] != 'stop':
            raise SourceError('model_incomplete_response', '模型响应未正常完成')
        plan = json.loads(choice['message']['content'])
        if not isinstance(plan, dict) or plan.get('url', url) != url:
            raise SourceError('model_url_mismatch', '模型建议 URL 与输入不匹配')
        for field in ('name', 'title', 'email'):
            item = plan.get(field)
            if not isinstance(item, dict) or not all(isinstance(item.get(k), str) for k in ('value', 'evidence')):
                raise ValueError('字段必须含 value 和 evidence 字符串')
        if not isinstance(plan.get('body_selector', ''), str):
            raise ValueError('body_selector 必须为字符串')
        return plan, response.get('usage')
    except (ValueError, TypeError, KeyError, IndexError) as error:
        raise SourceError('model_invalid_response', '模型响应 JSON 或字段形状无效') from error


def clean_source(data):
    soup = BeautifulSoup(data, 'html.parser')
    for node in soup.select('script,style,nav,aside,footer,template,svg,[role=navigation],[role=complementary],.sidebar,.side-bar,#sidebar'):
        node.decompose()
    return soup


def identity_in(node, name):
    for heading in node.select('h1,h2,.arti_title,.news_title'):
        label = compact(heading.get_text())
        if label == compact(name) or re.fullmatch(re.escape(compact(name)) + r'[（(]?(?:教授|副教授|讲师)[）)]?', label):
            return True
    return bool(re.search(r'姓名[:：]' + re.escape(compact(name)) + r'(?:$|[^\w\u4e00-\u9fff])',
                          node.get_text('\n', strip=True).replace(' ', '')))


def owned_quote(soup, quote, name):
    """Find a visible quote in a personal block, excluding institutional contacts."""
    needle = compact(quote)
    matches = [node for node in soup.find_all(True) if needle and needle in compact(node.get_text())]
    matches.sort(key=lambda node: len(compact(node.get_text())))
    for node in matches:
        for scope in [node, *node.parents]:
            if scope.name in ('html', 'body', '[document]'):
                break
            text = scope.get_text('\n', strip=True)
            if len(text) > 12000:
                break
            if identity_in(scope, name):
                return node
    return None


def disallowed_context(node, quote):
    context = node.get_text(' ', strip=True) + ' ' + quote
    if re.search(r'学院邮箱|办公室邮箱|招生邮箱|公共邮箱|联系编辑|通讯作者|通信作者|合作者|师从|导师为|指导教师', context):
        return True
    # A contact inside a publication list is evidence about the publication,
    # even when the enclosing article is this person's profile.
    for scope in [node, *node.parents]:
        if scope.name in ('body', 'html', '[document]'):
            break
        heading = scope.find_previous_sibling(['h2', 'h3', 'h4'])
        if heading and re.search(r'论文|成果|publications', heading.get_text(), re.I):
            return True
    return False


def apply_model(raw, metadata, data, record, folder):
    result = {**metadata, 'status': 'validated', 'candidates': {}}
    record['model'] = result
    plan, usage = parse_response(raw, record['requested_url'])
    result.update(proposal=plan, usage=usage)
    soup = clean_source(data)
    proposed_name = clean_name(plan['name']['value'])
    person = record['name'] or proposed_name
    for field in ('name', 'title', 'email'):
        item = plan[field]
        candidate = {**item, 'status': 'not_proposed', 'reason': 'empty_value'}
        result['candidates'][field] = candidate
        if not item['value']:
            continue
        if not item['evidence'] or compact(item['value']) not in compact(item['evidence']):
            candidate.update(status='rejected', reason='value_not_quoted')
            continue
        if compact(item['evidence']) not in compact(soup.get_text()):
            candidate.update(status='rejected', reason='quote_not_in_source')
            continue
        node = owned_quote(soup, item['evidence'], person)
        if node is None:
            candidate.update(status='unconfirmed', reason='personal_ownership_not_confirmed')
            continue
        if disallowed_context(node, item['evidence']):
            candidate.update(status='rejected', reason='other_person_or_public_context')
            continue
        if field == 'name' and not is_person_name(proposed_name):
            candidate.update(status='rejected', reason='invalid_person_name')
            continue
        value = proposed_name if field == 'name' else item['value']
        if field == 'title':
            qualifications = re.findall(r'(?:博士生|硕士生|博士研究生|硕士研究生)导师', value)
            ranks = list(dict.fromkeys(TITLE.findall(value)))
            remainder = TITLE.sub('', re.sub(r'(?:博士生|硕士生|博士研究生|硕士研究生)导师', '', value))
            if not ranks or remainder.strip(' ，,、;/；。\n\t'):
                candidate.update(status='rejected', reason='not_professional_title')
                continue
            value = '、'.join(ranks)
            candidate.update(professional_value=value, qualifications=qualifications)
        if field == 'email' and (not EMAIL.fullmatch(value) or not re.search(r'邮箱|邮件|[Ee]-?[Mm]ail|欢迎联系', item['evidence'])):
            candidate.update(status='unconfirmed', reason='personal_email_label_missing')
            continue
        if record[field]:
            candidate.update(status='corroborated' if record[field] == value else 'conflict',
                             reason='existing_trusted_value_preserved')
        else:
            record[field] = value
            record['field_status'][field] = 'found_model_evidence'
            record.setdefault('field_evidence', {})[field + '_model'] = {
                'value': value, 'evidence': item['evidence'], 'rule': 'model_personal_quote',
                'source_sha256': metadata['source_sha256']}
            candidate.update(status='applied', reason='personal_quote_verified')
    selector = plan.get('body_selector', '')
    selection = result['selector'] = {'proposal': selector, 'status': 'not_proposed'}
    if selector:
        try:
            nodes = soup.select(selector)
            if len(nodes) != 1:
                selection['status'] = 'not_unique'
            else:
                text = text_of(nodes[0])
                if compact(record['biography']) not in compact(text):
                    selection['status'] = 'would_shrink'
                elif not identity_in(nodes[0], record['name'] or person):
                    selection['status'] = 'identity_not_confirmed'
                else:
                    record.update(biography=text, content_selection='model_selector_verified',
                                  **section_text(nodes[0]))
                    (folder / 'biography.txt').write_text(text, encoding='utf-8')
                    selection['status'] = 'applied'
        except SelectorSyntaxError:
            selection['status'] = 'invalid_selector'
    result['status'] = 'evaluated' 
    return result
