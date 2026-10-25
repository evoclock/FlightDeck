#!/usr/bin/env bash
# Fail fast when the mac-mini agent does not have Python 3.11+.
set -euo pipefail
command -v python3 >/dev/null
python3 -c 'import sys; v=sys.version_info; raise SystemExit(0 if v>=(3,11) else "python3 %d.%d.%d is below 3.11" % v[:3])'
echo "python3 $(python3 -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])')"
