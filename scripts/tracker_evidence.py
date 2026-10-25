#!/usr/bin/env python3
"""Log open-PR and in-flight counts. Exit 2 when a present cache has gaps.

No .cache/prs.json and no .cache/repos.json: print offline and exit 0.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flightdeck.sync import main_evidence

if __name__ == "__main__":
    sys.exit(main_evidence())
