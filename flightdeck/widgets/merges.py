"""`merges.table`: PRs coming to you for merge (data.json `merges` = [[title, repo, bot, state], ...])."""
from flightdeck.common import colors, e, item_id, pane, rows, state_cls, tag, tick

KEYS = ('title', 'repo', 'bot', 'state')


def merge(m, R, B):
    p, r, b, s = m
    i = e(item_id("merge", {"text": f"{p} · {r}"}))
    return (f'<li class="item tickrow" data-kind="merge" data-id="{i}">{tick(i, p)}<div class="txt"><div class="strong t">{e(p)}</div>'
            f'<div class="tags">{tag(r, R)}{tag(b, B)}<span class="st {state_cls(s)}">{e(s)}</span><span class="when"></span></div></div></li>')


def render(ctx):
    R, B = colors(ctx, 'repo_colors'), colors(ctx, 'bot_colors')
    ms = rows(ctx.data.get('merges'), KEYS)
    ready = sum(1 for m in ms if str(m[3]).lower().startswith("ready"))
    note = ctx.data.get('merge_note') or ''
    body = (f'<ul class="list">{"".join(merge(m, R, B) for m in ms)}</ul>' if ms
            else '<p class="muted">No PRs coming to you.</p>') + (f'<p class="note">{e(note)}</p>' if note else '')
    return pane("merges", "Coming to you for merge", f"{len(ms)} PRs · {ready} ready", body)
