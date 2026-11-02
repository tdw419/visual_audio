#!/usr/bin/env bash
# h6 e2e v1 — the ONE command: poster -> SAM segments -> glyph decode ->
# kernel boots -> serial log. Boot leg is the frozen h1 BOOT_SMOKE gate
# (bounded 20M-step smoke, ~90s). NEVER raise BOOT_SMOKE_MAX_STEPS here:
# the full 1.4B-step boot is a MANUAL DAY-MARKER.
#
# Artifacts land in $E2E_OUT_DIR (default: a fresh /tmp dir): serial.log,
# summary.json. Exit 0 = both stages green.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../../.. && pwd)"
PY="$REPO_ROOT/venv/bin/python"
[ -x "$PY" ] || { echo "FATAL: venv python missing: $PY" >&2; exit 2; }

OUT_DIR="${E2E_OUT_DIR:-$(mktemp -d /tmp/hackathon_e2e_out.XXXX)}"
mkdir -p "$OUT_DIR"

cd "$REPO_ROOT"
"$PY" -m hackathon.demo.e2e --out-dir "$OUT_DIR"
