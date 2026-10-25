#!/usr/bin/env bash
# Dry-run: render the demo and embed it in a Worker bundle under site/dist.
# Deploy: scripts/publish_cloudflare.sh --deploy
#   requires site/site.json (gitignored) with real ids, plus npx and a Cloudflare API token.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

DEPLOY=0
if [[ "${1:-}" == "--deploy" ]]; then
  DEPLOY=1
elif [[ -n "${1:-}" ]]; then
  echo "usage: scripts/publish_cloudflare.sh [--deploy]" >&2
  exit 2
fi

"$ROOT/scripts/publish_local.sh" "$ROOT/dist/local"

if [[ "$DEPLOY" == 1 ]]; then
  SITE="$ROOT/site/site.json"
  if [[ ! -f "$SITE" ]]; then
    echo "Refusing to deploy: copy site/site.example.json to site/site.json and replace the placeholders. site.json is gitignored." >&2
    exit 1
  fi
  python3 - "$SITE" <<'PY'
import json, sys
cfg = json.load(open(sys.argv[1], encoding="utf-8"))

def placeholder(value):
    text = "" if value is None else str(value)
    return (not text) or text.endswith("_ID") or text.startswith("TEAM.") or "example.com" in text or "example.workers.dev" in text

bad = [key for key in ("account_id", "zone_id", "access_aud", "hostname", "access_team_domain") if placeholder(cfg.get(key))]
emails = cfg.get("allowed_emails") or []
if not emails or any(placeholder(item) for item in emails):
    bad.append("allowed_emails")
for key in ("responses_kv_id", "spark_kv_id"):
    if key in cfg and cfg[key] and placeholder(cfg[key]):
        bad.append(key)
if bad:
    sys.exit("Refusing to deploy: site/site.json still has placeholders in " + ", ".join(bad))
PY
else
  SITE="$ROOT/site/site.example.json"
fi

python3 "$ROOT/site/build.py" \
  --html "$ROOT/dist/local/index.html" \
  --site "$SITE" \
  --out "$ROOT/site/dist"

if [[ "$DEPLOY" == 1 ]]; then
  if ! command -v npx >/dev/null 2>&1; then
    echo "npx is required to deploy. The Worker bundle is at $ROOT/site/dist." >&2
    exit 1
  fi
  npx --yes wrangler@4 deploy --config "$ROOT/site/dist/wrangler.json"
fi

echo "Cloudflare bundle at $ROOT/site/dist"
