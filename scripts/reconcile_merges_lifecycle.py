#!/usr/bin/env python3
"""Drop merges rows for PRs in .cache/prs-closed.json. Tick steps. Settle decisions.

No closed cache: exit 0 and leave data.json alone.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flightdeck.sync import cli_data, reconcile_merges_lifecycle

if __name__ == "__main__":
    sys.exit(cli_data(reconcile_merges_lifecycle))
