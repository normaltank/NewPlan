"""Supplemental jump controls through the public college reconciliation seam."""
import unittest

import test_component_pagination as component


JUMP = ('<input id="u8_goto"/>'
        '<a href="javascript:;" onclick=\'_simple_list_gotopage_fun(4,"u8_goto",2)\'>跳转</a>')


def jump_pages(control=JUMP):
    return {url: component.page_html(n).replace('</span></div>', '</span>' + control + '</div>')
            for n, url in enumerate(component.PAGES, 1)}


STATIC_PAGES = ['https://example.edu.cn/staff/szdw.htm'] + [
    'https://example.edu.cn/staff/szdw/' + str(n) + '.htm' for n in (3, 2, 1)]


def static_pages(control=JUMP):
    pages = {}
    for n, url in enumerate(STATIC_PAGES):
        html = jump_pages(control)[component.PAGES[n]]
        for old, new in zip(component.PAGES, STATIC_PAGES):
            html = html.replace(old, new)
        pages[url] = html
    return pages


class StandardJumpTests(unittest.TestCase):
    def test_supplemental_jump_preserves_complete_http_urls(self):
        baseline, _ = component.ComponentPaginationTests().audit()
        actual, requested = component.ComponentPaginationTests().audit(pages=jump_pages())
        self.assertTrue(baseline['complete'], baseline['reason'])
        self.assertTrue(actual['complete'], actual['reason'])
        self.assertEqual(requested, component.PAGES)
        self.assertEqual(set(actual['corrected_urls']), set(component.TARGETS))

    def test_observed_static_pages_and_enter_binding_preserve_urls(self):
        enter = JUMP.replace('<input id="u8_goto"/>',
            '<input type="text" id="u8_goto" onkeydown=\'if(event.keyCode==13){_simple_list_gotopage_fun(4,"u8_goto",2)}\'/>')
        result, requested = component.ComponentPaginationTests().audit(pages=static_pages(enter), source_url=STATIC_PAGES[0])
        self.assertTrue(result['complete'], result['reason'])
        self.assertEqual(requested, STATIC_PAGES)
        self.assertEqual(set(result['corrected_urls']), set(component.TARGETS))

    def test_unknown_or_unbound_jump_remains_human(self):
        controls = [
            JUMP.replace('_simple_list_gotopage_fun', 'unknown_jump'),
            JUMP.replace('2)\'', '2);sideEffect()\''),
            JUMP.replace('onclick=', 'onmouseover="sideEffect()" onclick='),
            JUMP.replace('<input id="u8_goto"/>', ''),
            JUMP.replace('<input id="u8_goto"/>', '<input id="other"/>'),
            JUMP.replace('<input id="u8_goto"/>', '<input id="u8_goto"/><input id="u8_goto"/>'),
            JUMP.replace('<input id="u8_goto"/>', '<input id="u8_goto" onchange="sideEffect()"/>'),
            JUMP.replace('<input id="u8_goto"/>', '<input id="u8_goto" onkeydown="unknown()"/>'),
            JUMP.replace('(4,', '(3,'), JUMP.replace('(4,', '(5,'),
            JUMP.replace(',2)', ',3)'), JUMP.replace('跳转</a>', '下一页</a>'),
        ]
        for control in controls:
            with self.subTest(control=control):
                result, _ = component.ComponentPaginationTests().audit(pages=jump_pages(control))
                self.assertTrue(result['needs_human'], result['reason'])
                self.assertIn('分页目标不是可读取的HTTP地址', result['reason'])

    def test_unread_pages_and_unknown_next_or_last_are_not_excused(self):
        variants = []
        missing = '<span class="p_no"><a href="' + component.PAGES[2] + '">3</a></span>'
        variants.append({url: text.replace(missing, '') for url, text in jump_pages().items()})
        variants.append({**jump_pages(), component.PAGES[2]: 503})
        for label in ('Next', '尾页'):
            variants.append({url: text.replace('</div>', '<a href="javascript:unknown()">' + label + '</a></div>')
                             if url == component.SOURCE else text for url, text in jump_pages().items()})
        variants.append({url: text.replace('<div class="pb_sys_common">', '<div class="pb_sys_common" onclick="sideEffect()">')
                         for url, text in jump_pages().items()})
        for pages in variants:
            with self.subTest(first_page=pages[component.SOURCE]):
                result, _ = component.ComponentPaginationTests().audit(pages=pages)
                self.assertTrue(result['needs_human'], result['reason'])
                self.assertFalse(result['complete'])

    def test_same_count_different_url_still_reports_the_actual_difference(self):
        result, _ = component.ComponentPaginationTests().audit(
            pages=jump_pages(), inputs=component.TARGETS[:3] + ['https://example.edu.cn/person/other'])
        self.assertFalse(result['needs_human'], result['reason'])
        self.assertEqual((result['stats']['missing'], result['stats']['extra']), (1, 1))
        self.assertEqual(set(result['corrected_urls']), set(component.TARGETS))

    def test_explicit_single_page_is_terminal_without_a_synthetic_paging_url(self):
        control = JUMP.replace('(4,', '(1,')
        html = ('<div class="roster"><a href="/person/1">条目</a></div>'
                '<div class="pb_sys_common"><span class="p_pages">'
                '<span class="p_no_d">1</span></span><span>1/1</span>' + control + '</div>')
        result, requested = component.ComponentPaginationTests().audit(
            pages={component.SOURCE: html}, inputs=component.TARGETS[:1])
        self.assertTrue(result['complete'], result['reason'])
        self.assertEqual(requested, [component.SOURCE])
        self.assertEqual(result['corrected_urls'], component.TARGETS[:1])

    def test_single_page_jump_does_not_excuse_unknown_next_or_missing_dom_total(self):
        control = JUMP.replace('(4,', '(1,')
        html = ('<div class="roster"><a href="/person/1">条目</a></div>'
                '<div class="pb_sys_common"><span class="p_pages">'
                '<span class="p_no_d">1</span></span><span>1/1</span>' + control + '</div>')
        for changed in (html.replace('</span><span>1/1', '</span><a href="#">Next</a><span>1/1'),
                        html.replace('1/1', ''), html.replace('1/1', '1/2')):
            with self.subTest(html=changed):
                result, _ = component.ComponentPaginationTests().audit(
                    pages={component.SOURCE: changed}, inputs=component.TARGETS[:1])
                self.assertTrue(result['needs_human'], result['reason'])

    def test_current_marker_outside_numbered_control_is_not_jump_evidence(self):
        pages = static_pages()
        pages[STATIC_PAGES[0]] = pages[STATIC_PAGES[0]].replace(
            '<span class="p_no_d">1</span>', '').replace(
            '<span class="p_pages">', '<span class="p_no_d">1</span><span class="p_pages">')
        result, _ = component.ComponentPaginationTests().audit(pages=pages, source_url=STATIC_PAGES[0])
        self.assertTrue(result['needs_human'], result['reason'])
        self.assertIn('分页目标不是可读取的HTTP地址', result['reason'])

    def test_observed_address_shapes_and_jump_keep_the_same_complete_urls(self):
        from test_observed_pagination import CASES
        for first, last in CASES:
            with self.subTest(source=first):
                pages = {}
                for number, url in enumerate((first, last), 1):
                    other = last if number == 1 else first
                    pages[url] = ('<div class="roster"><a href="/person/' + str(number)
                        + '">教师</a></div><div class="pb_sys_common">' + str(number)
                        + '/2<span class="p_pages"><span class="p_no_d">' + str(number)
                        + '</span><a href="' + other + '">' + str(3 - number)
                        + '</a></span>' + JUMP.replace('(4,', '(2,') + '</div>')
                result, requested = component.ComponentPaginationTests().audit(
                    pages=pages, inputs=component.TARGETS[:2], source_url=first)
                self.assertTrue(result['complete'], result['reason'])
                self.assertEqual(requested, [first, last])
                self.assertEqual(set(result['corrected_urls']), set(component.TARGETS[:2]))

    def test_component_this_page_marker_and_jump_keep_complete_http_pages(self):
        pages = {url: html.replace('p_no_d', 'this-page') for url, html in jump_pages().items()}
        result, requested = component.ComponentPaginationTests().audit(pages=pages)
        self.assertTrue(result['complete'], result['reason'])
        self.assertEqual(requested, component.PAGES)
        self.assertEqual(set(result['corrected_urls']), set(component.TARGETS))


if __name__ == '__main__':
    unittest.main(verbosity=2)
