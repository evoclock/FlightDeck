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
    if not isinstance(config, dict):
        raise ConfigError('config must be an object')
    slots = config.get('slots')
    if not isinstance(slots, dict):
        raise ConfigError('slots must be an object')
    if slot not in slots:
        raise ConfigError(f'missing slot: {slot}')
    wid = slots[slot]
    if wid not in KNOWN_WIDGETS:
        raise ConfigError(f'unknown widget: {wid}')
    return wid


def validate(config):
    if not isinstance(config, dict):
        raise ConfigError('config must be an object')
    slots = config.get('slots', {})
    if not isinstance(slots, dict):
        raise ConfigError('slots must be an object')
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
