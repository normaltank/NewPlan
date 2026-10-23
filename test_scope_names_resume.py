import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from bs4 import BeautifulSoup
from api_pilot import Pilot,title_name
from test_api_pilot import FakeAPI
from benchmark import ROOT
from resume_acquisition import restore
from quality_fields import profile_label_name

class ScopeNamesTests(unittest.IsolatedAsyncioTestCase):
    def pilot(self,out,limit=2):
        p=Pilot(SimpleNamespace(url='https://wjx.seu.edu.cn/',university='东南大学',college='吴健雄学院',max_pages=limit),Path(out),FakeAPI({}))
        p.plans['学院导师']={'page_kind':'directory','source_qualification':'faculty_roster','row_selector':'li','label_selector':'a','href_selector':'a','body_selector':'','next_selector':'','next_text':'','pager_selector':'','branch_selector':''}
        return p

    def test_unicode_latin_and_rank_labels(self):
        for label,expected in [('沙菁㛃','沙菁㛃'),('𠮷田太郎','𠮷田太郎'),('Simone Baldi','Simone Baldi'),('José García','José García'),("Anne-Marie O’Neill","Anne-Marie O’Neill"),('吴国盛 教授','吴国盛')]:
            self.assertEqual(title_name(label),expected)
        for label in ['Faculty Members','Contact Us','Read More','No Data','创新设计与产业发展研究中心导师组介绍']:
            self.assertIsNone(title_name(label))
        self.assertEqual(title_name('个人简介 - 张三（教授）'),'张三')

    def test_resume_recovers_old_dropped_urls_and_keeps_empty_pages_out_of_queue(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'runs') as tmp:
            source=Path(tmp)/'source';dest=Path(tmp)/'dest';source.mkdir();dest.mkdir()
            p=self.pilot(dest);page='abcdef0123456789';(source/page).mkdir()
            roster=p.args.url+'list';known=p.args.url+'known'
            (source/page/'source.html').write_text('<li><a href="https://arch.seu.edu.cn/lyc/main.psp">李迎成</a></li><li><a href="/baldi">Simone Baldi</a></li>',encoding='utf8')
            saved={'input':vars(p.args),'targets':{known:{'kind':'profile','branch':'学院导师'},p.args.url+'baldi':{'kind':'document','branch':'学院导师'}},
                   'plans':p.plans,'pages':[{'url':roster,'directory':page,'kind':'roster'},{'url':known,'kind':'profile','body_status':'no_text'},{'url':p.args.url+'baldi','kind':'document'}],
                   'issues':[{'kind':'profile_without_text','url':known},{'kind':'page_limit','url':p.args.url+'baldi'}],
                   'roster-pages':[{'url':roster,'branch':'学院导师','entries':2,'source_qualification':'faculty_roster'}]}
            for key,value in saved.items():(source/(key+'.json')).write_text(json.dumps(value),encoding='utf8')
            queue=restore(p,source)
            self.assertEqual(set(queue),{'https://arch.seu.edu.cn/lyc/main.psp',p.args.url+'baldi'})
            self.assertEqual(len(p.pages),2)
            self.assertEqual(p.targets[p.args.url+'baldi']['kind'],'profile')
            self.assertEqual([o['name'] for o in p.observations],['李迎成','Simone Baldi'])
            self.assertTrue((dest/page/'source.html').exists())
            self.assertEqual(json.loads((source/'issues.json').read_text()),saved['issues'])
            self.assertEqual(p.issues,[{'kind':'profile_without_text','url':known}])

    def test_cross_subdomain_assets_stay_on_profile_origin(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=self.pilot(tmp);item={'loaded_url':'https://arch.seu.edu.cn/lyc/main.psp'}
            self.assertTrue(p.asset_allowed(item,'https://arch.seu.edu.cn/image.png'))
            self.assertFalse(p.asset_allowed(item,'https://unrelated.edu.cn/image.png'))
            self.assertFalse(p.asset_allowed(item,'https://arch.seu.edu.cn.evil.example/image.png'))

    async def test_profile_selectors_are_separate_across_hosts(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=self.pilot(tmp);p.profile_selector='.empty';p.profile_selectors=['.empty'];p.api.answer={'body_selector':'.bio'}
            (Path(tmp)/'page').mkdir()
            item={'url':'https://arch.seu.edu.cn/lyc/main.psp','loaded_url':'https://arch.seu.edu.cn/lyc/main.psp','directory':'page','title':'李迎成'}
            await p.profile(item,BeautifulSoup('<div class="empty"></div><div class="bio">李迎成，教授。现从事城市规划研究。</div>','lxml'))
            self.assertGreater(item['body_chars'],15)
            self.assertEqual(p.plans['__profiles__'][p.host]['body_selector'],'.empty')
            self.assertEqual(p.plans['__profiles__']['arch.seu.edu.cn']['body_selector'],'.bio')

    async def test_personal_information_card_outside_resume_is_saved_and_bound(self):
        from quality_fields import fields_from_text
        with tempfile.TemporaryDirectory() as tmp:
            p=self.pilot(tmp);p.profile_selector='.resume';(Path(tmp)/'page').mkdir()
            item={'url':p.args.url,'loaded_url':p.args.url,'directory':'page','title':'学院网站'}
            html='<div class="news_box"><div class="news_con"><div class="news_title"><i>姓名</i>:李迎成</div><div>职务职称:教授，博士生导师</div><div>电子邮箱:li@test.edu.cn</div></div></div><div class="resume">李迎成，博士。研究方向与完整履历记录。</div><footer>公共邮箱office@test.edu.cn</footer>'
            await p.profile(item,BeautifulSoup(html,'lxml'))
            text=(Path(tmp)/'page/body-text.txt').read_text(encoding='utf8')
            fields=fields_from_text('李迎成',text)
            self.assertEqual(fields['title']['value'],'教授')
            self.assertEqual(fields['email']['value'],'li@test.edu.cn')
            self.assertNotIn('office@test.edu.cn',text)
            soup=BeautifulSoup(html.replace('姓名</i>:李迎成','姓名</i>:王五'),'lxml')
            from quality_fields import profile_card
            self.assertEqual(profile_card(soup,soup.select_one('.resume'),{'李迎成'}),'')

    async def test_roster_keeps_every_target_and_only_links_qualified_university_profiles(self):
        with tempfile.TemporaryDirectory() as out:
            p=self.pilot(out)
            soup=BeautifulSoup('<ul><li><a href="https://arch.seu.edu.cn/lyc/main.psp">李迎成</a></li><li><a href="https://me.seu.edu.cn/sjj/list.htm">沙菁㛃</a></li><li><a href="/baldi">Simone Baldi</a></li><li><a href="https://seu.edu.cn.evil.example/other">张三</a></li></ul>','lxml')
            await p.roster({'url':p.args.url,'loaded_url':p.args.url,'branch':'学院导师'},soup)
            self.assertEqual([o['name'] for o in p.observations],['李迎成','沙菁㛃','Simone Baldi','张三'])
            self.assertIn('https://arch.seu.edu.cn/lyc/main.psp',p.targets)
            self.assertIn('https://me.seu.edu.cn/sjj/list.htm',p.targets)
            self.assertIn('https://wjx.seu.edu.cn/baldi',p.targets)
            self.assertNotIn('https://seu.edu.cn.evil.example/other',p.targets)
            p.register('https://arch.seu.edu.cn/all','roster','其他学院')
            p.register('https://arch.seu.edu.cn/unproven','profile','新闻')
            self.assertNotIn('https://arch.seu.edu.cn/all',p.targets)
            self.assertNotIn('https://arch.seu.edu.cn/unproven',p.targets)
            self.assertFalse(any(i['kind']=='page_limit' for i in p.issues))

if __name__=='__main__':unittest.main()
