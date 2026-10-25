#!/usr/bin/env bash
# Refresh the tracker, then render.
#   ./publish.sh            same as --build
#   ./publish.sh --build    hooks/pre-render.d, then a local HTML file
#   ./publish.sh --deploy   hooks, then a Cloudflare Worker (needs site/site.json)
# The default does not deploy. Do not deploy the public demo Worker from this repo.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")" && pwd)
cd "$ROOT"
mode=build
if [[ $# -gt 1 ]]; then
  echo "usage: ./publish.sh [--build|--deploy]" >&2
  exit 2
fi
if [[ $# -eq 1 ]]; then
  case "$1" in
    --build) mode=build ;;
    --deploy) mode=deploy ;;
    *) echo "usage: ./publish.sh [--build|--deploy]" >&2; exit 2 ;;
  esac
fi
if [[ "$mode" == "deploy" ]]; then
  exec "$ROOT/scripts/publish_cloudflare.sh" --deploy
fi
exec "$ROOT/scripts/publish_local.sh"
