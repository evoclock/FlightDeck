"""Copy a cluster reading into data.json `spark` for the `cluster.gpu` widget.

Stdlib only. This does not open SSH and does not invent readings.
Source, first hit wins:
  FLIGHTDECK_SPARK_FILE
  $FLIGHTDECK_CACHE/spark.json or .cache/spark.json
No file, or no data.json: exit 0 and write nothing.
A file without a `nodes` list exits 2 and writes nothing.

    FLIGHTDECK_CLUSTER=spark python3 -m collectors.spark --data path/to/data.json
"""
import argparse
import json
import os
import sys
from pathlib import Path

from collectors import data_path, load, save


def source_path():
    explicit = (os.environ.get("FLIGHTDECK_SPARK_FILE") or "").strip()
    if explicit:
        return Path(explicit)
    cache = Path(os.environ.get("FLIGHTDECK_CACHE") or ".cache")
    return cache / "spark.json"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", help="data.json to update (default $FLIGHTDECK_DATA or ./data.json)")
    args = parser.parse_args(argv)
    src = source_path()
    if not src.is_file():
        print("collectors.spark: no spark cache, skipping", file=sys.stderr)
        return 0
    reading = json.loads(src.read_text(encoding="utf-8"))
    if not isinstance(reading, dict) or not isinstance(reading.get("nodes"), list):
        print("collectors.spark: cache has no nodes list, not writing", file=sys.stderr)
        return 2
    explicit = bool(args.data or os.environ.get("FLIGHTDECK_DATA"))
    path = data_path(args.data)
    if not explicit and not Path(path).is_file():
        print("collectors.spark: no data file, skipping", file=sys.stderr)
        return 0
    doc = load(path)
    doc["spark"] = reading
    save(path, doc)
    print(f"collectors.spark: {len(reading['nodes'])} nodes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
