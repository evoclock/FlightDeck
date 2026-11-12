#!/usr/bin/env python3
"""Merge read-only tracker sidecars into local evidence caches before reconciliation."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flightdeck import sync as ev


SOURCES = (("bot-reports.json", "reports", "agent", "at"),
           ("responses.json", "responses", "id", "timestamp"))


def warn(path, reason):
    print(f"merge_sidecars: WARNING {path}: {reason}", file=sys.stderr)


def rows(path, key, identity, time_key):
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        warn(path, type(exc).__name__)
        return None, None
    if isinstance(doc, list):
        items = doc
    elif isinstance(doc, dict) and isinstance(doc.get(key), list):
        items = doc[key]
    else:
        warn(path, f"expected a list or object with a {key} list")
        return None, None
    valid = []
    for index, row in enumerate(items):
        if (not isinstance(row, dict) or not isinstance(row.get(identity), str)
                or not row[identity].strip() or not ev.parse_time(row.get(time_key))
                or (key == "reports" and
                    any(not isinstance(row.get(field), str) for field in ("area", "current", "next")))
                or (key == "responses" and
                    (row.get("value") not in ("accepted", "rejected", "comment", "done", "undone")
                     or row.get("type") not in ("decision", "step")))):
            warn(path, f"invalid {key} row {index}")
            continue
        valid.append(row)
    return doc, valid


def merge(current, incoming, identity, time_key):
    # Keep insertion order and break equal-time ties in favor of the cached row.
    by_id = {}
    for row in current + incoming:
        rid = row[identity]
        old = by_id.get(rid)
        if old is None or (row.get("value") == "undone" and old.get("value") != "undone"):
            by_id[rid] = row
        elif old.get("value") != "undone" and row.get("value") != "undone":
            if ev.parse_time(row[time_key]) > ev.parse_time(old[time_key]):
                by_id[rid] = row
    return list(by_id.values())


def main():
    configured = os.environ.get("CREW_TRACKER_SIDECAR_DIRS", "")
    dirs = [Path(part) for part in configured.split(":") if part]
    dirs = [path for path in dirs if path.is_dir()]
    if not dirs:
        print("merge_sidecars: no sidecar directories, skipping")
        return 0
    cache = Path(ev.load_config()["cache_dir"])
    for filename, key, identity, time_key in SOURCES:
        target = cache / filename
        pending = []
        for directory in dirs:
            source = directory / filename
            if not source.exists():
                continue
            if source.resolve() == target.resolve():
                warn(source, "input is the cache; skipping")
                continue
            _, items = rows(source, key, identity, time_key)
            if items:
                pending.extend(items)
        if not pending:
            continue
        if target.exists():
            doc, existing = rows(target, key, identity, time_key)
            if doc is None:
                continue  # Never replace an unreadable cache.
            original = doc if isinstance(doc, list) else doc[key]
            if len(existing) != len(original):
                warn(target, "invalid cached rows; leaving cache unchanged")
                continue
        else:
            doc, existing = {key: []}, []
        combined = merge(existing, pending, identity, time_key)
        updated = combined if isinstance(doc, list) else {**doc, key: combined}
        if updated != doc:
            ev.write_json(target, updated)
        print(f"merge_sidecars: {filename}: {len(pending)} sidecar rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
