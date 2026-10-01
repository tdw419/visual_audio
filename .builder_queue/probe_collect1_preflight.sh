#!/usr/bin/env bash
# probe_collect1_preflight.sh — RED evidence for SUITE-COLLECT-1, pre-change.
#
# Claim under test: tools/suite_iso_harness.py folds a pre-collection hang into TIMEOUT.
# Expected (pre-fix, RED): verdict TIMEOUT at the FULL budget, coll=0, last_line
# "TIMEOUT: exceeded <budget>s budget" — indistinguishable from an execution overrun.
# Expected (post-fix, GREEN): verdict COLLECT-HANG at ~--import-grace, well under the budget.
#
# Usage: bash .builder_queue/probe_collect1_preflight.sh [BUDGET] [GRACE]
set -uo pipefail
cd "$(dirname "$0")/.."
BUDGET="${1:-12}"
GRACE="${2:-3}"
T="$(mktemp -d)"
printf 'import time\ntime.sleep(30)\n\n\ndef test_ok():\n    assert True\n' > "$T/test_slow_import.py"
echo "probe dir: $T  budget=${BUDGET}s grace=${GRACE}s"
/usr/bin/python3 tools/suite_iso_harness.py "$T" -t "$BUDGET" -w 1 ${GRACE:+--import-grace "$GRACE"} --json > "$T/out.json" 2>&1
/usr/bin/python3 - "$T/out.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
r = d[0]
print("VERDICT=%s dur=%.1f coll=%s" % (r["verdict"], r["duration_s"], r["counts"]))
print("LAST=%s" % r.get("last_line", "")[:90])
print("pre-fix RED expected: VERDICT=TIMEOUT dur~=budget; post-fix GREEN expected: VERDICT=COLLECT-HANG dur~=grace")
PY
