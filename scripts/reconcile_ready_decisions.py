#!/usr/bin/env python3
"""Open a decision for each ready merge whose repo is public on repos.json.

Public = private=false on the live repos cache (not a frozen name set).
An empty list skips. One missing name means that repo gets no decision.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flightdeck.sync import cli_data, reconcile_ready_decisions

if __name__ == "__main__":
    sys.exit(cli_data(reconcile_ready_decisions))
