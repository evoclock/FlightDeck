"""Count GitHub activity for the `activity.github` widget: data.json `activity` + `activity_weekly`.

Stdlib only, read-only on GitHub (search API, GET). Two windows, same three numbers:
  activity         last hour:  commits, prs_opened, prs_merged
  activity_weekly  since the latest Friday 17:00 in FLIGHTDECK_TZ (default Europe/London)
Commits come from commit search (default branches only); PRs from issue search.

Owner: FLIGHTDECK_GH_OWNER (no default). Unset: nothing is fetched or written (the demo skips this).
Token: GITHUB_TOKEN or GH_TOKEN from the environment only (never read from a file, never printed).
No token, or GitHub refuses: sections never collected get zeros and a note; collected sections are kept.
A failed fetch exits 2.

    FLIGHTDECK_GH_OWNER=you GITHUB_TOKEN=... python3 -m collectors.activity --data path/to/data.json
"""
import argparse
import datetime
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

from collectors import data_path, load, save
from flightdeck.common import DEFAULT_TZ, week_start

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

API = "https://api.github.com"
KEYS = ("commits", "prs_opened", "prs_merged")


def zone():
    name = os.environ.get("FLIGHTDECK_TZ") or DEFAULT_TZ
    try:
        return ZoneInfo(name) if ZoneInfo else None
    except Exception:
        return None


def utc(t):
    return t.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def queries(owner, since):
    s = utc(since)
    return {"commits": ("commits", f"user:{owner} committer-date:>={s}"),
            "prs_opened": ("issues", f"user:{owner} is:pr created:>={s}"),
            "prs_merged": ("issues", f"user:{owner} is:pr is:merged merged:>={s}")}


def count(kind, q, token, opener=urllib.request.urlopen):
    accept = "application/vnd.github.cloak-preview+json" if kind == "commits" else "application/vnd.github+json"
    req = urllib.request.Request(f"{API}/search/{kind}?per_page=1&q={urllib.parse.quote(q)}",
                                 headers={"Accept": accept, "Authorization": f"Bearer {token}",
                                          "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "flightdeck-activity"})
    with opener(req, timeout=20) as r:
        return int(json.load(r)["total_count"])


def collect(owner, since, token, opener=urllib.request.urlopen):
    return {k: count(kind, q, token, opener) for k, (kind, q) in queries(owner, since).items()}


def not_collected(window, note, since=None):
    sec = {"window": window, **{k: 0 for k in KEYS}, "at": None, "note": note}
    if since:
        sec["since"] = since.isoformat(timespec="seconds")
    return sec


def fill_missing(d, week, why):
    """Zeros + a note for sections never collected; collected numbers are kept (never invented, never wiped)."""
    note = f"Not collected yet: {why}."
    if not (d.get("activity") or {}).get("at"):
        d["activity"] = not_collected("1h", note)
    if not (d.get("activity_weekly") or {}).get("at"):
        d["activity_weekly"] = not_collected("week", note, week)


def main(argv=None, now=None, opener=urllib.request.urlopen):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", help="data.json to update (default $FLIGHTDECK_DATA or ./data.json)")
    args = ap.parse_args(argv)
    owner = (os.environ.get("FLIGHTDECK_GH_OWNER") or "").strip()
    if not owner:
        print("collectors.activity: FLIGHTDECK_GH_OWNER not set, skipping", file=sys.stderr)
        return 0
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    path = data_path(args.data)
    d = load(path)
    z = zone()
    now = (now or datetime.datetime.now(datetime.timezone.utc))
    now = now.astimezone(z) if z else now.astimezone()
    hour, week = now - datetime.timedelta(hours=1), week_start(now, z)
    status = 0
    if not token:
        fill_missing(d, week, "run collectors.activity with GITHUB_TOKEN set")
        print("collectors.activity: no GITHUB_TOKEN/GH_TOKEN, nothing fetched", file=sys.stderr)
    else:
        try:
            hourly, weekly = collect(owner, hour, token, opener), collect(owner, week, token, opener)
        except (urllib.error.URLError, OSError, ValueError, KeyError) as x:
            why = f"GitHub search failed ({getattr(x, 'code', None) or type(x).__name__})"
            fill_missing(d, week, why)
            print(f"collectors.activity: {why}; kept earlier numbers", file=sys.stderr)
            status = 2
        else:
            at = now.isoformat(timespec="seconds")
            note = f"{owner} repos; commits on default branches"
            d["activity"] = {"window": "1h", **hourly, "at": at, "note": note}
            d["activity_weekly"] = {"window": "week", "since": week.isoformat(timespec="seconds"),
                                    **weekly, "at": at, "note": note}
            print("collectors.activity: 1h", hourly, "week", weekly)
    save(path, d)
    return status


if __name__ == "__main__":
    sys.exit(main())
