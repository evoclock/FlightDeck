"""The shipped examples/demo renders offline and contains only scrubbed, fake data."""
import json
import re
import tempfile
import unittest
from pathlib import Path

from flightdeck import render as R

DEMO = Path(__file__).resolve().parent.parent / 'examples' / 'demo'
FORBIDDEN = ('evoclock/', 'spark-backend', 'Neuromancer', 'neuromancer', 'crew-tracker', 'crewTracker',
             'Flockmate', 'flockmate', 'julen', 'Julen', '@gmail.com')


class DemoRenderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / 'index.html'
        self.doc = R.render(DEMO / 'config.json', DEMO / 'data.json', self.out)

    def tearDown(self):
        self.tmp.cleanup()

    def test_renders_fake_agents(self):
        self.assertTrue(self.doc.startswith('<!doctype html>'))
        self.assertEqual(self.out.read_text(), self.doc)
        for name in ('Harbor', 'Lumen', 'Quill', 'Nimbus'):
            self.assertIn(name, self.doc)
        self.assertIn('example/board', self.doc)
        self.assertIn('example/notes', self.doc)
        self.assertIn('example/charts', self.doc)
        self.assertIn('4 bots · 2 need you', self.doc)
        self.assertIn('3 open · 1 settled', self.doc)
        self.assertIn('6 PRs · 2 ready', self.doc)
        self.assertIn('Example week', self.doc)
        self.assertIn('data-window="week">28<', self.doc)
        self.assertIn('https://github.com/example/board/pull/18', self.doc)
        self.assertIn('Illustration of one crew layout', self.doc)
        self.assertNotIn('flockmate.dev', self.doc)
        self.assertNotIn('api.github.com', self.doc)

    def test_no_private_strings(self):
        for bad in FORBIDDEN:
            self.assertNotIn(bad, self.doc, bad)
        raw = (DEMO / 'config.json').read_text() + (DEMO / 'data.json').read_text()
        for bad in FORBIDDEN + ('flockmate.dev', 'api.github.com'):
            self.assertNotIn(bad, raw, bad)
        data = json.loads((DEMO / 'data.json').read_text())
        self.assertTrue(data['activity_weekly']['sample'])
        self.assertEqual(data['activity_weekly']['commits'], 28)

    def test_offline_assets_embedded(self):
        self.assertIn('data:image/webp;base64,UklG', self.doc)
        self.assertIn("font-family:'Geist Sans'", self.doc)
        srcs = [m for m in re.findall(r'<(\w+)\s[^>]*?\b(?:src|href)="https?://', self.doc) if m != 'a']
        self.assertEqual(srcs, [])
        self.assertNotIn('@import', self.doc)

    def test_banner_is_valid_webp(self):
        b = (DEMO / 'assets' / 'banner.webp').read_bytes()
        self.assertEqual((b[:4], b[8:12]), (b'RIFF', b'WEBP'))

    def test_demo_uses_generic_metrics_not_cluster(self):
        cfg = json.loads((DEMO / 'config.json').read_text())
        self.assertEqual(cfg['slots']['cluster'], 'metrics.generic')
        self.assertIn('<section class="spark metrics"', self.doc)


if __name__ == '__main__':
    unittest.main()
