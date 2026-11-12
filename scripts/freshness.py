#!/usr/bin/env python3
"""Advisory per-pane evidence freshness. Missing data skips; diagnostics never block publish."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flightdeck.freshness import main

if __name__ == "__main__":
    sys.exit(main())
