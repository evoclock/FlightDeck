import base64
import tempfile
import unittest
from pathlib import Path

from flightdeck.config import ConfigError
from flightdeck.widgets import RenderContext, render_slot


class WidgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.assets = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def ctx(self, config=None):
        return RenderContext(data={}, assets_dir=self.assets, config=config or {})

    def test_empty_renders_nothing(self):
        self.assertEqual(render_slot('empty', self.ctx()), '')

    def test_banner_embeds_webp_as_base64(self):
        raw = b'RIFF\x00\x00\x00\x00WEBPfake'
        (self.assets / 'banner.webp').write_bytes(raw)
        out = render_slot('banner.image', self.ctx())
        self.assertTrue(out.startswith('<figure class="banner"><img '))
        self.assertIn('src="data:image/webp;base64,' + base64.b64encode(raw).decode() + '"', out)
        self.assertIn('alt="', out)
        self.assertTrue(out.endswith('</figure>'))

    def test_banner_alt_from_config_is_escaped(self):
        (self.assets / 'banner.webp').write_bytes(b'x')
        out = render_slot('banner.image', self.ctx({'banner': {'alt': 'a <b> & "c"'}}))
        self.assertIn('alt="a &lt;b&gt; &amp; &quot;c&quot;"', out)

    def test_missing_banner_file_raises_clear_error(self):
        with self.assertRaises(FileNotFoundError) as cm:
            render_slot('banner.image', self.ctx())
        self.assertIn('banner.webp', str(cm.exception))

    def test_unknown_widget_raises(self):
        with self.assertRaises(ConfigError) as cm:
            render_slot('nope.widget', self.ctx())
        self.assertIn('nope.widget', str(cm.exception))

    def test_known_but_unimplemented_widget_raises(self):
        with self.assertRaises(ConfigError) as cm:
            render_slot('streams.table', self.ctx())
        self.assertIn('streams.table', str(cm.exception))


if __name__ == '__main__':
    unittest.main()
