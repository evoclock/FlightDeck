"""Render orchestration and ported widgets, on fake data only (no real agents, repos or hosts)."""
import datetime
import json
import re
import tempfile
import unittest
from pathlib import Path

from flightdeck import render as R
from flightdeck.common import week_start
from flightdeck.config import SLOT_IDS
from flightdeck.widgets import RenderContext, render_slot
from flightdeck.widgets import activity, cluster

try:
    from zoneinfo import ZoneInfo
    LONDON = ZoneInfo('Europe/London')
except Exception:  # pragma: no cover
    LONDON = None

NOW = datetime.datetime(2026, 10, 25, 1, 0, tzinfo=datetime.timezone.utc)
FULL = {
    'banner': 'banner.image', 'cluster': 'cluster.gpu', 'activity': 'activity.github',
    'streams': 'streams.table', 'decisions': 'decisions.cards', 'steps': 'steps.checklist',
    'merges': 'merges.table', 'priorities': 'priorities.list', 'settled': 'settled.list',
    'architecture': 'architecture.diagrams',
}


def fake_data():
    at = (NOW - datetime.timedelta(minutes=2)).isoformat()
    return {
        'title': 'Demo deck', 'summary': 'Two fake streams.',
        'bot_colors': {'Alpha': '#3f6f70', 'Beta': '#76536b'}, 'repo_colors': {'example/app': '#617082'},
        'streams': [['Alpha', 'example/app', 'Writing tests', 'Nothing'],
                    {'bot': 'Beta', 'project': 'example/lib', 'now': 'Reviewing', 'waiting': 'Approve the plan'}],
        'decisions': [{'id': 'dec-1', 'state': 'open', 'title': 'Ship it?', 'text': '- one\n- two',
                       'recommendation': 'Yes, see [PR](https://github.com/example/app/pull/1)'},
                      {'state': 'settled', 'title': 'Old', 'text': 'Done already'}],
        'steps': [{'text': 'Rotate the key', 'meta': 'blocks Alpha'}, {'text': 'Read notes', 'done': True}],
        'merges': [['Add widget', 'example/app', 'Alpha', 'Ready to merge'],
                   ['Fix bug', 'example/app', 'Beta', 'In progress']],
        'merge_note': 'Merge in order.',
        'priorities': [{'stream': 'Alpha', 'area': 'Tests', 'items': [
            {'text': 'Write', 'state': 'current'}, {'text': 'Wire', 'state': 'blocked'}, {'text': 'Old', 'state': 'done'}]}],
        'settled': [{'meta': '00:30', 'title': 'Picked a name', 'detail': 'FlightDeck'}],
        'spark': {'cluster': 'demo', 'nodes': [
            {'name': 'node-a', 'status': 'online', 'read_at': at, 'gpu_util_pct': 40.0,
             'mem_used_bytes': 50e9, 'mem_total_bytes': 100e9, 'temp_c': 60, 'power_w': 30},
            {'name': 'node-b', 'status': 'offline', 'error': 'ssh timeout'}],
            'history': [{'at': at, 'gpu': {'node-a': 40.0}}]},
        'metrics': {'title': 'This machine', 'items': [
            {'key': 'cpu', 'label': 'CPU', 'pct': 12.5}, {'label': 'Disk', 'pct': None, 'detail': 'unsupported'}]},
        'activity': {'window': '1h', 'commits': 3, 'prs_opened': 1, 'prs_merged': 2, 'at': at},
    }


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.assets = self.root / 'assets'
        self.assets.mkdir()
        (self.assets / 'banner.webp').write_bytes(b'RIFF\x00\x00\x00\x00WEBPfake')

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, slots=None, data=None, **extra):
        cfg = self.root / 'config.json'
        cfg.write_text(json.dumps({'slots': slots or FULL, **extra}))
        dp = self.root / 'data.json'
        dp.write_text(json.dumps(data if data is not None else fake_data()))
        return cfg, dp

    def ctx(self, data=None):
        return RenderContext(assets_dir=self.assets, data=data if data is not None else fake_data(), config={})


class RenderTests(Base):
    def test_render_writes_full_page_with_every_slot(self):
        cfg, dp = self.write()
        out = self.root / 'site' / 'index.html'
        doc = R.render(cfg, dp, out)
        self.assertEqual(out.read_text(), doc)
        self.assertTrue(doc.startswith('<!doctype html>'))
        self.assertIn('<title>Demo deck</title>', doc)
        top = re.search(r'<div class="top">(.*?)</div>\n<main', doc, re.S).group(1)
        self.assertRegex(top, r'^<figure class="banner"><img [^>]+></figure><section class="spark".*<section class="activity"')
        ids = re.findall(r'<section class="pane" id="([a-z]+)"', doc)
        self.assertEqual(ids, ['streams', 'decisions', 'steps', 'merges', 'priorities', 'settled', 'architecture'])
        self.assertIn('Alpha', doc)
        self.assertIn('.banner img{display:block;width:100%;height:auto;object-fit:unset;', doc)

    def test_public_template_uses_flightdeck_storage_keys_and_no_private_copy(self):
        cfg, dp = self.write()
        doc = R.render(cfg, dp, self.root / 'o.html')
        self.assertIn("'flightdeck.collapsed.v1'", doc)
        self.assertIn("'flightdeck.responses.v1'", doc)
        self.assertIn("'flightdeck.archTab.v1'", doc)
        for bad in ('crewTracker', 'crew-tracker', 'Neuromancer', 'Flockmate', 'flockmate', '__STALE_MIN__'):
            self.assertNotIn(bad, doc)

    def test_no_external_requests(self):
        cfg, dp = self.write()
        doc = R.render(cfg, dp, self.root / 'o.html')
        srcs = [m for m in re.findall(r'<(\w+)\s[^>]*?\b(?:src|href)="https?://', doc) if m != 'a']
        self.assertEqual(srcs, [])
        self.assertNotIn('@import', doc)

    def test_empty_cluster_marks_top_row(self):
        slots = dict(FULL, cluster='empty', architecture='empty')
        cfg, dp = self.write(slots)
        doc = R.render(cfg, dp, self.root / 'o.html')
        self.assertIn('<div class="top no-spark">', doc)
        self.assertNotIn('class="spark', doc)
        self.assertNotIn('id="architecture"', doc)

    def test_metrics_generic_fills_cluster_slot(self):
        cfg, dp = self.write(dict(FULL, cluster='metrics.generic'))
        doc = R.render(cfg, dp, self.root / 'o.html')
        self.assertIn('<section class="spark metrics"', doc)
        self.assertIn('This machine', doc)
        self.assertIn('style="width:12.5%"', doc)
        self.assertRegex(doc, r'data-k="disk"><span class="ml">Disk</span><span class="mv">n/a</span><span class="bar" hidden>')

    def test_assets_dir_from_config_and_override(self):
        other = self.root / 'other'
        other.mkdir()
        (other / 'banner.webp').write_bytes(b'zz')
        cfg, dp = self.write(assets_dir='other')
        self.assertIn('base64,eno="', R.render(cfg, dp, self.root / 'o.html'))
        self.assertIn('base64,UklG', R.render(cfg, dp, self.root / 'o.html', assets_dir=self.assets))

    def test_fonts_embedded_when_present(self):
        (self.assets / 'fonts').mkdir()
        (self.assets / 'fonts' / 'geist-500.woff2').write_bytes(b'font')
        cfg, dp = self.write()
        doc = R.render(cfg, dp, self.root / 'o.html')
        self.assertIn("font-family:'Geist Sans';font-style:normal;font-weight:500", doc)

    def test_cli(self):
        cfg, dp = self.write()
        out = self.root / 'cli.html'
        self.assertEqual(R.main([str(cfg), str(dp), str(out)]), 0)
        self.assertIn('Demo deck', out.read_text())

    def test_empty_data_still_renders(self):
        cfg, dp = self.write(data={})
        doc = R.render(cfg, dp, self.root / 'o.html')
        self.assertIn('<title>FlightDeck</title>', doc)
        self.assertIn('None open.', doc)
        self.assertIn('No priorities set.', doc)
        self.assertIn('No diagrams yet.', doc)


class WidgetPortTests(Base):
    def test_streams_badge_counts_who_needs_you(self):
        out = render_slot('streams.table', self.ctx())
        self.assertIn('2 bots · 1 need you', out)
        self.assertIn('class="st none">Waiting on you: Nothing', out)

    def test_decisions_open_first_with_respond_controls(self):
        out = render_slot('decisions.cards', self.ctx())
        self.assertLess(out.index('data-id="dec-1"'), out.index('Settled'))
        self.assertIn('1 open · 1 settled', out)
        self.assertIn('<ul class="prose-list"><li>one</li><li>two</li></ul>', out)
        self.assertIn('<a href="https://github.com/example/app/pull/1" target="_blank" rel="noopener">PR</a>', out)
        self.assertEqual(out.count('data-act="accepted"'), 2)

    def test_steps_and_merges_have_tick_boxes(self):
        st = render_slot('steps.checklist', self.ctx())
        self.assertIn('1 open', st)
        self.assertIn('class="meta blocks"', st)
        self.assertIn(' checked disabled', st)
        mg = render_slot('merges.table', self.ctx())
        self.assertEqual(mg.count('class="tick"'), 2)
        self.assertIn('2 PRs · 1 ready', mg)
        self.assertIn('Merge in order.', mg)

    def test_priorities_and_settled(self):
        pr = render_slot('priorities.list', self.ctx())
        self.assertIn('1 streams · 1 now · 1 blocked', pr)
        self.assertIn('class="pi p-current"', pr)
        se = render_slot('settled.list', self.ctx())
        self.assertIn('Picked a name', se)

    def test_cluster_rows_trends_and_offline(self):
        out = cluster.render(self.ctx(), now=NOW)
        self.assertIn('demo cluster', out)
        self.assertIn('1 online', out)
        self.assertIn('data-node="node-a"', out)
        self.assertIn('class="nrow s-offline"', out)
        self.assertIn('Offline: ssh timeout', out)
        self.assertIn('<path class="tl" data-node="node-a"', out)
        self.assertIn('id="trends-data"', out)

    def test_cluster_without_nodes(self):
        out = render_slot('cluster.gpu', self.ctx({}))
        self.assertIn('No nodes configured.', out)
        self.assertIn('0 online', out)

    def test_sample_spark_keeps_the_chart_after_the_hour(self):
        d = fake_data()
        end = NOW - datetime.timedelta(days=3)
        hist = []
        for i in range(0, 61, 5):
            at = end - datetime.timedelta(minutes=60 - i)
            hist.append({'at': at.isoformat(), 'gpu': {'demo-a': 40 + (i % 20), 'demo-b': 30 + (i % 15)}})
        d['spark'] = {
            'sample': True, 'cluster': 'demo',
            'nodes': [
                {'name': 'demo-a', 'status': 'online', 'read_at': end.isoformat(), 'gpu_util_pct': 55.0,
                 'mem_used_bytes': 40e9, 'mem_total_bytes': 80e9, 'temp_c': 60, 'power_w': 40},
                {'name': 'demo-b', 'status': 'online', 'read_at': end.isoformat(), 'gpu_util_pct': 42.0,
                 'mem_used_bytes': 30e9, 'mem_total_bytes': 80e9, 'temp_c': 55, 'power_w': 35},
            ],
            'history': hist,
        }
        out = cluster.render(self.ctx(d), now=NOW)
        self.assertIn('class="tr-empty" hidden', out)
        self.assertIn('class="nrow s-online"', out)
        self.assertIn('"sample": true', out)
        self.assertIn('data-node="demo-a"', out)

    def test_sample_spark_page_never_polls_live_readings(self):
        from flightdeck.page_js import JS
        self.assertIn("&&!(TR&&TR.sample)){var poll=", JS)

    def test_activity_counts_and_weekly_staleness(self):
        d = fake_data()
        start = week_start(NOW, LONDON)
        d['activity_weekly'] = {'commits': 9, 'prs_opened': 4, 'prs_merged': 5, 'at': NOW.isoformat(),
                                'since': start.isoformat()}
        out = activity.render(RenderContext(assets_dir=self.assets, data=d, config={}), now=NOW)
        self.assertIn('data-window="1h">3<', out)
        self.assertIn('data-window="week">9<', out)
        d['activity_weekly']['since'] = (start - datetime.timedelta(days=7)).isoformat()
        out = activity.render(RenderContext(assets_dir=self.assets, data=d, config={}), now=NOW)
        self.assertIn('data-window="week">0<', out)
        self.assertIn('Collecting…', out)

    def test_activity_sample_keeps_counts_when_the_week_is_stale(self):
        d = fake_data()
        start = week_start(NOW, LONDON)
        d['activity_weekly'] = {
            'commits': 9, 'prs_opened': 4, 'prs_merged': 5, 'at': NOW.isoformat(),
            'since': (start - datetime.timedelta(days=7)).isoformat(), 'sample': True,
        }
        out = activity.render(RenderContext(assets_dir=self.assets, data=d, config={}), now=NOW)
        self.assertIn('data-window="week">9<', out)
        self.assertIn('Example week', out)
        self.assertNotIn('Collecting…', out)

    def test_week_starts_friday_1700(self):
        start = week_start(NOW, LONDON)
        self.assertEqual((start.weekday(), start.hour, start.minute), (4, 17, 0))
        self.assertLessEqual(start, NOW)
        self.assertGreater(start, NOW - datetime.timedelta(days=7))

    def test_architecture_refuses_stale_render(self):
        arch = self.assets / 'architecture'
        (arch / 'rendered').mkdir(parents=True)
        (arch / 'demo.bower.json').write_text(json.dumps({'schema': 'bowerbird/v1', 'meta': {'title': 'D'}, 'nodes': []}))
        (arch / 'rendered' / 'manifest.json').write_text(json.dumps({'diagrams': {'demo.bower.json': {'sha256': 'old'}}}))
        d = {'projects': {'tabs': [{'id': 'demo', 'diagram': 'architecture/demo.bower.json'}]}}
        with self.assertRaises(ValueError) as cm:
            render_slot('architecture.diagrams', self.ctx(d))
        self.assertIn('changed since it was rendered', str(cm.exception))

    def test_architecture_inlines_self_contained_pages(self):
        import hashlib
        arch = self.assets / 'architecture'
        for v in ('iso', 'flat'):
            (arch / 'rendered' / v).mkdir(parents=True)
            (arch / 'rendered' / v / 'demo.html').write_text(
                '<html><head><link rel="stylesheet" href="https://fonts.example/x.css"></head><body>D</body></html>')
        src = json.dumps({'schema': 'bowerbird/v1', 'meta': {'title': 'Demo app', 'repos': ['example/app']},
                          'nodes': [{'status': 'implemented'}, {'status': 'planned', 'unverified': True}]}).encode()
        (arch / 'demo.bower.json').write_bytes(src)
        (arch / 'rendered' / 'manifest.json').write_text(json.dumps(
            {'diagrams': {'demo.bower.json': {'sha256': hashlib.sha256(src).hexdigest()}}}))
        (self.assets / 'fonts').mkdir()
        (self.assets / 'fonts' / 'geist-variable.ttf').write_bytes(b'ttf')
        d = {'projects': {'tabs': [{'id': 'demo', 'diagram': 'architecture/demo.bower.json'}]}}
        out = render_slot('architecture.diagrams', self.ctx(d))
        self.assertIn('1 projects · 2 parts', out)
        self.assertIn('1 built · 1 unverified', out)
        self.assertIn('id="bb-demo-iso"', out)
        self.assertIn('id="bb-font"', out)
        self.assertNotIn('fonts.example', out)
        self.assertIn('flightdeck-fonts', out)


if __name__ == '__main__':
    unittest.main()
