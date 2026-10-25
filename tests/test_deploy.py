"""Local publish and the Cloudflare Worker dry-run embed the scrubbed demo and no live secrets."""
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / 'site'
DEMO = ROOT / 'examples' / 'demo'

# Product and host markers that belong in the private instance, not this tree.
FORBIDDEN = (
    'flockmate',
    'neuromancer',
    'crew-tracker',
    'gmail.com',
)
HEX_ID = re.compile(r'\b[0-9a-f]{32}\b')


def _text(path):
    return Path(path).read_text(encoding='utf-8')


class DemoBannerAltTests(unittest.TestCase):
    def test_demo_alt_names_the_banner(self):
        cfg = json.loads(_text(DEMO / 'config.json'))
        self.assertEqual(cfg['banner']['alt'], 'FlightDeck demo banner')
        self.assertNotIn('placeholder', cfg['banner']['alt'].lower())


class SiteExampleTests(unittest.TestCase):
    def test_example_uses_placeholders_and_demo_worker_name(self):
        cfg = json.loads(_text(SITE / 'site.example.json'))
        self.assertEqual(cfg['worker_name'], 'flightdeck-demo')
        self.assertEqual(cfg['account_id'], 'ACCOUNT_ID')
        self.assertEqual(cfg['zone_id'], 'ZONE_ID')
        self.assertEqual(cfg['access_aud'], 'ACCESS_AUD')
        self.assertEqual(cfg['responses_kv_id'], 'RESPONSES_KV_ID')
        self.assertEqual(cfg['spark_kv_id'], 'SPARK_KV_ID')
        self.assertEqual(cfg['allowed_emails'], ['you@example.com'])
        self.assertEqual(cfg['access_team_domain'], 'TEAM.cloudflareaccess.com')
        self.assertEqual(cfg['hostname'], 'example.workers.dev')

    def test_live_site_json_is_not_committed(self):
        self.assertFalse((SITE / 'site.json').exists())


class PublishTests(unittest.TestCase):
    def test_publish_local_renders_demo_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'local'
            subprocess.check_call(['bash', str(ROOT / 'scripts' / 'publish_local.sh'), str(out)], cwd=ROOT)
            html = _text(out / 'index.html')
            self.assertIn('<!doctype html>', html)
            self.assertIn('OpenMausBot', html)
            self.assertIn('alt="FlightDeck demo banner"', html)
            self.assertTrue((out / 'assets' / 'banner.webp').is_file())
            self.assertTrue((out / 'assets' / 'flightdeck-demo.mp4').is_file())
            self.assertFalse((out / 'assets' / 'flock-tracker-demo.mp4').exists())

    def test_cloudflare_build_embeds_that_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / 'local'
            dist = Path(tmp) / 'cf'
            subprocess.check_call(['bash', str(ROOT / 'scripts' / 'publish_local.sh'), str(local)], cwd=ROOT)
            subprocess.check_call([
                'python3', str(SITE / 'build.py'),
                '--html', str(local / 'index.html'),
                '--site', str(SITE / 'site.example.json'),
                '--out', str(dist),
            ], cwd=ROOT)
            html = _text(local / 'index.html')
            worker = _text(dist / 'worker.js')
            wrangler = json.loads(_text(dist / 'wrangler.json'))
            self.assertIn(json.dumps(html), worker)
            self.assertIn('OpenMausBot', worker)
            # The page is embedded as a JSON string, so attribute quotes are escaped.
            self.assertIn(json.dumps('alt="FlightDeck demo banner"')[1:-1], worker)
            self.assertEqual(wrangler['name'], 'flightdeck-demo')
            self.assertEqual(wrangler['account_id'], 'ACCOUNT_ID')
            self.assertTrue(wrangler['observability']['enabled'])
            self.assertTrue(wrangler['observability']['traces']['enabled'])
            self.assertEqual(wrangler['compatibility_date'], '2026-10-25')
            self.assertIn('/api/responses', worker)
            self.assertIn('/api/spark', worker)
            self.assertIn('FLIGHTDECK_RESPONSES', worker)
            self.assertIn('FLIGHTDECK_SPARK', worker)
            blob = worker + _text(dist / 'deploy-mcp.js')
            low = blob.lower()
            for bad in FORBIDDEN:
                self.assertNotIn(bad, low, bad)


class PublicTreeSecretTests(unittest.TestCase):
    def test_site_scripts_and_readme_have_no_live_secrets(self):
        required = [
            SITE / 'site.example.json',
            SITE / 'build.py',
            SITE / 'api.js',
            SITE / 'worker.template.js',
            SITE / 'access-setup-mcp.js',
            ROOT / 'scripts' / 'publish_local.sh',
            ROOT / 'scripts' / 'publish_cloudflare.sh',
            ROOT / 'README.md',
            ROOT / 'docs' / 'deploy-cloudflare.md',
            ROOT / 'docs' / 'deploy-local.md',
        ]
        for path in required:
            self.assertTrue(path.is_file(), path)
        paths = list(SITE.glob('*'))
        paths += list((ROOT / 'scripts').glob('*'))
        paths += list((ROOT / 'hooks').rglob('*'))
        paths += list((ROOT / 'collectors').glob('*.py'))
        paths += [
            ROOT / 'README.md',
            ROOT / 'docs' / 'deploy-cloudflare.md',
            ROOT / 'docs' / 'deploy-local.md',
            ROOT / 'publish.sh',
            ROOT / 'config' / 'sync.example.json',
        ]
        blob = []
        for path in paths:
            if path.is_file() and path.suffix != '.pyc':
                blob.append(_text(path))
        low = '\n'.join(blob).lower()
        for bad in FORBIDDEN:
            self.assertNotIn(bad.lower(), low, bad)
        self.assertNotIn('claude', low)
        self.assertIsNone(HEX_ID.search(low), '32-hex account or namespace id in public sources')

    def test_docs_attribute_the_demo_banner_to_gpt_astra(self):
        spec = _text(ROOT / 'docs' / 'superpowers' / 'specs' / '2026-10-25-flightdeck-design.md')
        plan = _text(ROOT / 'docs' / 'superpowers' / 'plans' / '2026-10-25-flightdeck.md')
        readme = _text(ROOT / 'README.md')
        for label, text in (('spec', spec), ('plan', plan), ('readme', readme)):
            self.assertNotIn('Claude', text, label)
            self.assertIn('GPT Astra', text, label)


if __name__ == '__main__':
    unittest.main()
