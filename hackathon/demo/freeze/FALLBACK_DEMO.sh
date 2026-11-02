#!/usr/bin/env bash
# h7 fallback demo — the classical (non-SAM) decode path, standalone.
# Demo-day insurance: if the live SAM call is down or low-confidence, the
# h4 pixel fallback recovers the payload from poster pixels alone. Offline,
# deterministic, wall-time checked against the h6 decode budget (<= 5s).
#
# Artifacts land in $FALLBACK_OUT_DIR (default: a fresh /tmp dir):
# summary.json. Exit 0 = fallback green.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../../.. && pwd)"
PY="$REPO_ROOT/venv/bin/python"
[ -x "$PY" ] || { echo "FATAL: venv python missing: $PY" >&2; exit 2; }

OUT_DIR="${FALLBACK_OUT_DIR:-$(mktemp -d /tmp/hackathon_fallback_out.XXXX)}"
mkdir -p "$OUT_DIR"

cd "$REPO_ROOT"
"$PY" -m hackathon.demo.fallback_demo --out-dir "$OUT_DIR"
