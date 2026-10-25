"""Compare initial roster parsing and saved-run replay without network or API calls."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup

from api_pilot import Pilot
from resume_acquisition import restore
from roster_sections import administrative_roster_proof


PLAN = {
    'page_kind': 'directory', 'source_qualification': 'faculty_roster',
    'row_selector': 'li', 'label_selector': 'a', 'href_selector': 'a[href]',
    'body_selector': '', 'next_selector': '', 'next_text': '',
    'pager_selector': '', 'branch_selector': '',
}


class NoModel:
    async def ask(self, *args, **kwargs):
        raise AssertionError('Saved-roster replay must not request model inference')


def fingerprints(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


class DirectoryResumeTests(unittest.IsolatedAsyncioTestCase):
    async def collect(self, html, plan=None):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        source = root / 'runs' / 'source'
        source.mkdir(parents=True)
        directory = '0123456789abcdef'
        (source / directory).mkdir()
        (source / directory / 'source.html').write_text(html, encoding='utf-8')
        args = SimpleNamespace(url='https://test.edu.cn/', university='测试大学',
                               college='测试学院', browser=False, ocr=False)
        pilot = Pilot(args, source, NoModel())
        pilot.plans['师资'] = copy.deepcopy(plan or PLAN)
        item = {'url': args.url + 'list', 'loaded_url': args.url + 'list',
                'directory': directory, 'kind': 'roster', 'branch': '师资', 'title': '师资队伍'}
        await pilot.roster(item, BeautifulSoup(html, 'lxml'))
        pilot.pages = [item]
        saved = {'input': vars(args), 'targets': pilot.targets, 'plans': pilot.plans,
                 'pages': pilot.pages, 'observations': pilot.observations,
                 'roster-pages': pilot.rosters, 'issues': pilot.issues}
        for name, value in saved.items():
            self.save(source, name, value)
        return root, pilot

    def save(self, source, name, value):
        (source / (name + '.json')).write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')

    def resume(self, root, initial):
        dest = root / 'runs' / 'continued'
        dest.mkdir()
        before = fingerprints(initial.out)
        continued = Pilot(initial.args, dest, NoModel())
        with patch('resume_acquisition.ROOT', root):
            restore(continued, initial.out)
        self.assertEqual(fingerprints(initial.out), before, 'Previous evidence must remain unchanged')
        return continued

    async def test_empty_formatting_anchor_keeps_name_and_link(self):
        root, initial = await self.collect('<ul><li><a></a><a href="/zhang">张三</a></li></ul>')
        self.assertEqual([o['name'] for o in initial.observations], ['张三'])
        continued = self.resume(root, initial)
        self.assertEqual(continued.observations, initial.observations)
        self.assertIn('https://test.edu.cn/zhang', continued.pending_urls())

    async def test_explicit_administrative_section_remains_verifiable(self):
        root, initial = await self.collect(
            '<div><h2>行政教辅</h2><ul><li><a href="/li">李四</a></li></ul></div>')
        continued = self.resume(root, initial)
        self.assertEqual(continued.observations, initial.observations)
        for pilot in (initial, continued):
            proof = administrative_roster_proof({'pages': pilot.pages}, pilot.out,
                {'name': '李四', 'observations': pilot.observations}, {})
            self.assertIsNotNone(proof)
            self.assertEqual(proof['sources'][0]['section'], '行政教辅')

    async def test_legacy_nested_cards_recover_the_same_nine_people(self):
        html = (Path(__file__).parent / 'fixtures/nested_rank_cards.html').read_text(encoding='utf-8')
        plan = {**PLAN, 'row_selector': 'ul.contentbox > li.con',
                'label_selector': 'div.txt > h3', 'href_selector': 'a'}
        root, initial = await self.collect(html, plan)
        self.assertEqual(len(initial.observations), 9)
        # Simulate a saved run made before malformed sibling-card recovery existed.
        self.save(initial.out, 'observations', initial.observations[:3])
        self.save(initial.out, 'targets', {initial.args.url: {'kind': 'home', 'branch': ''}})
        legacy = copy.deepcopy(initial.rosters)
        legacy[0].update(entries=3, row_recovery=None)
        self.save(initial.out, 'roster-pages', legacy)
        continued = self.resume(root, initial)
        self.assertEqual(continued.observations, initial.observations)
        self.assertEqual(continued.rosters[0]['entries'], 9)
        self.assertEqual(continued.rosters[0]['row_recovery']['recovered_rows'], 9)

    async def test_ordinary_names_list_only_and_scope_guards_still_match(self):
        root, initial = await self.collect('''<ul>
            <li><a href="/han">沙菁㛃</a></li>
            <li><a href="https://dept.test.edu.cn/baldi">Simone Baldi</a></li>
            <li><a>王五</a></li>
            <li><a href="https://test.edu.cn.evil.example/a">张三</a></li>
            <li><a href="/download">学院简介</a></li>
            </ul>''')
        continued = self.resume(root, initial)
        self.assertEqual(continued.observations, initial.observations)
        self.assertEqual([o['name'] for o in continued.observations], ['沙菁㛃', 'Simone Baldi', '王五', '张三'])
        self.assertEqual(continued.targets, initial.targets)
        self.assertEqual(continued.targets['https://test.edu.cn/download']['kind'], 'document')
        self.assertNotIn('https://test.edu.cn.evil.example/a', continued.targets)

    async def test_incomplete_reinterpretation_preserves_saved_people(self):
        root, initial = await self.collect(
            '<ul><li><a href="/zhang">张三</a></li><li><a href="/li">李四</a></li></ul>')
        # The same row count is not proof that every former person can be parsed.
        path = initial.out / initial.pages[0]['directory'] / 'source.html'
        path.write_text('<ul><li><a href="/zhang">张三</a></li><li><span>李四</span></li></ul>', encoding='utf-8')
        continued = self.resume(root, initial)
        self.assertEqual(continued.observations, initial.observations)
        audit = json.loads((continued.out / 'resume.json').read_text(encoding='utf-8'))
        self.assertEqual(audit['replayed_rosters'], [])
        self.assertEqual(audit['skipped_rosters'][0]['reason'], 'observation_mismatch')

    async def test_unqualified_source_cannot_enqueue_additional_profiles(self):
        root, initial = await self.collect('<ul><li><a href="/zhang">张三</a></li></ul>')
        legacy = copy.deepcopy(initial.rosters)
        legacy[0]['source_qualification'] = 'uncertain'
        self.save(initial.out, 'roster-pages', legacy)
        targets = {initial.args.url: {'kind': 'home', 'branch': ''}}
        self.save(initial.out, 'targets', targets)
        continued = self.resume(root, initial)
        self.assertEqual(continued.observations, initial.observations)
        self.assertEqual(continued.targets, targets)
        audit = json.loads((continued.out / 'resume.json').read_text(encoding='utf-8'))
        self.assertEqual(audit['replayed_rosters'], [])

    async def test_mixed_directory_keeps_acquisition_order(self):
        _, initial = await self.collect('''<ul>
            <li><a href="/intro">学院简介</a></li>
            <li><a href="/zhang">张三</a></li>
            <li><a href="/research">研究方向</a></li>
            <li><a href="/li">李四</a></li>
            </ul>''')
        # Queue order affects which pages a bounded collection reaches first.
        self.assertEqual(list(initial.targets), [
            'https://test.edu.cn/', 'https://test.edu.cn/intro',
            'https://test.edu.cn/zhang', 'https://test.edu.cn/research', 'https://test.edu.cn/li'])


if __name__ == '__main__':
    unittest.main()
