"""`decisions.cards`: open decisions first, each with Accept / Reject / Alternative instructions."""
from flightdeck.common import e, item_id, pane, prose_html, respond, rich_text


def card(x):
    lab = "Open" if x["state"] == "open" else "Settled"
    i = e(item_id("dec", x))
    extra = ""
    if x.get("recommendation"):
        extra += f'<p class="rec"><span class="strong">Recommendation:</span> {rich_text(x["recommendation"])}</p>'
    if x.get("why"):
        extra += f'<p class="why"><span class="strong">Why:</span> {rich_text(x["why"])}</p>'
    return (f'<article class="dec {e(x["state"])}" data-kind="decision" data-id="{i}" data-state="{e(x["state"])}">'
            f'<div class="dec-head"><span class="pill">{lab}</span>'
            f'<div class="strong dec-title">{e(x.get("title") or "Decision")}</div>'
            f'<div class="meta">{e(x.get("meta") or "")}</div></div>'
            f'<div class="dec-body">{prose_html(x["text"])}{extra}</div>{respond(i)}</article>')


def render(ctx):
    ds = ctx.data.get('decisions') or []
    opened = [x for x in ds if x["state"] == "open"]
    body = "".join(card(x) for x in sorted(ds, key=lambda x: x["state"] != "open")) or '<p class="muted">None open.</p>'
    settled = len(ds) - len(opened)
    badge = f"{len(opened)} open" + (f" · {settled} settled" if settled else "")
    return pane("decisions", "Decisions", badge, body, hot=bool(opened))
