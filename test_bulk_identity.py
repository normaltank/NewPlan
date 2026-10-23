import json
import unittest
import test_workbench as fixture
accept=fixture.accept
from identity_export import consolidate

class BulkTests(unittest.TestCase):
    setUp=fixture.ReviewTests.setUp
    tearDown=fixture.ReviewTests.tearDown
    def prepare(self):
        p=self.store.add_person(self.key,{'name':'表格','actor':'测试','source_url':'https://test.edu.cn/table','reason':'隔离样本'})
        return [{'id':self.person,'revision':0},{'id':p['id'],'revision':0}]

    def test_bulk_exclusion_audits_every_item_and_is_atomic_on_conflict(self):
        items=self.prepare()
        self.store.decide(self.key,items[1]['id'],{**accept(),'status':'excluded'})
        data={'items':items,'actor':'测试','reason':'均为非教师表格','status':'excluded'}
        url=f'/api/jobs/{self.key}/bulk-decisions'
        self.assertEqual(self.client.post(url,json=data).status_code,409)
        self.assertEqual(self.store.catalog(self.key)['people'][0]['review']['revision'],0)
        items[1]['revision']=1
        before=len(self.store.history(self.key));r=self.client.post(url,json=data)
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(len(self.store.history(self.key)),before+2)
        self.assertEqual(len({i['bulk_id'] for i in r.json()['items']}),1)
        self.assertTrue(all(i['evidence'] for i in r.json()['items']))

    def test_bulk_cannot_accept_without_individual_field_checks(self):
        items=self.prepare();r=self.client.post(f'/api/jobs/{self.key}/bulk-decisions',json={'items':items,'actor':'测试','reason':'测试','status':'accepted'})
        self.assertEqual(r.status_code,422)
        self.assertTrue(all(p['review']['revision']==0 for p in self.store.catalog(self.key)['people']))

    def test_bulk_accept_keeps_each_preview_and_audits_every_person(self):
        added=self.store.add_person(self.key,{'name':'李四','actor':'测试','source_url':'https://test.edu.cn/list','reason':'名单无主页'})
        from quality_pipeline import build
        build(self.store,self.key,force=True)
        cat=self.store.catalog(self.key)
        data={'items':[{'id':p['id'],'revision':0,'fields':p['review']['fields']} for p in cat['people']],
              'actor':'测试','reason':'已对照正式名单和逐人字段','status':'accepted','checks':accept()['checks']}
        r=self.client.post(f'/api/jobs/{self.key}/bulk-decisions',json=data)
        self.assertEqual(r.status_code,200,r.text)
        people=self.store.catalog(self.key)['people']
        self.assertEqual({p['review']['fields']['name'] for p in people},{'张三','李四'})
        self.assertTrue(all(p['review']['status']=='accepted' for p in people))
        self.assertEqual(len({p['review']['bulk_id'] for p in people}),1)
        self.assertEqual(len(self.client.get(f'/api/jobs/{self.key}/export').json()['accepted']),2)

    def test_bulk_accept_stale_fields_checks_and_duplicates_are_atomic(self):
        from quality_pipeline import build
        build(self.store,self.key,force=True)
        cat=self.store.catalog(self.key);p=cat['people'][0]
        data={'items':[{'id':p['id'],'revision':0,'fields':p['review']['fields']}],
              'actor':'测试','reason':'核对字段','status':'accepted','checks':{}}
        url=f'/api/jobs/{self.key}/bulk-decisions'
        self.assertEqual(self.client.post(url,json=data).status_code,422)
        data['checks']=accept()['checks'];data['items'][0]['fields']['title']='已过时的预览'
        self.assertEqual(self.client.post(url,json=data).status_code,409)
        self.assertEqual(self.store.catalog(self.key)['people'][0]['review']['revision'],0)
        self.store.decide(self.key,p['id'],{**accept(),'status':'excluded'})
        data['items'][0].update(revision=1,fields=self.store.catalog(self.key)['people'][0]['review']['fields'])
        self.assertEqual(self.client.post(url,json=data).status_code,422)

    def test_bulk_rejects_running_and_duplicate_ids(self):
        items=self.prepare();data={'items':[items[0]]*2,'actor':'测试','reason':'测试','status':'excluded'}
        self.assertEqual(self.client.post(f'/api/jobs/{self.key}/bulk-decisions',json=data).status_code,422)
        data['items']=items;self.store.update(self.key,state='running')
        self.assertEqual(self.client.post(f'/api/jobs/{self.key}/bulk-decisions',json=data).status_code,409)

    def test_bulk_issues_resolve_and_college_is_invalidated_once(self):
        from pathlib import Path
        root=Path(self.store.job(self.key)['run_dir'])
        (root/'issues.json').write_text(json.dumps([{'kind':'request_failed','url':'https://test.edu.cn/one'},
                                                  {'kind':'request_failed','url':'https://test.edu.cn/two'}]),encoding='utf8')
        items=[{'id':p['id'],'revision':0} for p in self.store.catalog(self.key)['issues']]
        data={'items':items,'actor':'测试','reason':'逐项核对已处理','status':'resolved'}
        self.assertEqual(self.client.post(f'/api/jobs/{self.key}/bulk-decisions',json=data).status_code,200)
        self.store.decide(self.key,self.person,accept())
        final={**accept(),'status':'verified','checks':{k:True for k in ('entry_checked','branches_checked','pagination_checked','rows_checked')}}
        self.store.decide(self.key,'__college__',final)
        data.update(status='needs_followup',items=[dict(i,revision=1) for i in items])
        before=len(self.store.history(self.key))
        self.assertEqual(self.client.post(f'/api/jobs/{self.key}/bulk-decisions',json=data).status_code,200)
        self.assertEqual(self.store.catalog(self.key)['college_review']['status'],'unverified')
        self.assertEqual(len(self.store.history(self.key)),before+3)

class IdentityTests(__import__('unittest').TestCase):
    def record(self,**kw):
        return dict({'name':'张三','university':'测试大学','college':'甲学院','email':'zhang@test.edu.cn','title':'教授',
                     'profile_url':'https://test.edu.cn/zhang','biography':'张三，教授。研究原文。','run_id':'a','person_id':'p','sources':['https://test.edu.cn/list']},**kw)
    def test_same_person_merges_affiliations_and_keeps_full_bodies_and_conflict(self):
        a=self.record();b=self.record(college='乙学院',title='讲师',profile_url='https://other.test.edu.cn/z',biography='张三旧简介全文',run_id='b')
        result=consolidate([a,b]);self.assertEqual(len(result),1);r=result[0]
        self.assertEqual(r['college'],'甲学院；乙学院');self.assertEqual(r['title'],'')
        self.assertIn(a['biography'],r['biography']);self.assertIn(b['biography'],r['biography'])
        self.assertEqual(len(r['field_conflicts']['title']),2)
        self.assertEqual(len(r['members']),2)
    def test_names_and_public_mailboxes_do_not_merge(self):
        a=self.record(email='');b=self.record(college='乙学院',email='',profile_url='https://test.edu.cn/zhang2',biography='另一个同名教师')
        self.assertEqual(len(consolidate([a,b])),2)
        a['email']=b['email']='office@test.edu.cn'
        c=self.record(name='李四',email='office@test.edu.cn',profile_url='https://test.edu.cn/li',biography='李四')
        self.assertEqual(len(consolidate([a,b,c])),3)
    def test_different_universities_and_blank_urls_do_not_merge(self):
        a=self.record();b=self.record(university='其他大学')
        self.assertEqual(len(consolidate([a,b])),2)
        self.assertEqual(len(consolidate([self.record(email='',profile_url=''),self.record(email='',profile_url='',college='乙学院')])),2)
    def test_title_order_and_mail_case_are_not_conflicts(self):
        a=self.record(title='教授、主任医师',email='Zhang@test.edu.cn')
        b=self.record(title='主任医师、教授',college='乙学院')
        self.assertEqual(consolidate([a,b])[0]['field_conflicts'],{})

if __name__=='__main__':__import__('unittest').main()
