#!/usr/bin/env bash
set -euo pipefail
cd -- "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
command -v python3 >/dev/null 2>&1 || { echo '需要 Python 3.10+（python3）。' >&2; exit 1; }
exec python3 scripts/publish_github.py "$@"
