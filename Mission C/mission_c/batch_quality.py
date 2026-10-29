"""Conservative batch admission, retaining every original and candidate verbatim."""
import re
from bs4 import BeautifulSoup


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
    maintenance = re.search(r'^(?:(?:系统|网站)(?:正在)?(?:维护|升级)|安全验证(?:\s|$)|访问验证(?:\s|$)|人机验证(?:\s|$)|网站暂时无法访问|service unavailable|under maintenance|just a moment|verify you are human)',headings,re.I)
    if maintenance:
        return {'category':'temporarily_unavailable','eligible_for_workbook':False,'reasons':['维护或验证模板标题: '+maintenance.group(0)]}
    nonpersonal = re.search(r'^(?:.*学院首页|学院概况|师资队伍|教师名单|师资列表|新闻动态|新闻详情|新闻中心|学院新闻|通知公告)(?:\s|$)',headings)
    home = '欢迎访问' in page and sum(word in page for word in ['师资队伍','学院概况','新闻动态','人才培养']) >= 3
    news_structure = main.name == 'article' and any('news' in str(value).lower() for value in [main.get('class',[]),main.get('id','')]) and bool(main.select_one('time,[class*=time],[class*=date]'))
    news_report = bool(re.search(r'参加|出席|应邀|报告会|举行|召开|来访',headings))
    if nonpersonal or home or (news_structure and news_report):
        return {'category':'suspected_non_personal','eligible_for_workbook':False,'reasons':['明确首页/名单/新闻模板信号，需人工核对']}
    if record.get('biography_source') == 'deepseek-fetch':
        return {'category':'provider_candidate','eligible_for_workbook':False,'reasons':['提供方候选未证明原站或个人身份']}
    if record.get('name') and record.get('biography'):
        return {'category':'personal_candidate','eligible_for_workbook':True,'reasons':['既有采集器取得个人姓名及正文；仍遵守字段待核状态']}
    return {'category':'identity_review','eligible_for_workbook':False,'reasons':['个人身份材料不足，保留候选待核；不据此断言非个人页']}
