#!/usr/bin/env bash
# Test suite. CI runs this exact script; extra arguments go to pytest.
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m pytest "$@"
