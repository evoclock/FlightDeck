"""Widget registry: render_slot(widget_id, ctx) dispatches to one widget module."""
from dataclasses import dataclass, field
from pathlib import Path

from flightdeck.config import KNOWN_WIDGETS, ConfigError
from flightdeck.widgets import (activity, architecture, banner, cluster, decisions, empty, merges, metrics,
                                priorities, settled, steps, streams)


@dataclass
class RenderContext:
    assets_dir: Path
    data: dict = field(default_factory=dict)
    config: dict = field(default_factory=dict)


REGISTRY = {
    'empty': empty.render,
    'banner.image': banner.render,
    'cluster.gpu': cluster.render,
    'metrics.generic': metrics.render,
    'activity.github': activity.render,
    'streams.table': streams.render,
    'decisions.cards': decisions.render,
    'steps.checklist': steps.render,
    'merges.table': merges.render,
    'priorities.list': priorities.render,
    'settled.list': settled.render,
    'architecture.diagrams': architecture.render,
}


def render_slot(widget_id: str, ctx: RenderContext) -> str:
    if widget_id not in KNOWN_WIDGETS:
        raise ConfigError(f'unknown widget: {widget_id}')
    fn = REGISTRY.get(widget_id)
    if fn is None:
        raise ConfigError(f'widget not implemented yet: {widget_id}')
    return fn(ctx)
