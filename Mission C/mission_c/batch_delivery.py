"""University evidence packages; paths inside the archive are relative."""
import copy
import csv
import json
from pathlib import Path
import shutil
import uuid
import zipfile
from .export import export_tables, csv_value


def category(record):
    code = record.get('error',{}).get('code','')
    if code.startswith('http_') or code in {'network_error','redirect_limit'}: return 2
    return 0 if record.get('email') else 1


def export_universities(service, batch_id, school=None):
    status = service.status(batch_id)
    schools = sorted({t['school'] for t in status['tasks']})
    if school is not None:
        if school not in schools: raise ValueError('未知学校')
        schools = [school]
    exports = []
    for name in schools:
        token = uuid.uuid4().hex
        relative = Path('exports')/batch_id/token
        folder = service.root/relative
        folder.mkdir(parents=True)
        records, relations, all_records = [], [], []
        for task in status['tasks']:
            if task['school'] != name: continue
            if task['state'] in {'pending','running','artifact_missing'} or not task['artifact']: continue
            try: service.bound(task['artifact'])
            except (ValueError,OSError,KeyError): continue
            origin = service.root/task['artifact']
            record = json.loads((origin/'teachers.json').read_text(encoding='utf-8'))[0]
            prefix = Path('evidence')/task['id']
            shutil.copytree(origin,folder/prefix)
            # Only aggregate records are rebased; original record.json retains
            # its own per-attempt relative context inside the copied directory.
            def rebase(node):
                if isinstance(node,dict):
                    for key,value in list(node.items()):
                        if key.endswith('_file') and isinstance(value,str) and value:
                            source = (origin/value).resolve()
                            if source.is_relative_to(origin.resolve()) and source.is_file(): node[key] = (prefix/value).as_posix()
                        else: rebase(value)
                elif isinstance(node,list):
                    for value in node: rebase(value)
            rebase(record)
            record['batch_task_id'] = task['id']
            record['batch_state'] = task['state']
            record['relations'] = copy.deepcopy(task['relations'])
            record['input_sources'] = copy.deepcopy(task['sources'])
            record['input_metadata']['college'] = '; '.join(dict.fromkeys(r['college'] for r in task['relations']))
            record['quality'] = task['quality']
            all_records.append(record)
            if task['quality']['eligible_for_workbook']: records.append(record)
            for relation in task['relations']:
                relations.append([task['id'],task['url'],name,relation['college'],relation['id'],json.dumps(relation['faculty_urls'],ensure_ascii=False),json.dumps(task['sources'],ensure_ascii=False)])
        records.sort(key=category)
        export_tables(folder,records)
        (folder/'records.json').write_text(json.dumps(all_records,ensure_ascii=False,indent=2),encoding='utf-8')
        with (folder/'exceptions.csv').open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['任务ID','个人URL','状态','质量分类','原因','原件目录'])
            for task in status['tasks']:
                if task['school']==name and (not task['quality']['eligible_for_workbook'] or task['state'] in {'failed','program_error','artifact_missing'}):
                    writer.writerow([csv_value(v) for v in [task['id'],task['url'],task['state'],task['quality']['category'],'; '.join(task['quality']['reasons']),('evidence/'+task['id']) if task['id'] in copied else '']])
        (folder/'teachers.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
        scoped = copy.deepcopy(status)
        scoped['tasks'] = [t for t in scoped['tasks'] if t['school']==name]
        copied = {r['batch_task_id'] for r in all_records}
        for task in scoped['tasks']:
            task['artifact'] = ('evidence/'+task['id']) if task['id'] in copied else None
        (folder/'batch.json').write_text(json.dumps(scoped,ensure_ascii=False,indent=2),encoding='utf-8')
        with (folder/'relations.csv').open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['任务ID','个人URL','学校','学院','学院ID','师资来源','输入行来源'])
            writer.writerows([[csv_value(v) for v in row] for row in relations])
        for item in status['inputs']:
            target=folder/item['stored_file'];target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(service.root/item['stored_file'],target)
        (folder/'README.txt').write_text('学院完整性未验证。教师表包含独立任务C的待复核个人页结果；身份及批次状态请核对 teachers.json / batch.json。输入学校学院为关联元数据，未冒充官网核实。实际HTTP失败与缓存未读取分开保留。原件在evidence中，超长全文见TXT/CSV/JSON。',encoding='utf-8')
        archive = folder.with_suffix('.zip')
        with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as package:
            for path in folder.rglob('*'):
                if path.is_file(): package.write(path,path.relative_to(folder).as_posix())
        exports.append({'school':name,'path':archive.relative_to(service.root).as_posix(),'records':len(records)})
    return {'id':batch_id,'exports':exports,'completeness':'not_verified'}
