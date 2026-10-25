#!/usr/bin/env python3
"""Write an explicit unique id on every decision and step.

Ids match the renderer: an existing id is kept, otherwise dec- or step- plus a
short hash of the text. Re-running does not change ids that are already unique.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flightdeck.sync import cli_data, pin_ids

if __name__ == "__main__":
    sys.exit(cli_data(pin_ids))
