"""`streams.table`: one row per agent stream (data.json `streams` = [[bot, project, now, waiting], ...])."""
from flightdeck.common import colors, e, pane, prose_html, rows, tag, wait_cls

KEYS = ('bot', 'project', 'now', 'waiting')


def expand_semicolon_facts(text):
    """Turn a single semicolon-joined fact line into one markdown bullet per fact.

    Pre-as_bullets data looks like "- a; b; c." or a two-action waiting line
    "Review the draft; then merge it." Leave real multi-bullet text and
    ordinary one-clause sentences alone.
    """
    text = text if isinstance(text, str) else ""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) != 1 or lines[0].count("; ") < 1:
        return text
    raw = lines[0]
    prefixed = raw.lstrip().startswith("- ")
    body = raw.lstrip()[2:].strip() if prefixed else raw.strip()
    parts = [part.strip() for part in body.split("; ") if part.strip()]
    if len(parts) < 2:
        return text
    return "\n".join(f"- {part}" for part in parts)


def stream_text(value):
    """Render markdown bullet lists as <ul>/<li>; leave plain sentences escaped."""
    text = expand_semicolon_facts(value if isinstance(value, str) else "")
    if any(line.lstrip().startswith("- ") for line in text.splitlines()):
        return prose_html(text)
    return e(text)


def render(ctx):
    B = colors(ctx, 'bot_colors')
    rs = rows(ctx.data.get('streams'), KEYS)
    body = "".join(
        f'<li class="item"><div class="srow">{tag(b, B)}<span class="strong">{e(p)}</span></div>'
        f'<div class="now">{stream_text(n)}</div>'
        f'<div class="st {wait_cls(w)}">Waiting on you: {stream_text(w)}</div></li>'
        for b, p, n, w in rs)
    need = sum(1 for r in rs if wait_cls(r[3]) == "you")
    badge = f"{len(rs)} bots" + (f" · {need} need you" if need else "")
    return pane("streams", "Streams", badge,
                f'<ul class="list">{body}</ul>' if rs else '<p class="muted">No active streams.</p>')
