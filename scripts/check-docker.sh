#!/usr/bin/env bash
# Run lint + tests in a throwaway python:3.14 container, for machines whose
# own Python is older than Home Assistant needs. No ports, no network
# listeners: the container only reads the repo (mounted read-only) and exits.
set -euo pipefail
cd "$(dirname "$0")/.."

image="python:3.14-slim"
exec docker run --rm \
  --label dev-skills.test="${CLAUDE_CODE_SESSION_ID:-proxmox_sensors-check}" \
  -v "$PWD:/src:ro" \
  -w /work \
  "$image" bash -euo pipefail -c '
    cp -a /src/. /work/
    export DEBIAN_FRONTEND=noninteractive PIP_DISABLE_PIP_VERSION_CHECK=1
    apt-get update -qq && apt-get install -y -qq --no-install-recommends shellcheck >/dev/null
    pip install -q -r requirements_test.txt
    bash scripts/lint.sh
    bash scripts/test.sh -q
  '
