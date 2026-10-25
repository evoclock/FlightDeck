#!/usr/bin/env python3
"""Rebuild merges from open PRs and in-flight repos. Update the primary stream.

Needs .cache/prs.json and .cache/repos.json. Missing caches with no owner: exit 0.
Missing caches with an owner, or only one of the two files: exit 2 and do not write.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flightdeck.sync import cli_data, reconcile_inflight

if __name__ == "__main__":
    sys.exit(cli_data(reconcile_inflight))
