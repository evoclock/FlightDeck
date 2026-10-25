"""Stdlib collectors that write sections of data.json. Run as `python3 -m collectors.<name> --data path`."""
import json
import os
import sys
from pathlib import Path

# The public demo is a static illustration. Collectors and sync must not overwrite it.
DEMO_DATA = Path(__file__).resolve().parents[1] / "examples" / "demo" / "data.json"


class DemoDataError(RuntimeError):
    """Raised when a writer targets the shipped public demo file."""


def is_shipped_demo(path):
    if not path:
        return False
    try:
        return Path(path).expanduser().resolve() == DEMO_DATA
    except OSError:
        return False


def refuse_demo_write(path):
    """True when path is the shipped demo. Callers must not fetch or write."""
    if not is_shipped_demo(path):
        return False
    print(
        "Refusing to update examples/demo/data.json. The public demo is a static illustration.",
        file=sys.stderr,
    )
    return True


def load(path):
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else {}


def save(path, d):
    """Atomic write: temp file in the same directory, then os.replace."""
    if is_shipped_demo(path):
        raise DemoDataError(
            "Refusing to write examples/demo/data.json. The public demo is a static illustration."
        )
    p = Path(path)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, p)


def data_path(arg=None):
    return arg or os.environ.get("FLIGHTDECK_DATA") or "data.json"
