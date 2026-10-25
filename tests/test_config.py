import unittest
from pathlib import Path
from flightdeck.config import SLOT_IDS, load_config, resolve_widget, validate, ConfigError

ROOT = Path(__file__).resolve().parent.parent


class TestConfig(unittest.TestCase):
    def test_slot_ids_locked(self):
        self.assertEqual(SLOT_IDS, (
            'banner', 'cluster', 'activity', 'streams', 'decisions',
            'steps', 'merges', 'priorities', 'settled', 'architecture',
        ))

    def test_resolve_widget(self):
        cfg = {'slots': {s: 'empty' for s in SLOT_IDS}}
        cfg['slots']['banner'] = 'banner.image'
        self.assertEqual(resolve_widget(cfg, 'banner'), 'banner.image')

    def test_unknown_widget_raises(self):
        cfg = {'slots': {s: 'empty' for s in SLOT_IDS}}
        cfg['slots']['banner'] = 'no.such'
        with self.assertRaises(ConfigError):
            validate(cfg)

    def test_unknown_slot_raises(self):
        cfg = {'slots': {s: 'empty' for s in SLOT_IDS}}
        with self.assertRaises(ConfigError):
            resolve_widget(cfg, 'nope')

    def test_missing_slot_raises(self):
        cfg = {'slots': {s: 'empty' for s in SLOT_IDS[1:]}}
        with self.assertRaises(ConfigError):
            validate(cfg)

    def test_load_example(self):
        cfg = load_config(ROOT / 'config.example.json')
        for s in SLOT_IDS:
            self.assertIn(s, cfg['slots'])


if __name__ == '__main__':
    unittest.main()
