#!/usr/bin/env python3
"""Steps for ready and green PRs. Drafts stay off the list.

Also ticks an install step when .cache/omb-install.json has a version, and
holds a configured guard until .cache/omb-releases.json has a non-draft release.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flightdeck.sync import cli_data, reconcile_steps_evidence

if __name__ == "__main__":
    sys.exit(cli_data(reconcile_steps_evidence))
