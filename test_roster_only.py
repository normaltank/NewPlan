import json
import unittest
import test_roster_identity as fixture

class RosterOnlyTests(unittest.TestCase):
    setUp=fixture.RosterIdentityTests.setUp
    tearDown=fixture.RosterIdentityTests.tearDown
    roster_html=fixture.RosterIdentityTests.roster_html
    assess=fixture.RosterIdentityTests.assess

    def only(self,html='<p>张三：教授</p>'):
        self.obs=[o for o in self.obs if not o.get('profile_url')]
        self.roster_html(html)
        return self.assess()[0]

    def test_confirmed_roster_without_page_delivers_known_fields(self):
        p=self.only()
        self.assertEqual(p['review']['status'],'auto_accepted')
        self.assertEqual(p['review']['material_status'],'roster_only')
        self.assertEqual(p['review']['fields']['title'],'教授')
        self.assertEqual(p['review']['fields']['biography'],'')
        self.assertEqual(p['review']['fields']['profile_url'],'')
        self.assertEqual(p['review']['fields']['missing']['profile_url'],'not_stated_in_source')
        self.assertIn('sha256',p['review']['roster_only_evidence'])
        self.assertEqual(json.loads((self.root/'observations.json').read_text()),self.obs)

    def test_name_spacing_is_layout_not_missing_person(self):
        p=self.only('<p>张 三</p>')
        self.assertEqual(p['review']['status'],'auto_accepted')
        self.assertEqual(p['review']['fields']['title'],'')

    def test_hidden_profile_link_is_not_declared_absent(self):
        p=self.only('<p><a href="/zhang">张三</a></p>')
        self.assertEqual(p['review']['status'],'pending')

    def test_table_rowspan_rank_is_bound_to_person_cell(self):
        p=self.only('<table><tr><td rowspan="2">副教授</td><td>李四</td></tr><tr><td>张 三</td></tr><tr><td>讲师</td><td>王五</td></tr></table>')
        self.assertEqual(p['review']['fields']['title'],'副教授')

    def test_historical_admin_unknown_and_human_followup_are_preserved(self):
        for html in ('<p>行政：1人</p><p>张三</p>','<p>学生：张三</p>'):
            self.assertEqual(self.only(html)['review']['status'],'pending')
        self.obs[-1]['historical_roster']=True
        self.assertEqual(self.only()['review']['status'],'pending')

    def test_identical_roster_copy_collapses_but_name_alone_does_not(self):
        self.obs=[{**self.obs[1],'source_url':'https://test.edu.cn/'+slug} for slug in ('overview','list')]
        for slug in ('list','overview'):
            (self.root/slug/'source.html').write_text('<div class="wp_articlecontent"><p>张三：教授</p></div>',encoding='utf8')
        p=self.assess()
        self.assertEqual(sorted(x['review']['status'] for x in p),['auto_accepted','duplicate'])
        (self.root/'list/source.html').write_text('<div class="wp_articlecontent"><p>张三：讲师</p></div>',encoding='utf8')
        # Different lists cannot be deduplicated merely because names match.
        p=self.assess();self.assertFalse(any(x['review']['status']=='duplicate' for x in p))

if __name__=='__main__':unittest.main()
