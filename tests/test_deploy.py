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
# The public demo banner is the ADHD Neuromancer artwork, so that name is allowed.
FORBIDDEN = (
    'flockmate',
    'crew-tracker',
    'gmail.com',
)
HEX_ID = re.compile(r'\b[0-9a-f]{32}\b')


def _text(path):
    return Path(path).read_text(encoding='utf-8')


class DemoBannerAltTests(unittest.TestCase):
    def test_demo_alt_names_the_banner(self):
        cfg = json.loads(_text(DEMO / 'config.json'))
        self.assertEqual(cfg['banner']['alt'], 'ADHD Neuromancer')
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
        self.assertEqual(cfg['architecture_kv_id'], 'ARCHITECTURE_KV_ID')
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
            self.assertIn('alt="ADHD Neuromancer"', html)
            self.assertIn('<h1>FlightDeck</h1>', html)
            self.assertNotIn('FlightDeck demo', html)
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
            self.assertIn(json.dumps('alt="ADHD Neuromancer"')[1:-1], worker)
            self.assertEqual(wrangler['name'], 'flightdeck-demo')
            self.assertIn({'binding': 'CREW_ARCHITECTURE', 'id': 'ARCHITECTURE_KV_ID'}, wrangler['kv_namespaces'])
            self.assertIn('env.CREW_ARCHITECTURE', worker)
            self.assertIn('architecture/', worker)
            meta = _text(dist / 'deploy-mcp.js')
            self.assertIn('CREW_ARCHITECTURE', meta)
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


class TokenFileTests(unittest.TestCase):
    def test_token_file_fallback_is_scoped_and_env_wins(self):
        """Why: a deploy must prefer the caller token and never disclose either token in logs."""
        import os
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('scripts', 'site', 'bin'):
                (root / name).mkdir()
            shutil.copy2(ROOT / 'publish.sh', root / 'publish.sh')
            shutil.copy2(ROOT / 'scripts' / 'publish_cloudflare.sh', root / 'scripts' / 'publish_cloudflare.sh')
            (root / 'scripts' / 'publish_local.sh').write_text('#!/bin/bash\nprintf "local:%s\\n" "${CLOUDFLARE_API_TOKEN:-}" >> "$CAPTURE"\n')
            (root / 'scripts' / 'publish_local.sh').chmod(0o755)
            cfg = json.loads(_text(SITE / 'site.example.json'))
            cfg.update(account_id='test-account', zone_id='test-zone', access_aud='test-aud',
                       hostname='test.invalid', access_team_domain='team.test.invalid',
                       allowed_emails=['test@test.invalid'], architecture_kv_id='', responses_kv_id='', spark_kv_id='')
            (root / 'site' / 'site.json').write_text(json.dumps(cfg))
            (root / 'site' / 'build.py').write_text(
                'import os\nwith open(os.environ["CAPTURE"], "a") as f: f.write("build:" + os.environ.get("CLOUDFLARE_API_TOKEN", "") + "\\n")\n')
            (root / 'scripts' / 'upload_architecture_kv.py').write_text(
                'import os\nwith open(os.environ["CAPTURE"], "a") as f: f.write("upload:" + os.environ.get("CLOUDFLARE_API_TOKEN", "") + "\\n")\n')
            npx = root / 'bin' / 'npx'
            npx.write_text('#!/bin/bash\nprintf "wrangler:%s\\n" "${CLOUDFLARE_API_TOKEN:-}" >> "$CAPTURE"\n')
            npx.chmod(0o755)
            token_file = root / 'token'
            token_file.write_text('file-secret\n')
            token_file.chmod(0o644)
            capture = root / 'capture'
            env = dict(os.environ, CAPTURE=str(capture), CREW_TRACKER_CF_TOKEN_FILE=str(token_file),
                       PATH=str(root / 'bin') + os.pathsep + os.environ['PATH'])
            for explicit, expected in (('env-secret', 'env-secret'), (None, 'file-secret')):
                capture.write_text('')
                env.pop('CLOUDFLARE_API_TOKEN', None)
                if explicit is not None:
                    env['CLOUDFLARE_API_TOKEN'] = explicit
                result = subprocess.run(['bash', str(root / 'publish.sh'), '--deploy'],
                                        cwd=root, env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(capture.read_text().splitlines(),
                                 [f'local:{explicit or ""}', f'build:{explicit or ""}',
                                  f'upload:{expected}', f'wrangler:{expected}'])
                self.assertNotIn('file-secret', result.stdout + result.stderr)
                self.assertNotIn('env-secret', result.stdout + result.stderr)
                if explicit is None:
                    self.assertIn('mode 600', result.stderr)
                else:
                    self.assertNotIn('mode 600', result.stderr)
            env['CREW_TRACKER_CF_TOKEN_FILE'] = str(root / 'absent-token')
            capture.write_text('')
            result = subprocess.run(['bash', str(root / 'publish.sh'), '--deploy'],
                                    cwd=root, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(capture.read_text().splitlines(), ['local:', 'build:', 'upload:', 'wrangler:'])


class ArchitectureBindingTests(unittest.TestCase):
    def test_worker_read_requires_declared_binding(self):
        """Why: an architecture read without a declared KV binding silently leaves frames blank."""
        import importlib.util
        spec = importlib.util.spec_from_file_location('flightdeck_site_build', SITE / 'build.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cfg = json.loads(_text(SITE / 'site.example.json'))
        module.check_worker_bindings(module.build_worker('<html></html>', cfg), module.kv_bindings(cfg), cfg)
        with self.assertRaisesRegex(SystemExit, 'CREW_ARCHITECTURE'):
            module.check_worker_bindings(module.build_worker('<html></html>', cfg), [], cfg)
        cfg.pop('architecture_kv_id')
        module.check_worker_bindings(module.build_worker('<html></html>', cfg), module.kv_bindings(cfg), cfg)
        self.assertNotIn('CREW_ARCHITECTURE', dict(module.kv_bindings(cfg)))


class ArchitectureUploadTests(unittest.TestCase):
    def test_upload_only_changed_views_and_never_delete(self):
        """Why: unchanged diagrams must not write KV and missing views must not delete remote keys."""
        import importlib.util
        import io
        from unittest.mock import patch
        spec = importlib.util.spec_from_file_location('architecture_upload', ROOT / 'scripts' / 'upload_architecture_kv.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / 'source'
            iso = source / 'rendered' / 'iso' / 'sample.html'
            flat = source / 'rendered' / 'flat' / 'sample.html'
            iso.parent.mkdir(parents=True)
            flat.parent.mkdir(parents=True)
            iso.write_text('first', encoding='utf-8')
            flat.write_text('flat', encoding='utf-8')
            data = base / 'data.json'
            data.write_text(json.dumps({'projects': {'tabs': [{'id': 'sample', 'diagram': 'architecture/sample.bower.json'}]}}), encoding='utf-8')
            cfg = base / 'site.json'
            cfg.write_text(json.dumps({'architecture_kv_id': 'test-namespace', 'account_id': 'test-account'}), encoding='utf-8')
            dist = base / 'dist'
            with patch.dict(module.os.environ, {'CLOUDFLARE_API_TOKEN': 'test-token'}), patch.object(module, 'urlopen') as runner:
                runner.side_effect = lambda *a, **kw: io.BytesIO(b'{"success":true}')
                module.upload(source, dist, cfg, data, dry_run=True)
                self.assertFalse((dist / 'architecture-kv-manifest.json').exists())
                runner.assert_not_called()
                module.upload(source, dist, cfg, data)
                self.assertEqual(runner.call_count, 2)
                self.assertIn('architecture/sample/flat.html', runner.call_args.args[0].full_url)
                self.assertEqual(runner.call_args.args[0].get_header('Authorization'), 'Bearer test-token')
                self.assertEqual((dist / 'assets' / 'architecture' / 'sample' / 'iso.html').read_text(), 'first')
                module.upload(source, dist, cfg, data)
                self.assertEqual(runner.call_count, 2)
                iso.write_text('second', encoding='utf-8')
                module.upload(source, dist, cfg, data)
                self.assertEqual(runner.call_count, 3)
                data.write_text(json.dumps({'projects': {'tabs': []}}), encoding='utf-8')
                module.upload(source, dist, cfg, data)
                self.assertEqual(runner.call_count, 3)
                cfg.write_text('{}', encoding='utf-8')
                module.upload(source, dist, cfg, data)
                self.assertEqual(runner.call_count, 3)


class PartialReceiptTests(unittest.TestCase):
    def test_uploaded_worker_reports_domain_failure(self):
        """Why: uploaded code must get a receipt even when domain binding fails."""
        import importlib.util
        spec = importlib.util.spec_from_file_location('flightdeck_site_build', SITE / 'build.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cfg = json.loads(_text(SITE / 'site.example.json'))
        source = module.deploy_mcp('worker', cfg, {})
        script = """const cloudflare={request:async x=>{if(x.path.endsWith('/workers/domains'))throw Error('domain unavailable');return {success:true,result:{etag:'ok'}}}};
""" + '(' + source.strip() + ')().then(x=>console.log(JSON.stringify(x)))'
        result = subprocess.run(['node', '-e', script], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(result.stdout)
        self.assertTrue(receipt['uploaded'])
        self.assertEqual(receipt['domain'], 'failed: domain unavailable')


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

    def test_docs_name_the_shipped_banner(self):
        spec = _text(ROOT / 'docs' / 'superpowers' / 'specs' / '2026-10-25-flightdeck-design.md')
        plan = _text(ROOT / 'docs' / 'superpowers' / 'plans' / '2026-10-25-flightdeck.md')
        readme = _text(ROOT / 'README.md')
        for label, text in (('spec', spec), ('plan', plan), ('readme', readme)):
            self.assertNotIn('Claude', text, label)
        self.assertIn('GPT Astra', spec)
        self.assertIn('GPT Astra', plan)
        self.assertIn('examples/demo/assets/banner.webp', readme)
        self.assertNotIn('GPT Astra', readme)


if __name__ == '__main__':
    unittest.main()
