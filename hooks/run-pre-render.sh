#!/usr/bin/env bash
# Run hooks/pre-render.d in lexical order, then log evidence counts.
# A hook that exits non-zero stops the publish. Exit 2 means discovery failed.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
dir="$ROOT/hooks/pre-render.d"
shopt -s nullglob
for hook in "$dir"/*; do
  [[ -f "$hook" ]] || continue
  echo "pre-render: $(basename "$hook")"
  bash "$hook"
done
python3 "$ROOT/scripts/tracker_evidence.py"
