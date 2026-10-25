"""`steps.checklist`: human action items, open then done, each with a tick box."""
from flightdeck.common import e, item_id, linkify, pane, tick


def step(s):
    cls = "done" if s.get("done") else "todo"
    meta = s.get("meta", "")
    mcls = "blocks" if "block" in meta else ""
    i = e(item_id("step", s))
    return (f'<li class="{cls}" data-kind="step" data-id="{i}" data-done="{str(bool(s.get("done"))).lower()}">'
            f'{tick(i, s["text"], s.get("done"))}<div class="txt"><span class="t">{linkify(s["text"], s.get("url"))}</span>'
            f'<div class="meta {mcls}">{e(meta)}<span class="when"></span></div></div></li>')


def render(ctx):
    ss = ctx.data.get('steps') or []
    todo = [s for s in ss if not s.get("done")]
    done = [s for s in ss if s.get("done")]
    body = (f'<h3>Open</h3><ul class="steps">{"".join(map(step, todo)) or "<li class=muted>Nothing open.</li>"}</ul>'
            f'<h3>Done</h3><ul class="steps">{"".join(map(step, done))}</ul>')
    return pane("steps", "Your steps", f"{len(todo)} open", body, hot=bool(todo))
