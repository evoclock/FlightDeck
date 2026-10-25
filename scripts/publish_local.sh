#!/usr/bin/env bash
# Render the scrubbed demo to a folder of static files. Default: dist/local/index.html.
# The page is self-contained. assets/ is copied beside it for reference.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
if [[ $# -ge 1 ]]; then
  case "$1" in
    /*) OUT=$1 ;;
    *) OUT=$PWD/$1 ;;
  esac
else
  OUT=$ROOT/dist/local
fi
cd "$ROOT"
mkdir -p "$OUT"
python3 -m flightdeck.render \
  "$ROOT/examples/demo/config.json" \
  "$ROOT/examples/demo/data.json" \
  "$OUT/index.html"
rm -rf "$OUT/assets"
cp -R "$ROOT/examples/demo/assets" "$OUT/assets"
echo "Local build at $OUT"
