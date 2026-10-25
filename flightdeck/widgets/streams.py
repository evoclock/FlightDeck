"""`streams.table`: one row per agent stream (data.json `streams` = [[bot, project, now, waiting], ...])."""
from flightdeck.common import colors, e, pane, rows, tag, wait_cls

KEYS = ('bot', 'project', 'now', 'waiting')


def render(ctx):
    B = colors(ctx, 'bot_colors')
    rs = rows(ctx.data.get('streams'), KEYS)
    body = "".join(
        f'<li class="item"><div class="srow">{tag(b, B)}<span class="strong">{e(p)}</span></div>'
        f'<div class="now">{e(n)}</div><div class="st {wait_cls(w)}">Waiting on you: {e(w)}</div></li>'
        for b, p, n, w in rs)
    need = sum(1 for r in rs if wait_cls(r[3]) == "you")
    badge = f"{len(rs)} bots" + (f" · {need} need you" if need else "")
    return pane("streams", "Streams", badge, f'<ul class="list">{body}</ul>')
