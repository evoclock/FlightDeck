"""`activity.github`: commits / PRs opened / PRs merged, last hour beside this week.

data.json `activity` (last hour) and `activity_weekly` (since the latest Friday 17:00 in config `timezone`,
default Europe/London), each {window, commits, prs_opened, prs_merged, at, note}; weekly adds `since`.
Collectors fill these; the widget only prints. Missing, or a weekly count from an earlier week: zeros + Collecting.
"""
import datetime

from flightdeck.common import e, hm_zone, local_now, tz, week_start

ACTIVITY = (("commits", "Commits"), ("prs_opened", "PRs opened"), ("prs_merged", "PRs merged"))


def activity_rows(a, w):
    num = lambda x, k: int(x.get(k) or 0)
    return "".join(f'<tr class="ac" data-k="{k}"><th scope="row">{l}</th><td class="av" data-window="1h">{num(a, k)}</td>'
                   f'<td class="av" data-window="week">{num(w, k)}</td></tr>' for k, l in ACTIVITY)


def render(ctx, now=None):
    zone = tz(ctx)
    a = ctx.data.get("activity") or {}
    at = a.get("at")
    when = f'Refreshed {hm_zone(at, zone)}' if at else "Collecting…"
    note = f'<p class="anote">{e(a["note"])}</p>' if a.get("note") else ""
    start = week_start(now or local_now(zone), zone)
    w = ctx.data.get("activity_weekly") or {}
    try:
        current = bool(w.get("at")) and datetime.datetime.fromisoformat(w.get("since") or "") == start
    except ValueError:
        current = False
    if not current:
        w = {}
    wwhen = f'Refreshed {hm_zone(w["at"], zone).split(" ")[0]}' if w else "Collecting…"
    if w and at and wwhen in when:
        wwhen = ""   # same collection run as the hourly row: say the time once
    win = e(a.get("window") or "1h")
    return (f'<section class="activity" aria-labelledby="act-h"><h2 id="act-h">Activity</h2>'
            f'<table class="a-tab"><thead><tr><th scope="col"><span class="sr">Metric</span></th><th scope="col">Last {win}</th>'
            f'<th scope="col">This week</th></tr></thead><tbody>{activity_rows(a, w)}</tbody></table>'
            f'<div class="a-foot"><p class="a-meta">Last {win} · {e(when)}</p>'
            f'<p class="a-meta a-week" data-since="{e(start.isoformat(timespec="seconds"))}">Week since Fri {start.day} {start.strftime("%b")} 17:00'
            f'{" · " + e(wwhen) if wwhen else ""}</p>'
            f'{note}</div></section>')
