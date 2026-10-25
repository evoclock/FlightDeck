#!/usr/bin/env python3
"""Apply tracker responses: settle decisions, add settled rows, tick steps.

KV when CLOUDFLARE_API_TOKEN plus account id, namespace id, and key are set.
Otherwise .cache/responses.json. Neither: exit 0 and leave data.json alone.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flightdeck.sync import cli_data, reconcile_responses

if __name__ == "__main__":
    sys.exit(cli_data(reconcile_responses))
