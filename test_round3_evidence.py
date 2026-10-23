import hashlib,json,tempfile,unittest
from pathlib import Path
from bs4 import BeautifulSoup
from image_triage import named_image_title
from material_delivery import page_date
from quality_fields import administrative_only,profile_label_name,biography_identity_after_metadata,fields_from_text
from quality_pipeline import assessment_fingerprint
from roster_sections import directory_section,administrative_roster_proof

class RoundThreeEvidenceTests(unittest.TestCase):
    def test_cms_header_does_not_hide_the_opening_named_biography(self):
        text='个人简历\n标签：\n时间：2022-03-23　点击：439　来源：某学院\n雷磊，女，1962年出生。教授。'
        self.assertIsNotNone(biography_identity_after_metadata('雷磊',text))
        self.assertIsNone(biography_identity_after_metadata('张三',text))
        self.assertIsNone(biography_identity_after_metadata('雷磊',text.replace('个人简历','学术新闻')))
        self.assertIsNone(biography_identity_after_metadata('雷磊',text.replace('雷磊，女，','本院邀请雷磊，女，')))
        self.assertIsNone(biography_identity_after_metadata('雷磊',text.replace('标签：','报告人：')))

    def test_specific_rank_is_preserved_in_full(self):
        f=fields_from_text('吕芳','吕芳，女，博士，助理副教授，硕士生导师。主要从事地理教育研究。')
        self.assertEqual(f['title']['value'],'助理副教授')

    def test_dual_teaching_and_secretarial_role_is_not_admin_only(self):
        self.assertFalse(administrative_only('杜媛，现任旅游学院教师及教学秘书，主要从事旅游管理及酒店管理相关课程教学。',''))
        self.assertTrue(administrative_only('李四，现任学院教学秘书，负责教学管理及课程档案归档。',''))
        self.assertEqual(profile_label_name('杜鹏 副院长'),'杜鹏')

    def test_group_membership_must_be_proven_and_all_observations_admin(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'list').mkdir()
            html='<div><h2>行政教辅</h2><div><ul><li><a href="/person">张三</a></li></ul></div></div>'
            (root/'list/source.html').write_text(html,encoding='utf8')
            self.assertEqual(directory_section(BeautifulSoup(html,'lxml').li),'行政教辅')
            obs={'source_kind':'directory_link','source_url':'https://test.edu.cn/list','profile_url':'https://test.edu.cn/person','directory_section':'行政教辅'}
            p={'name':'张三','observations':[obs]};cat={'pages':[{'url':obs['source_url'],'directory':'list'}]}
            self.assertIsNotNone(administrative_roster_proof(cat,root,p,{}))
            p['observations'].append({**obs,'directory_section':'旅游管理系'})
            self.assertIsNone(administrative_roster_proof(cat,root,p,{}))
            p['observations']=[{**obs,'profile_url':'https://test.edu.cn/another'}]
            self.assertIsNone(administrative_roster_proof(cat,root,p,{}))
            p['observations']=[{k:v for k,v in obs.items() if k!='directory_section'}]
            self.assertIsNone(administrative_roster_proof(cat,root,p,{}))

    def test_header_publication_date_is_not_biographical_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'p').mkdir();path=root/'p/source.html'
            page={'directory':'p','retrieved_at':'2026-10-15T12:00:00Z'}
            path.write_text('<div class="title"><div class="tit_attr">发布日期：2025年01月04日 来源：学院</div></div><div class="v_news_content">2020年01月01日任职。</div>',encoding='utf8')
            self.assertEqual(page_date(root,page)['date'],'2025-01-04')
            for html in ('<div class="v_news_content"><div class="title"><div class="tit_attr">发布日期：2025年01月04日</div></div></div>',
                         '<div class="title"><div class="tit_attr">出生日期：1990年01月04日</div></div>',
                         '<div class="title"><div class="tit_attr">发布日期：2030年01月04日</div></div>'):
                path.write_text(html,encoding='utf8');self.assertIsNone(page_date(root,page))

    def test_named_image_rank_requires_source_identity_confidence_and_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'p').mkdir();(root/'m').mkdir()
            raw=b'original image fixture';(root/'m/source.png').write_bytes(raw)
            page={'url':'https://test.edu.cn/person','directory':'p','body_selector':'.body'}
            (root/'p/source.html').write_text('<div class="body"><img src="/card.png"></div>',encoding='utf8')
            m={'directory':'m','source_file':'source.png','source_url':'https://test.edu.cn/card.png','sha256':hashlib.sha256(raw).hexdigest(),
               'lines':[{'text':'张三','confidence':.999},{'text':'副教授','confidence':.999}]}
            self.assertEqual(named_image_title(root,page,[m],'张三')['value'],'副教授')
            self.assertIsNone(named_image_title(root,page,[m],'李四'))
            m['lines'][1]['confidence']=.8;self.assertIsNone(named_image_title(root,page,[m],'张三'))
            m['lines'][1]={'text':'硕士生导师','confidence':.999};self.assertIsNone(named_image_title(root,page,[m],'张三'))
            m['lines'][1]['text']='副教授';m['source_url']='https://test.edu.cn/other.png'
            self.assertIsNone(named_image_title(root,page,[m],'张三'))
            m['source_url']='https://test.edu.cn/card.png'
            (root/'media.json').write_text(json.dumps([m]),encoding='utf8')
            before=assessment_fingerprint(root)
            (root/'m/source.png').write_bytes(b'changed image')
            self.assertIsNone(named_image_title(root,page,[m],'张三'))
            self.assertNotEqual(assessment_fingerprint(root),before)

if __name__=='__main__':unittest.main()
