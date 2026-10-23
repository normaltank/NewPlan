import json
import shutil
from pathlib import Path
from prepare import ROOT, read, save, sha

docs=read(ROOT/'documents.json')
candidates=read(ROOT/'attachment-candidates.json')
for sid, needle, name, title, kind in [
    ('d02','b60f48a6ed424e70b1478494d5edb138','张红岩','副教授','image_biography'),
    ('d03','c48f0652d947498bb2634c44eda2c21b','鲍相志','讲师','image_biography'),
    ('d04','b0ec4173-8507-49af-94e2-452d0a29e305','','','negative_photo_with_text'),
]:
    row=next(x for x in candidates if needle in x['source_url'])
    native=read(row['path'])
    old=Path(row['path']).parent/native['source_file']
    folder=ROOT/'sources'/sid
    folder.mkdir(parents=True,exist_ok=True)
    source=folder/old.name
    shutil.copy2(old,source)
    shutil.copy2(row['path'],folder/'native.json')
    docs.append({'id':sid,'kind':kind,'source':str(source),'previous_source':str(old),'url':row['source_url'],
        'sha256':sha(source),'expected':{'name':name,'title':title},'visual_verification':'pending'})
save(ROOT/'documents.json',docs)
print(json.dumps(docs,ensure_ascii=False,indent=2))
