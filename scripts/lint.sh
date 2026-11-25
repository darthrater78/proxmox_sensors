#!/usr/bin/env bash
# Static checks. CI runs this exact script; run it locally before pushing.
set -euo pipefail
cd "$(dirname "$0")/.."

ruff check .
python3 -m py_compile scripts/pve-sensors-api.py

if ! command -v shellcheck >/dev/null 2>&1; then
  echo "shellcheck is not installed (apt install shellcheck), or use scripts/check-docker.sh" >&2
  exit 1
fi
shellcheck --severity=warning scripts/*.sh
