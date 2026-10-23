"""Save concrete source evidence for selected gains, losses and repetitions."""
from collections import Counter
import hashlib
import json
from pathlib import Path
from bs4 import BeautifulSoup
from evaluate import markdown_text, norm, retained_fraction

ROOT=Path(__file__).resolve().parent

def read(path):
    return json.loads(path.read_text(encoding='utf8'))

def main():
    samples=[
        ('fynu','徐华杰','https://www.fynu.edu.cn/hxycl/info/1047/4105.htm','2000xhj@163.com'),
        ('fynu','解金旋','https://www.fynu.edu.cn/hxycl/info/1049/8931.htm','xiejinxuan2025@163.com'),
        ('fynu','董秋静','https://www.fynu.edu.cn/hxycl/info/1047/4115.htm','dongqj1980@163.com'),
        ('fynu','杨池','https://www.fynu.edu.cn/hxycl/info/1049/7431.htm','youngchi0724@gmail.com'),
        ('seu','仇晓黎','https://me.seu.edu.cn/cxl/list.htm','qiuxiaoli@seu.edu.cn'),
        ('seu','陈震','https://me.seu.edu.cn/cz_31654/list.htm','zhenchen@seu.edu.cn'),
        ('seu','邓小鹏','https://civil.seu.edu.cn/dxp/list.htm','dxp@seu.edu.cn'),
        ('seu','李迎成','https://arch.seu.edu.cn/lyc/main.psp',''),
        ('seu','淳庆','https://arch.seu.edu.cn/2019/1228/c16785a304635/page.htm',''),
        ('seu','王海兵','https://math.seu.edu.cn/whb/list.htm',''),
        ('seu','张金霞','https://automation.seu.edu.cn/zjx/list.htm',''),
        ('seu','曾勇','https://radio.seu.edu.cn/2019/0613/c19937a277743/page.htm',''),
        ('seu','吴巍炜','https://cs.seu.edu.cn/weiweiwu/main.htm','weiweiwu@seu.edu.cn'),
        ('seu','祁磊','https://cs.seu.edu.cn/qilei/main.htm','qilei@seu.edu.cn'),
        ('seu','朱利','https://electronic.seu.edu.cn/zl/list.htm','li-zhu@seu.edu.cn'),
        ('seu','晏井利','https://smse.seu.edu.cn/2011/1121/c2590a83608/page.htm','jlyan@seu.edu.cn'),
    ]
    calls=read(ROOT/'fetch-api/calls.json')
    rows=[]
    for case,name,url,email in samples:
        pointer=ROOT/'runs'/case/('continued-pointer.json' if case=='seu' else 'capture-pointer.json')
        run=Path(read(pointer)['run_dir'])
        page=next(p for p in read(run/'pages.json') if p['url']==url)
        folder=run/page['directory']
        source=folder/'source.html'
        soup=BeautifulSoup(source.read_text(encoding='utf8',errors='replace'),'html.parser')
        for node in soup.select('script,style'):
            node.decompose()
        raw_text=soup.get_text('',strip=True)
        body=run/(page.get('body_path') or page['directory']+'/body-text.txt')
        native=body.read_text(encoding='utf8') if body.is_file() else ''
        call=next(c for c in reversed(calls) if c['url']==url and c['status']=='ok')
        response=ROOT/'fetch-api'/f"{call['index']:04}-{hashlib.sha256(url.encode()).hexdigest()[:16]}-response.json"
        fetched,_=markdown_text(read(response)['content'])
        counts=Counter(norm(line) for line in fetched.splitlines() if len(norm(line))>=80)
        repeats=[{'normalized_excerpt':line[:180],'fetch_occurrences':count,
                  'native_occurrences':norm(native).count(line)}
                 for line,count in counts.items() if count>1][:5]
        probes={
            '王海兵':'On the convergence of the no-response test for the heat equation',
            '张金霞':'A prior-based graph for salient object detection',
            '曾勇':'Joint base station selection and linear precoding for networks with multi-cell processing',
        }
        marker=probes.get(name)
        rows.append({'case':case,'name':name,'url':url,'source':str(source),'fetch_response':str(response),
            'email_checked':email or None,
            'email_in_original_visible_html':email.lower() in raw_text.lower() if email else None,
            'email_contiguous_in_native_body':email.lower() in native.lower() if email else None,
            'email_in_fetch_plaintext':email.lower() in fetched.lower() if email else None,
            'native_chars':len(native),'fetch_plaintext_chars':len(fetched),
            'native_32char_window_retention':retained_fraction(native,fetched),
            'repeated_long_passages':repeats,
            'biography_item_check':({'item':marker,'in_native':norm(marker) in norm(native),
                                     'in_fetch':norm(marker) in norm(fetched)} if marker else None),
            'limit':'Selected contact fields and repeated passages only; not full biography correctness certification.'})
    (ROOT/'spot-checks.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps([{'name':x['name'],'native_email':x['email_contiguous_in_native_body'],
                      'fetch_email':x['email_in_fetch_plaintext'],'repeated_long_passages':len(x['repeated_long_passages'])} for x in rows],ensure_ascii=False))

if __name__=='__main__':main()
