"""Config loader: ten locked slots, each mapped to one known widget id."""
import json
from pathlib import Path

SLOT_IDS = (
    'banner', 'cluster', 'activity', 'streams', 'decisions',
    'steps', 'merges', 'priorities', 'settled', 'architecture',
)
KNOWN_WIDGETS = frozenset({
    'banner.image', 'cluster.gpu', 'metrics.generic', 'activity.github',
    'streams.table', 'decisions.cards', 'steps.checklist', 'merges.table',
    'priorities.list', 'settled.list', 'architecture.diagrams', 'empty',
})


class ConfigError(ValueError):
    pass


def resolve_widget(config, slot):
    if slot not in SLOT_IDS:
        raise ConfigError(f'unknown slot: {slot}')
    wid = config['slots'][slot]
    if wid not in KNOWN_WIDGETS:
        raise ConfigError(f'unknown widget: {wid}')
    return wid


def validate(config):
    slots = config.get('slots', {})
    missing = [s for s in SLOT_IDS if s not in slots]
    if missing:
        raise ConfigError(f'missing slots: {missing}')
    extra = [s for s in slots if s not in SLOT_IDS]
    if extra:
        raise ConfigError(f'unknown slot: {extra}')
    for s in SLOT_IDS:
        resolve_widget(config, s)
    return config


def load_config(path: Path) -> dict:
    return validate(json.loads(Path(path).read_text()))
