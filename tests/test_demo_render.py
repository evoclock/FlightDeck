"""The shipped examples/demo renders offline as a static illustration of public evoclock repos."""
import datetime
import json
import re
import tempfile
import unittest
from pathlib import Path

from flightdeck import render as R

DEMO = Path(__file__).resolve().parent.parent / 'examples' / 'demo'
FORBIDDEN = (
    'spark-backend', 'crew-tracker', 'crewTracker',
    'Flockmate', 'flockmate', 'flock-master', 'flockmate.dev', 'julen', 'Julen', '@gmail.com',
    'Harbor', 'Lumen', 'Quill', 'Nimbus', 'example/board', 'example/app',
    'pstack', 'tater-tot', 'node-a',
)


class DemoRenderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / 'index.html'
        self.doc = R.render(DEMO / 'config.json', DEMO / 'data.json', self.out)

    def tearDown(self):
        self.tmp.cleanup()

    def test_renders_public_repos(self):
        self.assertTrue(self.doc.startswith('<!doctype html>'))
        self.assertEqual(self.out.read_text(), self.doc)
        for name in ('FlightDeck', 'OpenMausBot', 'pi-agentic-driver', 'pi-bowerbird', 'Demeter'):
            self.assertIn(name, self.doc)
        for repo in (
            'evoclock/FlightDeck', 'evoclock/OpenMausBot', 'evoclock/pi-agentic-driver',
            'evoclock/pi-bowerbird', 'evoclock/fieldnotes',
        ):
            self.assertIn(repo, self.doc)
        self.assertIn('5 bots · 2 need you', self.doc)
        self.assertIn('3 open · 1 settled', self.doc)
        self.assertIn('4 PRs · 0 ready', self.doc)
        self.assertIn('>This week<', self.doc)
        self.assertNotIn('Example week', self.doc)
        self.assertIn('data-window="1h">14<', self.doc)
        self.assertIn('data-window="week">286<', self.doc)
        self.assertIn('data-window="week">104<', self.doc)
        self.assertIn('data-window="week">93<', self.doc)
        self.assertIn('https://github.com/evoclock/pi-bowerbird/pull/2', self.doc)
        self.assertIn('https://github.com/evoclock/OpenMausBot/pull/48', self.doc)
        self.assertIn('Static illustration of public evoclock repos', self.doc)
        self.assertNotIn('api.github.com', self.doc)
        self.assertIn('<title>FlightDeck</title>', self.doc)
        self.assertIn('<h1>FlightDeck</h1>', self.doc)
        self.assertNotIn('FlightDeck demo', self.doc)
        self.assertIn('alt="ADHD Neuromancer"', self.doc)

    def test_no_private_strings(self):
        for bad in FORBIDDEN:
            self.assertNotIn(bad, self.doc, bad)
        raw = (DEMO / 'config.json').read_text() + (DEMO / 'data.json').read_text()
        for bad in FORBIDDEN + ('flockmate.dev', 'api.github.com'):
            self.assertNotIn(bad, raw, bad)
        data = json.loads((DEMO / 'data.json').read_text())
        self.assertFalse(data['activity_weekly'].get('sample'))
        self.assertEqual(data['activity']['commits'], 14)
        self.assertEqual(data['activity']['prs_opened'], 8)
        self.assertEqual(data['activity']['prs_merged'], 8)
        self.assertEqual(data['activity_weekly']['commits'], 286)
        self.assertEqual(data['activity_weekly']['prs_opened'], 104)
        self.assertEqual(data['activity_weekly']['prs_merged'], 93)
        self.assertNotIn('evoclock/demeter', raw)

    def test_every_outside_link_opens_in_a_new_tab(self):
        links = re.findall(r'<a [^>]*href="https?://[^>]*>', self.doc)
        self.assertTrue(links)
        for a in links:
            self.assertIn('target="_blank" rel="noopener noreferrer"', a)
        self.assertIn("a.target='_blank'", self.doc)

    def test_offline_assets_embedded(self):
        self.assertIn('data:image/webp;base64,UklG', self.doc)
        self.assertIn("font-family:'Geist Sans'", self.doc)
        srcs = [m for m in re.findall(r'<(\w+)\s[^>]*?\b(?:src|href)="https?://', self.doc) if m != 'a']
        self.assertEqual(srcs, [])
        self.assertNotIn('@import', self.doc)

    def test_banner_is_valid_webp(self):
        b = (DEMO / 'assets' / 'banner.webp').read_bytes()
        self.assertEqual((b[:4], b[8:12]), (b'RIFF', b'WEBP'))
        self.assertEqual(len(b), 406602)

    def test_demo_uses_filled_gpu_cluster(self):
        cfg = json.loads((DEMO / 'config.json').read_text())
        data = json.loads((DEMO / 'data.json').read_text())
        self.assertEqual(cfg['slots']['cluster'], 'cluster.gpu')
        self.assertEqual(data['title'], 'FlightDeck')
        self.assertTrue(data['spark']['sample'])
        self.assertEqual([n['name'] for n in data['spark']['nodes']], ['demo-a', 'demo-b'])
        hist = data['spark']['history']
        self.assertEqual(len(hist), 5)
        times = [datetime.datetime.fromisoformat(h['at']) for h in hist]
        self.assertEqual([(b - a).total_seconds() for a, b in zip(times, times[1:])], [15 * 60] * 4)
        self.assertRegex(self.doc, r'data-node="demo-a"[^>]* d="M[^"]* L')
        self.assertNotIn('metrics', data)
        self.assertIn('demo cluster', self.doc)
        self.assertIn('2 online', self.doc)
        self.assertIn('data-node="demo-a"', self.doc)
        self.assertIn('data-node="demo-b"', self.doc)
        self.assertIn('<path class="tl" data-node="demo-a"', self.doc)
        self.assertIn('class="tr-empty" hidden', self.doc)
        self.assertNotIn('<section class="spark metrics"', self.doc)
        self.assertNotIn('Example host', self.doc)
        self.assertIn('"sample": true', self.doc)

    def test_demo_cluster_runs_hot(self):
        spark = json.loads((DEMO / 'data.json').read_text())['spark']
        for n in spark['nodes']:
            self.assertGreaterEqual(n['gpu_util_pct'], 95, n['name'])
            self.assertLessEqual(n['gpu_util_pct'], 100, n['name'])
        for h in spark['history']:
            for node in ('demo-a', 'demo-b'):
                self.assertTrue(95 <= h['gpu'][node] <= 100, (h['at'], node))

    def test_demo_fills_every_live_pane(self):
        cfg = json.loads((DEMO / 'config.json').read_text())
        self.assertEqual(cfg['slots'], {
            'banner': 'banner.image', 'cluster': 'cluster.gpu', 'activity': 'activity.github',
            'streams': 'streams.table', 'decisions': 'decisions.cards', 'steps': 'steps.checklist',
            'merges': 'merges.table', 'priorities': 'priorities.list', 'settled': 'settled.list',
            'architecture': 'architecture.diagrams',
        })
        self.assertIn('id="architecture"', self.doc)
        self.assertIn('4 projects', self.doc)
        for tab in ('tab-flightdeck', 'tab-omb', 'tab-bowerbird', 'tab-demeter'):
            self.assertIn(f'id="{tab}"', self.doc)
        self.assertNotIn('No diagrams yet.', self.doc)
        stub = (DEMO / 'assets' / 'architecture' / 'demeter.bower.json').read_text()
        self.assertIn('evoclock/fieldnotes', stub)
        self.assertNotIn('evoclock/demeter', stub)

    def test_walkthrough_video_is_the_attached_file(self):
        video = DEMO / 'assets' / 'flightdeck-demo.mp4'
        self.assertTrue(video.is_file())
        self.assertGreater(video.stat().st_size, 500_000)
        self.assertLess(video.stat().st_size, 25_000_000)
        self.assertIn(b'ftyp', video.read_bytes()[:32])
        self.assertFalse((DEMO / 'assets' / 'flock-tracker-demo.mp4').exists())
        demo_doc = (DEMO / 'README.md').read_text()
        self.assertIn('assets/flightdeck-demo.mp4', demo_doc)
        self.assertNotIn('flock-tracker', demo_doc)
        self.assertIn('demo-still.png', demo_doc)
        root = (DEMO.parent.parent / 'README.md').read_text()
        self.assertIn('examples/demo/assets/flightdeck-demo.mp4', root)
        self.assertNotIn('flock-tracker', root)


if __name__ == '__main__':
    unittest.main()
