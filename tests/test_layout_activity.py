"""Activity text stays inside the activity card: wrap, and scroll inside the card if needed."""
import re
import unittest

from flightdeck.layout_css import CSS


def rule(selector):
    found = re.findall(r'(?:^|[}\s])%s\{([^}]*)\}' % re.escape(selector), CSS)
    return found


class ActivityLayoutTests(unittest.TestCase):
    def test_activity_card_clips_or_scrolls_inside_its_border(self):
        rules = rule('.activity')
        self.assertTrue(rules)
        box = rules[0]
        self.assertIn('min-width:0', box)
        self.assertIn('max-width:100%', box)
        self.assertIn('overflow:auto', box)
        self.assertNotIn('overflow:visible', box)

    def test_activity_labels_and_notes_wrap(self):
        head = rule('.a-tab thead th')
        body = rule('.a-tab tbody th')
        self.assertTrue(head and body)
        for block in (head[0], body[0]):
            self.assertIn('white-space:normal', block)
            self.assertIn('overflow-wrap:anywhere', block)
            self.assertNotIn('nowrap', block)
        table = rule('.a-tab')
        self.assertIn('table-layout:fixed', table[0])
        self.assertIn('max-width:100%', table[0])
        foot = rule('.a-foot')
        self.assertIn('min-width:0', foot[0])
        self.assertIn('max-width:100%', foot[0])
        note = rule('.a-meta,.anote')
        self.assertIn('overflow-wrap:anywhere', note[0])
        self.assertIn('max-width:100%', note[0])
        children = rule('.activity>*')
        self.assertIn('min-width:0', children[0])
        self.assertIn('max-width:100%', children[0])


if __name__ == '__main__':
    unittest.main()
