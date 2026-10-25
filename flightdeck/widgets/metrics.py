"""`metrics.generic`: simple host bars for installs without a GPU cluster.

data.json `metrics` = {title?, at?, note?, items: [{key?, label, pct, text?, detail?}]} (a bare list of items works
too). `pct` is 0..100 or null; null prints n/a and hides the bar, never a made-up number.
"""
from flightdeck.common import e, hm_zone, tz


def row(m):
    pct = m.get("pct")
    text = m.get("text") or ("n/a" if pct is None else f"{pct:.0f}%")
    width = max(0, min(100, pct or 0))
    key = m.get("key") or str(m.get("label", "")).lower().replace(" ", "-")
    return (f'<div class="mrow" data-k="{e(key)}"><span class="ml">{e(m.get("label", ""))}</span><span class="mv">{e(text)}</span>'
            f'<span class="bar"{"" if pct is not None else " hidden"}><i style="width:{width:g}%"></i></span>'
            f'<span class="mx">{e(m.get("detail") or "")}</span></div>')


def render(ctx):
    m = ctx.data.get("metrics") or {}
    if isinstance(m, list):
        m = {"items": m}
    items = m.get("items") or []
    title = m.get("title") or "System"
    foot = ""
    if m.get("at"):
        foot += f'<p class="m-at">Read {e(hm_zone(m["at"], tz(ctx)))}</p>'
    if m.get("note"):
        foot += f'<p class="m-at">{e(m["note"])}</p>'
    body = "".join(row(i) for i in items) or '<p class="muted">Collecting…</p>'
    return (f'<section class="spark metrics" aria-labelledby="metrics-h"><div class="sp-head"><h2 id="metrics-h">{e(title)}</h2></div>'
            f'<div class="sp-body"><div class="mlist">{body}</div>{foot}</div></section>')
