"""Pane body text stays inside the card: wrap, grow with content, no mid-line clip."""
import re
import unittest

from flightdeck.layout_css import CSS


def rule(selector):
    return re.findall(r'(?:^|[}\s])%s\{([^}]*)\}' % re.escape(selector), CSS)


class PaneLayoutTests(unittest.TestCase):
    def test_desktop_panes_grow_instead_of_fixed_clip_height(self):
        # Inside the 1100px media query block we set min-height + height:auto.
        self.assertIn('min-height:clamp(420px,70vh,760px)', CSS)
        self.assertIn('.pane{min-height:clamp(420px,70vh,760px);height:auto;max-height:none}', CSS.replace('\n', '').replace(' ', '') or CSS)
        self.assertIn('height:auto', CSS)
        self.assertNotIn('.pane{height:clamp(420px,70vh,760px)}', CSS)

    def test_list_and_title_text_wrap_inside_pane(self):
        txt = rule('.txt')
        self.assertTrue(txt)
        self.assertIn('min-width:0', txt[0])
        self.assertIn('max-width:100%', txt[0])
        self.assertIn('overflow-wrap:anywhere', txt[0])
        titles = rule('.t,.strong.t')
        self.assertTrue(titles)
        self.assertIn('overflow-wrap:anywhere', titles[0])
        items = rule('.list .item,.tickrow')
        self.assertTrue(items)
        self.assertIn('min-width:0', items[0])
        pb = rule('.pb')
        self.assertTrue(any('overflow-x:hidden' in b for b in pb))


if __name__ == '__main__':
    unittest.main()
