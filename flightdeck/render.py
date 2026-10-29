"""Assemble the FlightDeck page: config.json slots -> widgets -> one self-contained static HTML file.

Usage: python3 -m flightdeck.render CONFIG DATA OUT [--assets DIR]
`assets_dir` defaults to config `assets_dir` (relative to the config file), else `assets/` beside the config.
Stdlib only; the page makes no runtime requests except optional same-origin /api/* calls when served over http(s).
"""
import argparse
import base64
import json
import logging
import sys
from pathlib import Path

from flightdeck.common import e, local_now, tz
from flightdeck.config import SLOT_IDS, ConfigError, load_config, resolve_widget
from flightdeck.layout_css import CSS
from flightdeck.page_js import JS
from flightdeck.widgets import RenderContext, render_slot
from flightdeck.widgets.cluster import STALE_MIN

TOP_SLOTS = ('banner', 'cluster', 'activity')       # .top row: banner · cluster · activity
PANE_SLOTS = tuple(s for s in SLOT_IDS if s not in TOP_SLOTS)   # main grid, in locked order
TOP_EMPTY_CLASS = {'banner': 'no-banner', 'cluster': 'no-spark', 'activity': 'no-act'}
PALETTE = ["sage", "rust", "peach", "mustard", "slate", "mauve", "olive", "teal", "ochre", "forest", "clay"]
LOG = logging.getLogger(__name__)


def font_faces(assets_dir):
    """Geist Sans embedded from assets_dir/fonts (offline, no external requests). Missing files are skipped."""
    out = []
    for w in (400, 500, 600):
        p = Path(assets_dir) / "fonts" / f"geist-{w}.woff2"
        if p.exists():
            src = "url(data:font/woff2;base64,%s) format('woff2')" % base64.b64encode(p.read_bytes()).decode()
            out.append("@font-face{font-family:'Geist Sans';font-style:normal;font-weight:%d;font-display:swap;src:%s}" % (w, src))
    return "\n".join(out)


def resolve_assets(config, config_path, assets_dir=None):
    if assets_dir is not None:
        return Path(assets_dir)
    return Path(config_path).resolve().parent / (config.get('assets_dir') or 'assets')


def render_html(config, data, assets_dir, now=None):
    ctx = RenderContext(assets_dir=Path(assets_dir), data=data, config=config)
    slots = {}
    for slot in SLOT_IDS:
        widget = resolve_widget(config, slot)
        try:
            slots[slot] = render_slot(widget, ctx)
        except ConfigError:
            raise  # Invalid configuration is not a degraded widget.
        except Exception as exc:
            LOG.error('widget %s in slot %s failed: %s', widget, slot, type(exc).__name__)
            label = slot.capitalize()
            slots[slot] = (f'<section class="pane" id="{slot}"><h2>{label}</h2>'
                           f'<p role="alert">{label} unavailable.</p></section>')
    top_mods = [TOP_EMPTY_CLASS[s] for s in TOP_SLOTS if not slots[s]]
    top = ''
    if len(top_mods) < len(TOP_SLOTS):
        cls = 'top' + ''.join(' ' + m for m in top_mods)
        top = f'<div class="{cls}">{"".join(slots[s] for s in TOP_SLOTS)}</div>'
    panes = "".join(slots[s] for s in PANE_SLOTS)
    zone = tz(ctx)
    now = now or local_now(zone)
    updated = now.strftime("%a %-d %b %Y, %H:%M") + (f" {now.strftime('%Z')}" if now.tzinfo and now.strftime('%Z') else "")
    title = data.get('title') or 'FlightDeck'
    sw = "".join(f'<span class="sw" style="background:var(--{p})" title="{p}"></span>' for p in PALETTE)
    js = JS.replace("__STALE_MIN__", str(STALE_MIN))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light">
<title>{e(title)}</title>
<style>{font_faces(assets_dir)}
{CSS}</style></head><body><div class="wrap">
<header><h1>{e(title)}</h1><span class="updated">Updated {e(updated)}</span>
<div class="tools"><span class="sync muted" id="sync" aria-live="polite">Responses saved in this browser</span>
<button id="ex" type="button" aria-label="Export responses">Export<span class="long"> responses</span></button><button id="xa" type="button" aria-label="Expand all">Expand<span class="long"> all</span></button><button id="ca" type="button" aria-label="Collapse all">Collapse<span class="long"> all</span></button></div></header>
{top}
<main class="grid">{panes}</main>
<footer><span>{e(data.get('summary') or '')}</span><span style="margin-left:auto">{sw}</span></footer>
</div>
<dialog id="export" aria-labelledby="ex-title"><div class="pop"><button class="x" type="button" aria-label="Close">&times;</button>
<h2 id="ex-title">Responses</h2><p class="muted">Copy this JSON for your agents.</p><label class="sr" for="ex-json">Responses JSON</label><textarea id="ex-json" readonly rows="12"></textarea></div></dialog>
<script>{js}</script></body></html>
"""


def render(config_path, data_path, out_path, assets_dir=None, now=None):
    """Read config + data, write the page to out_path, return the HTML string."""
    config = load_config(Path(config_path))
    data = json.loads(Path(data_path).read_text())
    if not isinstance(data, dict):
        raise ValueError('data.json must be an object')
    doc = render_html(config, data, resolve_assets(config, config_path, assets_dir), now=now)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc)
    return doc


def main(argv=None):
    ap = argparse.ArgumentParser(prog='python3 -m flightdeck.render', description=__doc__.splitlines()[0])
    ap.add_argument('config')
    ap.add_argument('data')
    ap.add_argument('out')
    ap.add_argument('--assets', default=None, help='assets dir (banner.webp, fonts/, architecture/)')
    a = ap.parse_args(argv)
    doc = render(a.config, a.data, a.out, assets_dir=a.assets)
    print('wrote', a.out, len(doc), 'bytes', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
