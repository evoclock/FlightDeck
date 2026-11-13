import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flightdeck.architecture_provenance import check_directory, check_file, check_html, copy_assets
from scripts.upload_architecture_kv import upload

SHA = 'a' * 40
GOOD = f'<html><head><meta name="generator" content="bowerbird 0.2.0"><meta name="bowerbird-input-sha" content="{SHA}"></head></html>'
LEGACY = '<html><head><meta name="generator" content="bowerbird"></head></html>'
HAND = '<html><body>Manual diagram</body></html>'


class ProvenanceTests(unittest.TestCase):
    def test_marker_contract(self):
        self.assertTrue(check_html(GOOD).ok)
        self.assertEqual(check_html(GOOD.replace('bowerbird 0.2.0', 'bowerbird')).missing, ('version',))
        self.assertEqual(check_html(GOOD.replace(f'<meta name="bowerbird-input-sha" content="{SHA}">', '')).missing,
                         ('input SHA',))
        self.assertEqual(check_html(HAND).missing, ('not a bowerbird page',))
        self.assertEqual(check_html(LEGACY).missing, ('version', 'input SHA'))
        self.assertTrue(check_html(f'<html data-bowerbird-version="0.2.0" data-bowerbird-input-sha="{SHA}"><body></body></html>').ok)
        self.assertTrue(check_html(f'<html><body data-bowerbird-version="0.2.0" data-bowerbird-input-sha="{SHA}"></body></html>').ok)
        self.assertEqual(check_html(GOOD.replace(SHA, SHA.upper())).missing, ('input SHA',))

    def test_directory_and_committed_demo(self):
        demo = Path(__file__).parents[1] / 'examples/demo/assets/architecture/rendered/flat/flightdeck.html'
        self.assertEqual(check_file(demo).missing, ('version', 'input SHA'))
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp:
            root = Path(temp)
            (root / 'flat').mkdir()
            (root / 'iso').mkdir()
            (root / 'flat/good.html').write_text(GOOD)
            (root / 'iso/bad.html').write_text(HAND)
            self.assertEqual(list(check_directory(root)), [root / 'iso/bad.html'])

    def test_local_copy_filters_each_file(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp:
            source, dest = Path(temp) / 'assets', Path(temp) / 'out'
            rendered = source / 'architecture/rendered/flat'
            rendered.mkdir(parents=True)
            pages = {'good': GOOD, 'hand': HAND, 'legacy': LEGACY,
                     'partial': GOOD.replace(f'<meta name="bowerbird-input-sha" content="{SHA}">', '')}
            for name, html in pages.items():
                (rendered / f'{name}.html').write_text(html)
            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                copy_assets(source, dest)
            self.assertEqual({p.stem for p in (dest / 'architecture/rendered/flat').glob('*.html')},
                             {'good', 'legacy'})
            self.assertIn('hand.html', stderr.getvalue())
            self.assertIn('partial.html', stderr.getvalue())
            self.assertIn('legacy.html', stderr.getvalue())

    def test_upload_filters_each_file_without_aborting(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp:
            root = Path(temp)
            source = root / 'source'
            tabs = []
            pages = {'good': GOOD, 'hand': HAND, 'legacy': LEGACY,
                     'partial': GOOD.replace('bowerbird 0.2.0', 'bowerbird')}
            for name, html in pages.items():
                tabs.append({'id': name, 'diagram': f'{name}.bower.json'})
                for view in ('flat', 'iso'):
                    path = source / 'rendered' / view / f'{name}.html'
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(html)
            config, data = root / 'config.json', root / 'data.json'
            config.write_text(json.dumps({'architecture_kv_id': 'namespace', 'account_id': 'account'}))
            data.write_text(json.dumps({'projects': {'tabs': tabs}}))
            requests = []

            class Response:
                def __enter__(self):
                    return io.BytesIO(b'{"success": true}')

                def __exit__(self, *args):
                    pass

            def send(request, timeout):
                requests.append(request.full_url)
                return Response()

            with patch.dict('os.environ', {'CLOUDFLARE_API_TOKEN': 'test-token'}), \
                    patch('scripts.upload_architecture_kv.urlopen', side_effect=send), \
                    contextlib.redirect_stderr(io.StringIO()) as stderr:
                self.assertEqual(upload(source, root / 'dist', config, data), 0)
            self.assertEqual(len(requests), 4)
            self.assertTrue(all('/good/' in url or '/legacy/' in url for url in requests))
            for name in ('hand', 'partial', 'legacy'):
                self.assertIn(f'{name}.html', stderr.getvalue())
            self.assertTrue((root / 'dist/architecture-kv-manifest.json').exists())


if __name__ == '__main__':
    unittest.main()
