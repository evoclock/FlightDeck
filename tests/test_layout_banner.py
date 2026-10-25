"""Banner is never shrunk or cropped to fit other panes: the layout CSS keeps its natural aspect."""
import re
import unittest

from flightdeck.layout_css import CSS


def banner_img_rules(css):
    return re.findall(r'\.banner img\{([^}]*)\}', css)


def banner_rules(css):
    return re.findall(r'(?:^|[}\s,])\.banner\{([^}]*)\}', css)


class BannerLayoutTests(unittest.TestCase):
    def test_banner_img_keeps_natural_aspect(self):
        rules = banner_img_rules(CSS)
        self.assertTrue(rules, 'no .banner img rule in layout CSS')
        self.assertIn('.banner img{display:block;width:100%;height:auto;object-fit:unset;', CSS)
        for r in rules:
            self.assertIn('height:auto', r)
            self.assertIn('object-fit:unset', r)

    def test_no_shrink_to_fit_or_crop_on_banner(self):
        for r in banner_img_rules(CSS) + banner_rules(CSS):
            self.assertNotIn('max-height', r)
            self.assertNotIn('object-fit:cover', r)
            self.assertNotIn('object-fit:contain', r)
            self.assertIsNone(re.search(r'(?<![-\w])height:(?!auto)', r), r)

    def test_banner_aspect_ratio_is_not_forced(self):
        for r in banner_img_rules(CSS) + banner_rules(CSS):
            self.assertNotIn('aspect-ratio', r)


if __name__ == '__main__':
    unittest.main()
