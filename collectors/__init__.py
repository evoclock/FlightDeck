"""Stdlib collectors that write sections of data.json. Run as `python3 -m collectors.<name> --data path`."""
import json
import os
from pathlib import Path


def load(path):
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else {}


def save(path, d):
    """Atomic write: temp file in the same directory, then os.replace."""
    p = Path(path)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, p)


def data_path(arg=None):
    return arg or os.environ.get("FLIGHTDECK_DATA") or "data.json"
