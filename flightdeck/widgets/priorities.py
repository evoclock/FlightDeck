"""`priorities.list`: per-stream focus (data.json `priorities` = [{stream, area, items: [{text, state}]}])."""
from flightdeck.common import colors, e, pane, tag

PRI_STATES = {"done": "Done", "current": "Now", "next": "Next", "blocked": "Blocked"}


def body(ps, B):
    out = []
    for p in ps:
        items = "".join(f'<li class="pi p-{e(i["state"] if i.get("state") in PRI_STATES else "next")}">'
                        f'<span class="pm">{PRI_STATES.get(i.get("state"), "Next")}</span><span class="t">{e(i["text"])}</span></li>'
                        for i in p.get("items", []))
        out.append(f'<div class="pri" data-stream="{e(p["stream"])}"><div class="srow">{tag(p["stream"], B)}'
                   f'<span class="strong">{e(p.get("area", ""))}</span></div><ol class="plist">{items}</ol></div>')
    return "".join(out) or '<p class="muted">No priorities set.</p>'


def badge(ps):
    now = sum(1 for p in ps for i in p.get("items", []) if i.get("state") == "current")
    blk = sum(1 for p in ps for i in p.get("items", []) if i.get("state") == "blocked")
    return f"{len(ps)} streams · {now} now" + (f" · {blk} blocked" if blk else "")


def render(ctx):
    ps = ctx.data.get('priorities') or []
    return pane("priorities", "Priorities", badge(ps), body(ps, colors(ctx, 'bot_colors')))
