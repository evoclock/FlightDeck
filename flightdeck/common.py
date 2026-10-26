"""Shared HTML helpers for widgets, ported from crew-tracker render.py (stdlib only)."""
import datetime
import hashlib
import html
import re

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

DEFAULT_TZ = 'Europe/London'


def e(s):
    return html.escape(str(s))


_MD_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_BARE_GH = re.compile(r"https://github\.com/[\w.+/~-]+")
NEW_TAB = 'target="_blank" rel="noopener noreferrer"'


def ext_link(url, label=None):
    """An outside link. It opens in a new tab so the tracker stays open."""
    return f'<a href="{e(url)}" {NEW_TAB}>{e(url if label is None else label)}</a>'


def plain_text(s):
    """Prose with [label](url) reduced to its label, for attributes such as aria-label."""
    return _MD_LINK.sub(lambda m: m.group(1), s or "")


def rich_text(s):
    """Escape prose; turn [label](url) and bare github.com URLs into links."""
    s = s or ""
    out, i = [], 0
    while i < len(s):
        m_md = _MD_LINK.search(s, i)
        m_gh = _BARE_GH.search(s, i)
        if m_md and (not m_gh or m_md.start() <= m_gh.start()):
            m, kind = m_md, "md"
        elif m_gh:
            m, kind = m_gh, "bare"
        else:
            out.append(e(s[i:]))
            break
        out.append(e(s[i:m.start()]))
        if kind == "md":
            label, url = m.group(1), m.group(2)
            out.append(ext_link(url, label))
            i = m.end()
        else:
            url = m.group(0).rstrip(".,);]")
            out.append(ext_link(url))
            i = m.start() + len(url)
    return "".join(out)


def prose_html(text):
    """Tracker prose: '- ' lines become a real <ul>, else paragraphs. Links allowed."""
    text = (text or "").strip()
    if not text:
        return ""
    lines_ = [ln.rstrip() for ln in text.splitlines()]
    bullets = [ln[2:].strip() for ln in lines_ if ln.lstrip().startswith("- ")]
    non = [ln for ln in lines_ if ln.strip() and not ln.lstrip().startswith("- ")]
    ul_html = lambda items: '<ul class="prose-list">' + "".join(f"<li>{rich_text(b)}</li>" for b in items if b) + "</ul>"
    if bullets and not non:
        return ul_html(bullets)
    if bullets and len(bullets) >= max(1, len(non)):
        parts, ul = [], []
        for ln in lines_:
            s = ln.strip()
            if s.startswith("- "):
                ul.append(s[2:].strip())
                continue
            if ul:
                parts.append(ul_html(ul))
                ul = []
            if s:
                parts.append(f"<p>{rich_text(s)}</p>")
        if ul:
            parts.append(ul_html(ul))
        return "".join(parts)
    return "<p>" + "<br>".join(rich_text(ln) for ln in lines_ if ln.strip()) + "</p>"


def tag(name, colors):
    c = (colors or {}).get(name, "#5c564f")
    return f'<span class="tag" style="--c:{e(c)}">{e(name)}</span>'


def state_cls(s):
    s = str(s).lower()
    if s.startswith("ready"):
        return "ok"
    if "progress" in s or "building" in s or "pushing" in s:
        return "wait"
    return "later"


def wait_cls(s):
    return "none" if str(s).lower().startswith("nothing") else "you"


def linkify(t, url=None):
    """Prose with its links, then `url` as a trailing link. Every link opens in a new tab."""
    t = rich_text(t)
    if url:
        t += " " + ext_link(url, re.sub(r"^https?://", "", url))
    return t


def item_id(prefix, x):
    """Stable id: explicit `id` in data.json, else a hash of the text. Responses key on this."""
    return x.get("id") or f"{prefix}-{hashlib.sha1(x['text'].encode()).hexdigest()[:10]}"


CHECK = '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 10.5l4 4 8-9"/></svg>'
CROSS = '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M5 5l10 10M15 5L5 15"/></svg>'


def respond(i):
    """Accept / reject / alternative instructions for one decision; the page script keeps the state."""
    return (f'<div class="respond"><div class="choice" role="group" aria-label="Your answer">'
            f'<button type="button" class="act acc" data-act="accepted" aria-pressed="false">{CHECK}Accept</button>'
            f'<button type="button" class="act rej" data-act="rejected" aria-pressed="false">{CROSS}Reject</button></div>'
            f'<details class="alt"><summary>Alternative instructions</summary>'
            f'<label class="sr" for="{i}-c">Alternative instructions</label>'
            f'<textarea id="{i}-c" rows="3" placeholder="What should happen instead?"></textarea>'
            f'<button type="button" class="act send" data-act="comment">Submit</button></details>'
            f'<p class="resp" aria-live="polite" hidden></p></div>')


def tick(i, label, done=False):
    return (f'<label class="hit" for="{i}-t"><input type="checkbox" class="tick" id="{i}-t" '
            f'aria-label="Mark done: {e(plain_text(label))}"{" checked disabled" if done else ""}></label>')


def pane(pid, title, badge, body, hot=False, open_=True):
    return (f'<section class="pane" id="{pid}" data-default="{"open" if open_ else "closed"}">'
            f'<button class="ph" aria-expanded="true" aria-controls="{pid}-b"><span class="chev" aria-hidden="true"></span>'
            f'<span class="pt">{e(title)}</span><span class="badge{" hot" if hot else ""}">{e(badge)}</span></button>'
            f'<div class="pb" id="{pid}-b">{body}</div></section>')


def colors(ctx, key):
    c = (ctx.data or {}).get(key) or {}
    return c if isinstance(c, dict) else {}


def tz(ctx):
    name = (ctx.config or {}).get('timezone') or DEFAULT_TZ
    if ZoneInfo is None:
        return None
    try:
        return ZoneInfo(name)
    except Exception:
        return None


def local_now(zone=None):
    now = datetime.datetime.now(datetime.timezone.utc)
    return now.astimezone(zone) if zone else now.astimezone()


def hm_zone(iso, zone=None):
    """'HH:MM ZZZ' for an ISO timestamp shown in the configured zone (e.g. '14:05 BST')."""
    t = datetime.datetime.fromisoformat(iso)
    if t.tzinfo is not None:
        t = t.astimezone(zone) if zone else t.astimezone()
    return t.strftime('%H:%M') + (f' {t.strftime("%Z")}' if t.tzinfo is not None and t.strftime('%Z') else '')


def week_start(now, zone=None):
    """Most recent Friday 17:00 (wall time in `zone`) at or before `now` (an aware datetime)."""
    local = now.astimezone(zone) if zone else now.astimezone()
    back = (local.weekday() - 4) % 7
    start = local.replace(hour=17, minute=0, second=0, microsecond=0) - datetime.timedelta(days=back)
    if start > local:
        start -= datetime.timedelta(days=7)
    if zone:
        start = start.replace(tzinfo=None).replace(tzinfo=zone)
    return start


def rows(seq, keys):
    """Accept either crew-tracker style lists ([a, b, c, d]) or dicts with `keys`; return tuples."""
    out = []
    for r in seq or []:
        if isinstance(r, dict):
            out.append(tuple(r.get(k, '') for k in keys))
        else:
            r = list(r) + [''] * (len(keys) - len(r))
            out.append(tuple(r[:len(keys)]))
    return out
