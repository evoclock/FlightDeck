"""Widget registry: render_slot(widget_id, ctx) dispatches to one widget module."""
from dataclasses import dataclass, field
from pathlib import Path

from flightdeck.config import KNOWN_WIDGETS, ConfigError
from flightdeck.widgets import banner, empty


@dataclass
class RenderContext:
    assets_dir: Path
    data: dict = field(default_factory=dict)
    config: dict = field(default_factory=dict)


REGISTRY = {
    'empty': empty.render,
    'banner.image': banner.render,
}


def render_slot(widget_id: str, ctx: RenderContext) -> str:
    if widget_id not in KNOWN_WIDGETS:
        raise ConfigError(f'unknown widget: {widget_id}')
    fn = REGISTRY.get(widget_id)
    if fn is None:
        raise ConfigError(f'widget not implemented yet: {widget_id}')
    return fn(ctx)
