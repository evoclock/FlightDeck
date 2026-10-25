#!/usr/bin/env python3
"""Refresh .cache/prs.json, prs-closed.json, repos.json, and optional release evidence.

Owner: FLIGHTDECK_GH_OWNER or config/sync.json. Unset: exit 0, write nothing.
Evidence: gh, else a GitHub token, else unauthenticated REST for public_repos only.
A configured owner that cannot be listed exits 2. Tokens are never printed.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flightdeck.sync import main_refresh

if __name__ == "__main__":
    sys.exit(main_refresh())
