#!/usr/bin/env bash
# probe_defect22_instrument_sweep.sh — positive + negative leg for the apport hygiene sweep that
# tools/arc_lega_capture.sh gained on 2026-09-13 (builder cron af3e62239ce2).
#
# Property under test: an instrument run leaves the shared apport report path (CRASH_DIR) free of
# FIXTURE-caused reports, while a report that is NOT the fixture survives untouched.
#
# Legs:
#   P1 (GREEN, fixed instrument): plant a fixture report F and a non-fixture report N -> run
#      tools/arc_lega_capture.sh with a non-crashing stub -> F must be gone (moved to the
#      quarantine dir), N must survive, and the run's rc must still be the stub's rc (0).
#   P2 (RED, pre-fix instrument): same planting -> run the instrument as of HEAD (git show) from a
#      temp path -> F must STILL be present, i.e. the property really was absent before the fix.
# Any synthetic report this probe creates is removed at the end (quarantine dir kept — it holds
# only junk by construction).
#
# Run: bash .builder_queue/probe_defect22_instrument_sweep.sh
set -u
cd /home/jericho/projects/zion/projects/visual_audio || exit 9

CRASH_DIR=/var/crash
TAG=faulthandler_segv_fixture.py
Q=/tmp/d22probe_q
OUT=output/d22_instrument_sweep_probe_$(date +%Y%m%d_%H%M%S).txt
: > "$OUT"

plant() { # $1 = label for the synthetic report; fixture report always named *_fixture.crash
  printf 'ProblemType: Crash\nExecutablePath: /usr/bin/python3.12\nProcCmdline: /usr/bin/python3 tests/fixtures/faulthandler_segv_fixture.py -m pytest probes\n' \
    > "$CRASH_DIR/_probe_fixture_report.crash" 2>/dev/null || return 1
  printf 'ProblemType: Crash\nExecutablePath: /usr/bin/python3.12\nProcCmdline: /usr/bin/python3 -m pytest tests/test_gh22_device_driver_abi.py\nStacktraceTop: tests/fixtures/faulthandler_segv_fixture.py (body mention only)\n' \
    > "$CRASH_DIR/_probe_nonfixture_report.crash" 2>/dev/null || return 1
  return 0
}

cleanup() { rm -f "$CRASH_DIR/_probe_fixture_report.crash" "$CRASH_DIR/_probe_nonfixture_report.crash"; }
trap cleanup EXIT

if ! plant; then
  echo "PROBE UNDECIDED: cannot write to $CRASH_DIR (permission) — leg not decidable here" | tee -a "$OUT"
  exit 3
fi

STUB=$(mktemp /tmp/d22probe_stub.XXXXXX.sh)
# Mirror the gate's stub shape (gate_arc_lega_capture.sh:39-46): invoked with `-m ...` it is the
# inferior; invoked with `- <args>` it IS the parse step (exec python3). A stub that ignored the
# parse invocation made the instrument exit 2 ("sidecar was not written") — correct instrument
# behaviour, wrong probe.
cat > "$STUB" <<'STUBEOF'
#!/usr/bin/env bash
if [ "${1:-}" = "-m" ]; then
  echo "probe stub: no crash"
  exit 0
fi
exec /usr/bin/python3 "$@"
STUBEOF
chmod +x "$STUB"
PREFIX_INSTR=$(mktemp /tmp/d22probe_prefix.XXXXXX.sh)
git show HEAD:tools/arc_lega_capture.sh > "$PREFIX_INSTR" 2>/dev/null || true

overall=0

# ---------------------------------------------------------------- P1: fixed instrument
echo "== P1 (fixed instrument): fixture report must be swept, non-fixture must survive ==" | tee -a "$OUT"
rm -rf "$Q"; mkdir -p "$Q"
PY="$STUB" QUARANTINE_DIR="$Q" OUTDIR=/tmp/d22probe_out timeout 120 bash tools/arc_lega_capture.sh > /tmp/d22probe_p1.out 2>&1
P1_RC=$?
FIX_LEFT=0; NONFIX_LEFT=0
[ -f "$CRASH_DIR/_probe_fixture_report.crash" ] && FIX_LEFT=1
[ -f "$CRASH_DIR/_probe_nonfixture_report.crash" ] && NONFIX_LEFT=1
P1_MOVED=$(ls "$Q" 2>/dev/null | wc -l)
echo "   instrument rc=${P1_RC} (stub exits 0 -> expect 0)" | tee -a "$OUT"
grep -a "apport path:" /tmp/d22probe_p1.out | sed 's/^/   /' | tee -a "$OUT"
echo "   fixture report left in $CRASH_DIR: ${FIX_LEFT} (expect 0)" | tee -a "$OUT"
echo "   non-fixture report left in $CRASH_DIR: ${NONFIX_LEFT} (expect 1)" | tee -a "$OUT"
echo "   reports moved to quarantine: ${P1_MOVED} (expect >=1)" | tee -a "$OUT"
if [ "$P1_RC" -eq 0 ] && [ "$FIX_LEFT" -eq 0 ] && [ "$NONFIX_LEFT" -eq 1 ] && [ "$P1_MOVED" -ge 1 ]; then
  echo "   P1 PASS" | tee -a "$OUT"
else
  echo "   P1 FAIL" | tee -a "$OUT"; overall=1
fi

# ---------------------------------------------------------------- P2: pre-fix instrument
echo "== P2 (pre-fix instrument @HEAD content): the fixture report must SURVIVE (falsifier) ==" | tee -a "$OUT"
cleanup; plant || true
PY="$STUB" OUTDIR=/tmp/d22probe_prefix_out timeout 120 bash "$PREFIX_INSTR" > /tmp/d22probe_p2.out 2>&1
P2_RC=$?
FIX_LEFT2=0; NONFIX_LEFT2=0
[ -f "$CRASH_DIR/_probe_fixture_report.crash" ] && FIX_LEFT2=1
[ -f "$CRASH_DIR/_probe_nonfixture_report.crash" ] && NONFIX_LEFT2=1
echo "   pre-fix instrument rc=${P2_RC}" | tee -a "$OUT"
echo "   fixture report left in $CRASH_DIR: ${FIX_LEFT2} (expect 1 — proves the property was absent)" | tee -a "$OUT"
echo "   non-fixture report left in $CRASH_DIR: ${NONFIX_LEFT2} (expect 1)" | tee -a "$OUT"
if [ "$FIX_LEFT2" -eq 1 ]; then
  echo "   P2 RED observed (property absent pre-fix, as required)" | tee -a "$OUT"
else
  echo "   P2 VACUOUS: the pre-fix instrument also cleared the fixture report — probe proves nothing" | tee -a "$OUT"; overall=1
fi

echo "== VERDICT: $([ "$overall" -eq 0 ] && echo PROBE PASS || echo PROBE FAIL) ==" | tee -a "$OUT"
echo "(transcript: $OUT)"
exit "$overall"
