#!/usr/bin/env python3
"""One priorities block per stream. Rebuild items with src "stream". Keep the rest.

Done ladder items stay. Streams that disappeared keep their block.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flightdeck.sync import cli_data, reconcile_priorities

if __name__ == "__main__":
    sys.exit(cli_data(reconcile_priorities))
