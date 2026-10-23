"""Reference checks recorded after viewing the actual document images."""
import shutil
from prepare import ROOT, read, save, sha

docs=read(ROOT/'documents.json')
for item in docs:
    if item['id']=='d01':
        item['visual_checks']={'page':1,'rows':24,'first_name':'王芳','last_name':'季建红',
            'incomplete_email':{'name':'严海鸥','visible':'yho0704@163.','status':'incomplete_in_visible_original'},
            'scope':'Page 1 visual verification; all pages separately compared with original table rows.'}
    if item['id'] in ('d02','d03'):
        item['visual_verification']='name, declared title and section boundaries verified from original image'
        item['expected']['email']=None
        item['expected']['email_status']='not_shown_in_this_image'
    if item['id']=='d02':
        item['expected']['markers']=['装饰艺术研究','美术学科教学','2006年6月','副教授','2016']
    if item['id']=='d03':
        item['expected']['markers']=['历史学博士','讲师','中国古代书画鉴定与研究','明清文化史','2025']
    if item['id']=='d04':
        item['visual_verification']='portrait with decorative restaurant inscription; no faculty biography/contact statement in image'
        item['expected']['should_create_person_from_text']=False
folder=ROOT/'sources/d05'
folder.mkdir(parents=True,exist_ok=True)
source=folder/'source.png'
shutil.copy2(ROOT/'sources/d01/page-1.png',source)
docs.append({'id':'d05','kind':'derived_scan_control','source':str(source),'sha256':sha(source),
    'derived_from':'d01 page 1, rasterized with pdftoppm at 2200-pixel maximum dimension',
    'expected_rows':24,'independent_real_document':False,
    'purpose':'Same known table without a PDF text layer; not a new independent field case.'})
save(ROOT/'documents.json',docs)
print('Recorded visual checks for four real documents and one derived scan control.')
