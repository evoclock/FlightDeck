"""`cluster.gpu`: Nvidia-style per-node GPU/memory/temp/power plus a last-hour GPU utilization trend.

data.json `spark` = {cluster, nodes: [{name, status, read_at, gpu_util_pct, mem_used_bytes, mem_total_bytes,
temp_c, power_w, error}], history: [{at, gpu: {node: pct}}]}. The page script re-checks staleness at view time
and, when served with a /api/spark endpoint, refreshes every 60s.
"""
import datetime
import json

from flightdeck.common import e

STALE_MIN = 10
TREND_MIN, TREND_GAP_MIN = 60, 12          # a gap longer than two 5-min runs breaks the line
# Calm colour per node; never rust/peach/clay (orange/red reads as redlining). Dash is a second cue.
TREND_COLORS = ["teal", "mustard", "mauve", "slate", "olive", "forest"]
TREND_DASH = ["", "7 4", "2 3", "10 3 2 3"]
NODE_LABEL = {"online": "Online", "stale": f"Stale, over {STALE_MIN} min", "offline": "Offline", "never": "No reading yet"}


def gb(b):
    return f"{b / 1e9:.0f} GB"   # decimal GB


def node_metrics(n):
    """(key, label, text, percent or None, extra); None prints as n/a, never as a number."""
    u, used, tot = n.get("gpu_util_pct"), n.get("mem_used_bytes"), n.get("mem_total_bytes")
    mp = round(100 * used / tot) if used is not None and tot else None
    return [
        ("gpu", "GPU", "n/a" if u is None else f"{u:.0f}%", u, ""),
        ("mem", "System memory", "n/a" if mp is None else f"{mp}%", mp, f"{gb(used)} of {gb(tot)}" if mp is not None else ""),
        ("temp", "Temp", "n/a" if n.get("temp_c") is None else f"{n['temp_c']:.0f}°C", None, ""),
        ("power", "Power", "n/a" if n.get("power_w") is None else f"{n['power_w']:.0f} W", None, ""),
    ]


def node_state(n, at=None):
    if n.get("status") == "offline":
        return "offline"
    if n.get("status") != "online" or not n.get("read_at"):
        return "never"
    age = (at or datetime.datetime.now().astimezone()) - datetime.datetime.fromisoformat(n["read_at"])
    return "stale" if age > datetime.timedelta(minutes=STALE_MIN) else "online"


def node_row(n, at=None):
    st = node_state(n, at)
    when = datetime.datetime.fromisoformat(n["read_at"]).strftime("%H:%M") if n.get("read_at") else ""
    sub = {"online": f"Read {when}", "stale": f"{NODE_LABEL[st]} · read {when}",
           "offline": f"Offline{' · ' + when if when else ''}{': ' + n['error'] if n.get('error') else ''}"}.get(st, NODE_LABEL[st])
    mets = "".join(f'<div class="m" data-k="{k}"><span class="ml">{l}</span><span class="mv">{e(t)}</span>'
                   f'<span class="bar"{"" if p is not None else " hidden"}><i style="width:{max(0, min(100, p or 0))}%"></i></span>'
                   f'<span class="mx">{e(x)}</span></div>' for k, l, t, p, x in node_metrics(n))
    return (f'<div class="nrow s-{st}" data-node="{e(n["name"])}" data-read-at="{e(n.get("read_at", ""))}" data-status="{e(n.get("status", "never"))}">'
            f'<div class="nn"><span class="nname"><span class="sdot" aria-hidden="true"></span>{e(n["name"])}</span>'
            f'<span class="nsub">{e(sub)}</span></div>{mets}</div>')


def trend_names(nodes, history):
    names, seen = [], set()
    for k in [n["name"] for n in nodes] + [k for h in history for k in h.get("gpu", {})]:
        if k not in seen:
            seen.add(k)
            names.append(k)
    return names


def trend_colors(nodes, history):
    return {k: f"var(--{TREND_COLORS[i % len(TREND_COLORS)]})" for i, k in enumerate(trend_names(nodes, history))}


def trend_dash(i):
    return TREND_DASH[i % len(TREND_DASH)]


def trend_paths(history, colors, now):
    """SVG elements for the last TREND_MIN minutes: one line per node, a dot per sample."""
    out = []
    for i, (name, color) in enumerate(colors.items()):
        pts = []
        for h in history:
            v = (h.get("gpu") or {}).get(name)
            if v is None:
                continue
            mins = (now - datetime.datetime.fromisoformat(h["at"])).total_seconds() / 60
            if 0 <= mins <= TREND_MIN:
                pts.append((mins, max(0, min(100, v)), h["at"]))
        if not pts:
            continue
        d_, prev = [], None
        for mins, v, _ in pts:
            x, y = 600 * (TREND_MIN - mins) / TREND_MIN, 100 - v
            d_.append(f'{"L" if prev is not None and prev - mins <= TREND_GAP_MIN else "M"}{x:.1f},{y:.1f}')
            prev = mins
        dash = f' stroke-dasharray="{trend_dash(i)}"' if trend_dash(i) else ""
        out.append(f'<path class="tl" data-node="{e(name)}" stroke="{color}"{dash} d="{" ".join(d_)}"/>')
        out += [f'<path class="td" stroke="{color}" d="M{600 * (TREND_MIN - m) / TREND_MIN:.1f},{100 - v:.1f}h0">'
                f'<title>{e(name)} {v:.0f}% at {datetime.datetime.fromisoformat(at).strftime("%H:%M")}</title></path>' for m, v, at in pts]
    return "".join(out)


def _parsed(at):
    try:
        return datetime.datetime.fromisoformat(at) if at else None
    except ValueError:
        return None


def anchor_now(spark, now):
    """Sample decks keep the chart on the newest stored reading. Live decks use wall clock."""
    if not spark.get("sample"):
        return now
    times = [t for t in (_parsed(h.get("at")) for h in spark.get("history") or []) if t]
    times += [t for t in (_parsed(n.get("read_at")) for n in spark.get("nodes") or []) if t]
    return max(times) if times else now


def trends(nodes, history, now=None, sample=False):
    now = now or datetime.datetime.now().astimezone()
    colors = trend_colors(nodes, history)
    lines = trend_paths(history, colors, now)
    grid = "".join(f'<line class="tg" x1="0" x2="600" y1="{y}" y2="{y}"/>' for y in (0, 25, 50, 75, 100))
    dash = lambda i: f' stroke-dasharray="{trend_dash(i)}"' if trend_dash(i) else ""
    legend = "".join(f'<span class="tk"><i style="background:{c}"></i><svg class="tk-l" viewBox="0 0 24 6" aria-hidden="true">'
                     f'<line x1="0" x2="24" y1="3" y2="3" stroke="{c}"{dash(i)}/></svg>{e(k)}</span>'
                     for i, (k, c) in enumerate(colors.items()))
    payload = {"history": history, "colors": colors, "palette": TREND_COLORS, "dash": TREND_DASH}
    if sample:
        payload["sample"] = True
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    yl = "".join(f'<span style="top:{100 - v}%">{v}%</span>' for v in (100, 75, 50, 25, 0))
    return (f'<div class="trends" id="trends"><div class="tr-head"><h3>Trends</h3><span class="tr-pill">GPU Utilization (%)</span>'
            f'<span class="tr-win">Last hour</span></div>'
            f'<div class="tr-plot"><div class="tr-y" aria-hidden="true">{yl}</div>'
            f'<div class="tr-area"><svg class="tr-svg" viewBox="0 0 600 100" preserveAspectRatio="none" role="img" '
            f'aria-label="GPU utilization per node over the last hour">{grid}<g class="tr-lines">{lines}</g></svg>'
            f'<p class="tr-empty"{" hidden" if lines else ""}>Collecting. The chart fills over the next hour.</p></div>'
            f'<span></span><div class="tr-x" aria-hidden="true"><span>1h ago</span><span>45m ago</span><span>30m ago</span><span>15m ago</span><span>Now</span></div></div>'
            f'<div class="tr-legend">{legend}</div>'
            f'<script type="application/json" id="trends-data">{blob}</script></div>')


def render(ctx, now=None):
    s = ctx.data.get("spark") or {}
    now = anchor_now(s, now or datetime.datetime.now().astimezone())
    nodes = s.get("nodes") or []
    live = [n for n in nodes if node_state(n, now) == "online"]
    summary = ""
    if live:
        avg = [n["gpu_util_pct"] for n in live if n.get("gpu_util_pct") is not None]
        used = sum(n.get("mem_used_bytes") or 0 for n in live)
        tot = sum(n.get("mem_total_bytes") or 0 for n in live)
        summary = (f'<p class="csum">GPU {sum(avg) / len(avg):.0f}% avg' if avg else '<p class="csum">GPU n/a') + \
                  (f' · System memory {gb(used)} used of {gb(tot)} cluster total</p>' if tot else '</p>')
    rows_ = "".join(node_row(n, now) for n in nodes) or "<p class=muted>No nodes configured.</p>"
    return (f'<section class="spark" aria-labelledby="spark-h"><div class="sp-head"><h2 id="spark-h">{e(s.get("cluster", "Local"))} cluster</h2>'
            f'<span class="online{" none" if not live else ""}"><span class="sdot" aria-hidden="true"></span>{len(live)} online</span>{summary}</div>'
            f'<div class="sp-body">{trends(nodes, s.get("history") or [], now, sample=bool(s.get("sample"))) if nodes else ""}<div class="nodes">{rows_}</div></div></section>')
