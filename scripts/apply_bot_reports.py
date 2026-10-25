#!/usr/bin/env python3
"""Copy .cache/bot-reports.json onto stream rows. Missing file: leave streams alone.

Each report is {agent, area, current, next, at}. Fields are copied as written.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flightdeck.sync import apply_bot_reports, cli_data

if __name__ == "__main__":
    sys.exit(cli_data(apply_bot_reports))
