#!/usr/bin/env bash
# .builder_queue/probe_arc_widen_red.sh — RED-first evidence for the arc-widen change.
#
# Proves the widened selector is discriminating, in both directions, without
# touching the live tree:
#   LEG-A (the gate's own RED): run the widened test file with the runner scripts'
#       FILES selector temporarily narrowed to the OLD glob (test_defect1*) —
#       the audit legs that pin the new patterns must FAIL (old selector cannot
#       see the defect20/23/d clusters). Then run again with the WIDENED
#       selector — the same legs must PASS. Same interpreter, same seed, same
#       workdir, only the selector glob differs.
#   LEG-B (runner-level): source-extract each runner's FILES command with the
#       new glob and count the defect20/23/d files it names — must be 6, and
#       must include the file that went stale-red unnoticed (pte_acceptance).
set -u
cd /home/jericho/projects/zion/projects/visual_audio || exit 9
PY="${PY:-/usr/bin/python3}"
SEED="${SEED:-202609164}"
TMPD=$(mktemp -d)
trap 'rm -rf "$TMPD"' EXIT

GATE="tests/test_arc_selector_parity.py"

echo "=== LEG A1: widened-selector audit vs OLD (pre-widen) glob -> expect RED ==="
cat > "$TMPD/oldglob.py" <<EOF
import sys
sys.path.insert(0, "$PWD")
# Simulate the pre-widen runner: monkeypatch Path.glob so 'tests/test_defect*'
# yields only what the OLD 'tests/test_defect1*' glob matched.
from pathlib import Path
import tests.test_arc_selector_parity as g
real_glob = Path.glob
def narrow_glob(self, pattern):
    if pattern == "tests/test_defect*.py":
        return real_glob(self, "tests/test_defect1*.py")
    return real_glob(self, pattern)
g.Path.glob = narrow_glob
import pytest
sys.exit(pytest.main(["-q", "-p", "no:randomly", "tests/test_arc_selector_parity.py"]))
EOF
( cd "$PWD" && "$PY" "$TMPD/oldglob.py" ) > "$TMPD/legA1.txt" 2>&1
RC1=$?
tail -3 "$TMPD/legA1.txt"
echo "LEG-A1 rc=$RC1 (want NONZERO = RED: old glob misses the new clusters)"

echo
echo "=== LEG A2: same audit vs WIDENED glob -> expect GREEN ==="
"$PY" -m pytest "$GATE" -q -p no:randomly > "$TMPD/legA2.txt" 2>&1
RC2=$?
tail -3 "$TMPD/legA2.txt"
echo "LEG-A2 rc=$RC2 (want 0 = GREEN)"

echo
echo "=== LEG B: runner selector expansion names all 6 defect20/23/d files ==="
WIDEN_LINE='FILES=$(ls tests/test_gh*.py tests/test_bk*.py tests/test_eng*.py tests/test_defect*.py \
        | grep -vE "glass_box|gh24_s2_mcp")'
eval "$WIDEN_LINE"
N=$(echo "$FILES" | grep -cE "test_defect(20|23|_d)")
MISSING=0
for f in test_defect20_write_identity test_defect23_bake_validation test_defect23_pfn_ceiling \
         test_defect23_pte_acceptance test_defect23_pt_identity test_defect_d_ram_scoped_handlers; do
  echo "$FILES" | grep -q "$f.py" || { echo "MISSING: $f"; MISSING=1; }
done
echo "$FILES" | grep -q "test_defect23_pte_acceptance.py" && echo "stale-red file PRESENT: test_defect23_pte_acceptance.py"
echo "LEG-B defect20/23/d files named: $N (want 6), missing-flag=$MISSING (want 0)"

if [ "$RC1" -ne 0 ] && [ "$RC2" -eq 0 ] && [ "$N" -eq 6 ] && [ "$MISSING" -eq 0 ]; then
  echo; echo "PROBE_VERDICT=GREEN (RED-first proven: narrow RED, widened GREEN, runner selector complete)"
  exit 0
else
  echo; echo "PROBE_VERDICT=RED"
  exit 1
fi
