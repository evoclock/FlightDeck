"""Host CPU / memory / disk for the `metrics.generic` widget: data.json `metrics`.

Stdlib only. CPU from two /proc/stat samples, memory from /proc/meminfo, disk from os.statvfs.
Anything a host cannot supply (no /proc on macOS/Windows, missing path) is written as pct null with
text n/a and a note, never a made-up number.

    python3 -m collectors.metrics_generic --data path/to/data.json [--disk /] [--title "This machine"]
"""
import argparse
import datetime
import os
import sys
import time
from pathlib import Path

from collectors import data_path, load, refuse_demo_write, save

PROC = Path("/proc")


def cpu_sample(proc=PROC):
    """Jiffies from the aggregate `cpu` line of /proc/stat, or None."""
    try:
        first = (Path(proc) / "stat").read_text().splitlines()[0].split()
    except (OSError, IndexError):
        return None
    if not first or first[0] != "cpu":
        return None
    return tuple(int(x) for x in first[1:])


def cpu_pct(a, b):
    """Busy share between two samples; idle = idle + iowait (fields 3, 4)."""
    if not a or not b:
        return None
    idle = lambda s: s[3] + (s[4] if len(s) > 4 else 0)
    total = sum(b) - sum(a)
    if total <= 0:
        return None
    return round(100.0 * (total - (idle(b) - idle(a))) / total, 1)


def mem(proc=PROC):
    """(pct used, detail) from /proc/meminfo MemTotal / MemAvailable, or (None, None)."""
    try:
        info = {}
        for line in (Path(proc) / "meminfo").read_text().splitlines():
            k, _, v = line.partition(":")
            info[k.strip()] = int(v.split()[0])
        total, avail = info["MemTotal"], info["MemAvailable"]
    except (OSError, KeyError, ValueError, IndexError):
        return None, None
    if total <= 0:
        return None, None
    used = total - avail
    gb = lambda kb: kb / 1024 / 1024
    return round(100.0 * used / total, 1), f"{gb(used):.1f} / {gb(total):.0f} GB"


def disk(path="/"):
    try:
        st = os.statvfs(path)
    except (OSError, AttributeError):
        return None, None
    total = st.f_blocks * st.f_frsize
    if total <= 0:
        return None, None
    used = total - st.f_bfree * st.f_frsize
    gb = lambda b: b / 1024 ** 3
    return round(100.0 * used / total, 1), f"{gb(used):.0f} / {gb(total):.0f} GB"


def collect(proc=PROC, disk_path="/", interval=0.5, title=None):
    a = cpu_sample(proc)
    if a and interval:
        time.sleep(interval)
    c = cpu_pct(a, cpu_sample(proc)) if a else None
    mp, md = mem(proc)
    dp, dd = disk(disk_path)
    items = [{"key": "cpu", "label": "CPU", "pct": c},
             {"key": "mem", "label": "Memory", "pct": mp, "detail": md},
             {"key": "disk", "label": "Disk", "pct": dp, "detail": dd}]
    for i in items:
        if i["pct"] is None:
            i["text"] = "n/a"
        if i.get("detail") is None:
            i.pop("detail", None)
    out = {"title": title or "This machine", "at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
           "items": items}
    missing = [i["label"] for i in items if i["pct"] is None]
    if missing:
        out["note"] = f"{', '.join(missing)} not supported on this host (stdlib reads /proc and statvfs)."
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", help="data.json to update (default $FLIGHTDECK_DATA or ./data.json)")
    ap.add_argument("--disk", default="/", help="filesystem path to measure (default /)")
    ap.add_argument("--title", help='panel title (default "This machine")')
    args = ap.parse_args(argv)
    path = data_path(args.data)
    if refuse_demo_write(path):
        return 2
    d = load(path)
    d["metrics"] = collect(disk_path=args.disk, title=args.title)
    save(path, d)
    print("collectors.metrics_generic:", ", ".join(f'{i["label"]} {i.get("text") or i["pct"]}' for i in d["metrics"]["items"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
