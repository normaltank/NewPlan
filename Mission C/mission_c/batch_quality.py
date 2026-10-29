"""Conservative batch admission, retaining every original and candidate verbatim."""
import re
from bs4 import BeautifulSoup
from .extract import name_candidates


def assess(record, folder):
    code = record.get('error',{}).get('code','')
    if code.startswith('http_') or code in {'network_error','redirect_limit'}:
        return {'category':'origin_unavailable','eligible_for_workbook':bool(record.get('name') and record.get('field_status',{}).get('name') in {'found','found_model_evidence'}),'reasons':[code,'只有已有可靠教师身份才纳入主页失效表']}
    source = folder/record.get('source_file','')
    html = source.read_bytes() if source.is_file() else b''
    soup = BeautifulSoup(html,'html.parser')
    titles = [re.split(r'[-|_—]',tag.get_text(' ',strip=True),maxsplit=1)[0] for tag in soup.select('title')]
    main = soup.select_one('main,article') or soup
    headings = ' '.join(titles + [tag.get_text(' ',strip=True) for tag in main.select('h1') if not tag.find_parent(['nav','header','footer'])])
    for tag in main.select('nav,header,footer'): tag.decompose()
    page = main.get_text(' ',strip=True)
    primary = main.select('h1,.arti_title,.news_title,.jsbt')
    primary_names = {c['value'] for node in primary
                     for c in name_candidates(BeautifulSoup(str(node),'html.parser'))}
    name = record.get('name','')
    evidence = record.get('field_evidence',{}).get('name_candidates',[])
    explicit_name = any(c.get('value') == name and c.get('rule') in
                        {'labelled_name','known_profile_card'} for c in evidence)
    profile_sections = any(re.fullmatch(r'个人简介|基本信息|教育经历|工作经历|研究方向|联系方式',tag.get_text(' ',strip=True).rstrip(':：'))
                           for tag in main.select('h2,h3'))
    profile_identity = bool(name and (explicit_name or (name in primary_names and
                            (record.get('title') or record.get('email') or profile_sections))))
    # Service state must come from the main content, not navigation or a quoted
    # notice. A title-shaped name alone cannot defeat a current outage message;
    # an independently supported profile can discuss or quote such messages.
    service_scope = BeautifulSoup(str(main),'html.parser')
    for tag in service_scope.select('nav,header,footer,aside,blockquote,q,script,style'): tag.decompose()
    service_text = service_scope.get_text(' ',strip=True)
    service_state = r'(?:网站|系统|本站|本网站|本?平台|服务器|服务)\s*(?:(?:目前|当前|正在|正|现|暂时|进行)\s*){0,4}(?:升级|维护)\s*(?:升级|维护|中)?'
    interruption = r'(?:(?:暂停|停止)(?:访问|服务)|暂(?:时)?(?:无法访问|不可用)|稍后(?:再)?(?:重试|访问|再试))'
    current_interruption = re.search(service_state+r'.{0,120}'+interruption+'|'+interruption+r'.{0,120}'+service_state,service_text)
    if current_interruption and not profile_identity:
        return {'category':'temporarily_unavailable','eligible_for_workbook':False,'reasons':['主内容明确网站/系统正在维护升级并中断访问；缺少独立个人身份，原候选保留']}
    maintenance = re.search(r'^(?:安全验证(?:\s|$)|访问验证(?:\s|$)|人机验证(?:\s|$)|网站暂时无法访问|service unavailable|under maintenance|just a moment|verify you are human)',headings,re.I)
    notice = re.search(r'^(?:(?:系统|网站|本站|本网站|本?平台|服务器|服务)?(?:正在|目前|当前)?(?:维护|升级)(?:维护|升级)?(?:中|公告|通知)?|(?:访问|服务)(?:提示|提醒|公告))(?:\s|$)',headings)
    if maintenance and not profile_identity:
        return {'category':'temporarily_unavailable','eligible_for_workbook':False,'reasons':['维护或验证模板标题: '+maintenance.group(0)]}
    if notice and not profile_identity:
        return {'category':'identity_review','eligible_for_workbook':False,'reasons':['维护/访问提示标题缺少当前服务中断的主内容及独立个人身份，页面身份待核；原候选保留']}
    nonpersonal = re.search(r'^(?:.*学院首页|学院概况|师资队伍|教师名单|师资列表|新闻动态|新闻详情|新闻中心|学院新闻|通知公告)(?:\s|$)',headings)
    home = '欢迎访问' in page and sum(word in page for word in ['师资队伍','学院概况','新闻动态','人才培养']) >= 3
    news_structure = main.name == 'article' and any('news' in str(value).lower() for value in [main.get('class',[]),main.get('id','')]) and bool(main.select_one('time,[class*=time],[class*=date]'))
    news_report = bool(re.search(r'参加|出席|应邀|报告会|举行|召开|来访',headings))
    # A timestamped news article with a report headline is not a profile merely
    # because its body labels a person's name. A profile identity heading still
    # permits reused article templates and their publication metadata.
    if nonpersonal or home or (news_structure and (news_report or not primary_names)):
        return {'category':'suspected_non_personal','eligible_for_workbook':False,'reasons':['明确首页/名单/新闻模板信号，需人工核对']}
    if record.get('biography_source') == 'deepseek-fetch':
        return {'category':'provider_candidate','eligible_for_workbook':False,'reasons':['提供方候选未证明原站或个人身份']}
    if record.get('name') and record.get('biography'):
        # The collector's heading candidates include h2 section headings. A
        # candidate is not identity proof: require an independent primary slot
        # or its existing explicit-name/title evidence. Reuse the collector's
        # vocabulary rather than building another name extractor here.
        corroborated = any(c.get('value') == name and c.get('rule') in
                           {'labelled_name','page_title','known_profile_card'} for c in evidence)
        if not corroborated and name not in primary_names:
            return {'category':'identity_review','eligible_for_workbook':False,
                    'reasons':['采集器姓名仅有次级标题候选，缺少主身份位置或明确姓名/标题佐证；原候选保留']}
        return {'category':'personal_candidate','eligible_for_workbook':True,'reasons':['既有采集器取得个人姓名及正文；仍遵守字段待核状态']}
    return {'category':'identity_review','eligible_for_workbook':False,'reasons':['个人身份材料不足，保留候选待核；不据此断言非个人页']}
