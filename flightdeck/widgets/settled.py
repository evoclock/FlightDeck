"""`settled.list`: what was decided today (data.json `settled` = [{meta, title, detail}])."""
from flightdeck.common import e, pane, prose_html


def render(ctx):
    ss = ctx.data.get('settled') or []
    body = "".join(
        f'<li><span class="time">{e(s.get("meta", ""))}</span><div><div class="strong">{e(s["title"])}</div>'
        f'<div class="muted">{prose_html(s.get("detail", ""))}</div></div></li>' for s in ss)
    return pane("settled", "Settled today", f"{len(ss)}", f'<ul class="settled">{body}</ul>')
