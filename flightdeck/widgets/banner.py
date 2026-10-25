"""The `banner.image` widget: assets_dir/banner.webp embedded as base64 (no external requests)."""
import base64
from html import escape
from pathlib import Path

DEFAULT_ALT = 'FlightDeck banner'


def render(ctx):
    p = Path(ctx.assets_dir) / 'banner.webp'
    if not p.is_file():
        raise FileNotFoundError(f'banner.image: missing banner file {p}')
    banner_cfg = ctx.config.get('banner') if isinstance(ctx.config, dict) else None
    alt = (banner_cfg or {}).get('alt', DEFAULT_ALT)
    b64 = base64.b64encode(p.read_bytes()).decode()
    return (f'<figure class="banner"><img src="data:image/webp;base64,{b64}" '
            f'width="1600" height="915" alt="{escape(alt, quote=True)}"></figure>')
