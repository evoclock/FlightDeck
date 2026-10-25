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
        self.assertIn('Alpha', self.doc)
        self.assertIn('Beta', self.doc)
        self.assertIn('example/app', self.doc)

    def test_no_private_strings(self):
        for bad in FORBIDDEN:
            self.assertNotIn(bad, self.doc, bad)
        raw = (DEMO / 'config.json').read_text() + (DEMO / 'data.json').read_text()
        for bad in FORBIDDEN:
            self.assertNotIn(bad, raw, bad)

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
