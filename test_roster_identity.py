import json
import tempfile
import unittest
from pathlib import Path

from quality_pipeline import build
from test_workbench import fixture


class RosterIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store, self.key = fixture(Path(self.temp.name))
        self.root = Path(self.store.job(self.key)['run_dir'])
        (self.root/'page/body-text.txt').write_text('张三，教授。研究方向为材料科学，长期从事相关领域的教学与研究工作。', encoding='utf8')
        self.obs = json.loads((self.root/'observations.json').read_text())
        self.obs.append({'name': '张三', 'profile_url': '', 'source_url': 'https://test.edu.cn/overview',
                         'source_kind': 'rich_roster', 'evidence': '张三'})
        self.pages = json.loads((self.root/'pages.json').read_text())
        self.pages += [{'url': 'https://test.edu.cn/'+slug, 'directory': slug, 'title': '师资队伍', 'kind': 'roster'} for slug in ('list', 'overview')]
        for slug in ('list', 'overview'):
            (self.root/slug).mkdir()
        (self.root/'list/source.html').write_text('<div><a href="/zhang">张三</a></div>', encoding='utf8')
        self.roster_html('<p>教授：1人</p><p>张三</p>')
        self.rosters = [{'url': p['url'], 'branch': '师资队伍', 'source_qualification': 'faculty_roster'} for p in self.pages[1:]]

    def tearDown(self):
        self.temp.cleanup()

    def roster_html(self, body):
        (self.root/'overview/source.html').write_text('<div class="wp_articlecontent">'+body+'</div>', encoding='utf8')

    def assess(self):
        for name, data in [('observations', self.obs), ('pages', self.pages), ('roster-pages', self.rosters)]:
            (self.root/(name+'.json')).write_text(json.dumps(data), encoding='utf8')
        build(self.store, self.key, force=True)
        return self.store.catalog(self.key)['people']

    def test_saved_same_college_roster_associates_and_retains_proof(self):
        (self.root/'list/source.html').write_text('<a href="/zhang">\u200b张三</a>', encoding='utf8')
        people = self.assess(); overview = next(p for p in people if not p['profile_url'])
        primary = next(p for p in people if p['profile_url'])
        self.assertEqual(overview['review']['status'], 'duplicate')
        self.assertEqual(overview['review']['canonical_id'], primary['id'])
        self.assertIn('sha256', overview['review']['identity_link']['roster'])
        self.assertEqual(primary['review']['status'], 'auto_accepted')
        self.assertEqual(primary['review']['roster_associations'][0]['person_id'], overview['id'])
        self.assertEqual(json.loads((self.root/'observations.json').read_text()), self.obs)
        from workbench_export import accepted_records
        self.assertIn('https://test.edu.cn/overview', accepted_records(self.store.catalog(self.key))[0]['sources'])

    def test_coauthor_in_role_labelled_biography_is_not_a_roster_member(self):
        from roster_identity import RosterEvidence
        self.pages[-1]['title']='行业导师-李四-某大学书法学院'
        self.roster_html('<p>李四，教授。曾与张三合著著作。</p>')
        self.assess();cat=self.store.catalog(self.key,apply_auto=False)
        p=next(p for p in cat['people'] if not p['profile_url'])
        self.assertIsNone(RosterEvidence(cat,self.root).evidence(p))

    def test_legacy_roster_requires_saved_document_title(self):
        for r in self.rosters:
            r.pop('source_qualification')
        self.assertEqual(next(p for p in self.assess() if not p['profile_url'])['review']['status'], 'pending')
        for slug in ('list', 'overview'):
            path = self.root/slug/'source.html'
            path.write_text('<title>师资队伍</title>'+path.read_text(encoding='utf8'), encoding='utf8')
        self.assertEqual(next(p for p in self.assess() if not p['profile_url'])['review']['status'], 'duplicate')

    def test_faculty_card_teaching_students_is_not_student_roster(self):
        self.roster_html('<table><tr><td><img src="portrait.jpg"><div>\u200b张三</div><div>教授，多次获得学生最喜爱的教师奖。</div></td></tr></table>')
        self.assertEqual(next(p for p in self.assess() if not p['profile_url'])['review']['status'],'duplicate')
        self.roster_html('<table><tr><td><img src="portrait.jpg"><div>张三</div><div>学生姓名：张三</div></td></tr></table>')
        self.assertEqual(next(p for p in self.assess() if not p['profile_url'])['review']['status'],'pending')

    def test_unknown_roster_or_wrong_host_does_not_match(self):
        self.rosters[1]['source_qualification'] = 'unknown'
        self.assertEqual(next(p for p in self.assess() if not p['profile_url'])['review']['status'], 'pending')

        self.rosters[1]['source_qualification'] = 'faculty_roster'
        for rows in (self.obs, self.pages, self.rosters):
            for row in rows:
                for field in ('source_url', 'url'):
                    if field in row:
                        row[field] = row[field].replace('test.edu.cn', 'else.edu.cn')
        self.assertEqual(next(p for p in self.assess() if not p['profile_url'])['review']['status'], 'pending')

    def test_changed_original_invalidates_association_without_metadata_changes(self):
        self.assess()
        self.roster_html('<p>李四</p>')
        build(self.store, self.key)
        self.assertEqual(next(p for p in self.store.catalog(self.key)['people'] if not p['profile_url'])['review']['status'], 'pending')

    def test_missing_anchor_different_person_substring_and_admin_keep_pending(self):
        for html in ['<p>李四</p>', '<p>张三丰</p>', '<p>行政：1人</p><p>张三</p>', '<p>联系人：张三</p>']:
            with self.subTest(html=html):
                self.roster_html(html)
                self.assertEqual(next(p for p in self.assess() if not p['profile_url'])['review']['status'], 'pending')
        self.roster_html('<p>张三</p>')
        (self.root/'list/source.html').write_text('<a href="/li">张三</a>', encoding='utf8')
        self.assertEqual(next(p for p in self.assess() if not p['profile_url'])['review']['status'], 'pending')

    def test_multiple_profiles_historical_and_manual_decisions_keep_pending(self):
        self.obs.append({**self.obs[0], 'profile_url': 'https://test.edu.cn/zhang2'})
        self.assertEqual(next(p for p in self.assess() if not p['profile_url'])['review']['status'], 'pending')
        self.obs.pop(); self.obs[-1]['historical_roster'] = True
        self.assertEqual(next(p for p in self.assess() if not p['profile_url'])['review']['status'], 'pending')
        self.obs[-1].pop('historical_roster')
        p = next(p for p in self.assess() if not p['profile_url'])
        self.store.decide(self.key, p['id'], {'revision': 0, 'status': 'needs_followup', 'actor': '测试员', 'reason': '有不同任职线索', 'evidence': '官方页面'})
        self.assertEqual(next(p for p in self.assess() if not p['profile_url'])['review']['status'], 'needs_followup')

    def test_primary_field_problem_stays_in_review_without_duplicate_roster_request(self):
        (self.root/'page/body-text.txt').write_text('张三，教授。研究方向为材料科学，长期从事相关领域的教学与研究工作。邮箱 zhang@163.', encoding='utf8')
        people = self.assess()
        self.assertEqual(next(p for p in people if p['profile_url'])['review']['status'], 'pending')
        self.assertEqual(next(p for p in people if not p['profile_url'])['review']['status'], 'duplicate')


if __name__ == '__main__':
    unittest.main()
