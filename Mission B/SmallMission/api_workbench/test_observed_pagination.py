"""Captured CMS page forms exercised through the public college audit."""
import unittest
import test_component_pagination as component

PAGES, TARGETS, page_html = component.PAGES, component.TARGETS, component.page_html


CASES = [
    ('https://example.edu.cn/teachers/', 'https://example.edu.cn/teachers/lists_74_2.html'),
    ('https://example.edu.cn/teachers/C47010201index_1.htm', 'https://example.edu.cn/teachers/C47010201index_2.htm'),
    ('https://example.edu.cn/tplb.jsp?urltype=tree.TreeTempUrl&wbtreeid=1112',
     'https://example.edu.cn/tplb.jsp?totalpage=2&PAGENUM=2&urltype=tree.TreeTempUrl&wbtreeid=1112'),
]


def fixtures(first, last):
    return {url: '<div class="roster"><a href="/person/' + str(i) + '">教师</a></div>'
            + '<div class="pb_sys_common">' + str(i) + '/2<a href="' + (last if i == 1 else first)
            + '">' + ('下一页' if i == 1 else '首页') + '</a></div>'
            for i, url in enumerate((first, last), 1)}


class ObservedPaginationTests(unittest.TestCase):
    def audit(self, pages, first, inputs=TARGETS[:2]):
        return component.ComponentPaginationTests().audit(pages, inputs, first)

    def test_observed_addresses_read_all_pages_and_compare_urls(self):
        for first, last in CASES:
            with self.subTest(source=first):
                result, requested = self.audit(fixtures(first, last), first)
                self.assertEqual(requested, [first, last])
                self.assertTrue(result['complete'], result['reason'])
                self.assertEqual(set(result['corrected_urls']), set(TARGETS[:2]))

    def test_directory_full_number_range_with_unique_current_marker(self):
        first, last = CASES[0]
        pages = fixtures(first, last)
        pages[first] = pages[first].replace('1/2', '<ul><li class="active"><a>1</a></li><li><a href="' + last + '">2</a></li></ul>')
        result, requested = self.audit(pages, first)
        self.assertEqual(requested, [first, last])
        self.assertTrue(result['complete'], result['reason'])

    def test_page_failures_missing_pages_and_totals_remain_special(self):
        for first, last in CASES:
            for failure in ('failed', 'missing', 'contradictory', 'address'):
                with self.subTest(source=first, failure=failure):
                    pages = fixtures(first, last)
                    if failure == 'failed':
                        pages[last] = 503
                    elif failure == 'missing':
                        pages = {u: h.replace('/2', '/3') for u, h in pages.items()}
                    elif failure == 'contradictory':
                        pages[last] = pages[last].replace('2/2', '2/3')
                    else:
                        pages[last] = pages[last].replace('2/2', '1/2')
                    result, _ = self.audit(pages, first)
                    self.assertTrue(result['needs_human'], result['reason'])

    def test_column_fixed_query_fragment_and_extension_boundaries_stay_closed(self):
        for first, last in CASES:
            bad = [last.replace('example.edu.cn', 'other.edu.cn'), last + '#other', last + '&category=other',
                   last.replace('/teachers/', '/other/'), last.replace('lists_74', 'lists_75'),
                   last.replace('C47010201', 'C47010202'), last.replace('.htm', '.shtm'),
                   last.replace('wbtreeid=1112', 'wbtreeid=1113'), last.replace('totalpage=2', 'totalpage=3')]
            for target in set(bad) - {last}:
                with self.subTest(target=target):
                    pages = fixtures(first, last)
                    pages[first] = pages[first].replace(last, target)
                    if 'lists_75' in target:
                        pages[first] = pages[first].replace('</div>', '<a href="' + last + '">2</a></div>')
                    result, requested = self.audit(pages, first)
                    self.assertNotIn(target, requested)
                    self.assertTrue(result['needs_human'], result['reason'])

    def test_same_count_different_urls_still_reports_missing_and_extra(self):
        for first, last in CASES:
            result, _ = self.audit(fixtures(first, last), first, [TARGETS[0], TARGETS[2]])
            self.assertFalse(result['needs_human'], result['reason'])
            self.assertEqual((result['stats']['missing'], result['stats']['extra']), (1, 1))

    def test_parallel_pager_totals_and_duplicate_current_markers_stay_special(self):
        first, last = CASES[0]
        for evidence in ('<span>1/1</span>', '<span class="active">1</span><span class="active">2</span>'):
            with self.subTest(evidence=evidence):
                pages = fixtures(first, last)
                pages[first] = pages[first].replace('1/2', '1/2' + evidence)
                result, _ = self.audit(pages, first)
                self.assertTrue(result['needs_human'], result['reason'])

    def test_component_this_page_marker_and_table_counter_variant(self):
        for variant in ('marker', 'table'):
            pages = dict(zip(PAGES, map(page_html, (1, 2, 3, 4))))
            if variant == 'marker':
                pages = {u: h.replace('p_no_d', 'this-page') for u, h in pages.items()}
            else:
                pages = {u: h.replace('<span class="p_pages">', '<table><tr><td>' + str(i) + '/4')
                         .replace('<span class="p_no_d">' + str(i) + '</span>', '')
                         .replace('</span></div>', '</td></tr></table></div>') for i, (u, h) in enumerate(pages.items(), 1)}
            result, requested = self.audit(pages, PAGES[0], TARGETS)
            self.assertEqual(requested, PAGES)
            self.assertTrue(result['complete'], result['reason'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
