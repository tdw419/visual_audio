#!/usr/bin/env bash
# tools/gate_L6_env_skip.sh — harness gate for DEFECT-22d L6 apport falsifier flake repair.
#
# Legs:
#   H0 premise                 pinned revision ecef274 contains vacuous FAIL and no L6_CRASHER_FIXTURE
#   H1 RED-first               pre-fix gate under stub exits 1 (vacuous FAIL); working tree prints L6b-alt PASS + L6 ENV NOTE
#   H2 discrimination preserved neutered sweep fails on stub-forced path (L6b-alt FAIL)
#   H3 real path discriminates real fixture prints L6b RED observed or L6 ENV NOTE (never silent)
#   H4 no-regression/hygiene   capture, naming, telemetry, record_survival gates pass; /var/crash 0 reports; no tracked pollution
#
# Usage: bash tools/gate_L6_env_skip.sh (exit 0 = all pass, 1 = leg failed, 2 = setup failure)
set -u

REPO="/home/jericho/projects/zion/projects/visual_audio"
cd "$REPO" || exit 2

PINNED_REV="ecef274"
TMP="$(mktemp -d /tmp/gate_L6_env_skip.XXXXXX)" || exit 2
FAIL=0

cleanup() {
  rm -rf "$TMP"
  # Quarantine/sweep any stray fixture reports that might remain
  rm -f /var/crash/*faulthandler_segv_fixture*.crash /var/crash/*l6_no_crash_stub*.crash 2>/dev/null || true
}
trap cleanup EXIT

echo "== gate: L6 environment skip harness (DEFECT-22d) =="

check_crash_and_tracked_hygiene() {
  local leg="$1"
  local crash_count
  crash_count=$(ls /var/crash/*.crash 2>/dev/null | wc -l)
  if [ "$crash_count" -ne 0 ]; then
    echo "   ${leg} FAIL: /var/crash held ${crash_count} report(s) after leg"
    ls -l /var/crash/*.crash
    FAIL=1
  fi
  # Tracked modification check: only tools/gate_arc_lega_capture.sh may be modified
  local diff_files
  diff_files=$(git status --short -uno | awk '{print $2}')
  for f in $diff_files; do
    if [ "$f" != "tools/gate_arc_lega_capture.sh" ]; then
      echo "   ${leg} FAIL: unexpected tracked file modified: $f"
      FAIL=1
    fi
  done
}

# ---------------------------------------------------------------- H0 premise
echo "-- H0 premise: pinned revision ${PINNED_REV} gate has vacuous FAIL and no L6_CRASHER_FIXTURE"
git show "${PINNED_REV}:tools/gate_arc_lega_capture.sh" > "$TMP/pinned_gate.sh" 2>/dev/null || {
  echo "   H0 SETUP FAIL: cannot retrieve ${PINNED_REV}:tools/gate_arc_lega_capture.sh"
  exit 2
}
if ! grep -q "L6 FAIL: falsifier vacuous" "$TMP/pinned_gate.sh"; then
  echo "   H0 SETUP FAIL: pinned revision does not contain 'L6 FAIL: falsifier vacuous'"
  exit 2
fi
if grep -q "L6_CRASHER_FIXTURE" "$TMP/pinned_gate.sh"; then
  echo "   H0 SETUP FAIL: pinned revision already contains L6_CRASHER_FIXTURE"
  exit 2
fi
echo "   H0 PASS: pinned ${PINNED_REV} verified (contains 'L6 FAIL: falsifier vacuous', lacks L6_CRASHER_FIXTURE)"
check_crash_and_tracked_hygiene "H0"

# ---------------------------------------------------------------- H1 RED-first
echo "-- H1 RED-first: pre-fix gate under stub exits 1 (vacuous FAIL); working tree under stub PASSes with L6 ENV NOTE"
cp "$TMP/pinned_gate.sh" "$TMP/pinned_stub.sh"
md5_pre_orig=$(md5sum "$TMP/pinned_gate.sh" | awk '{print $1}')
sed -i 's|( ulimit -c 0; exec /usr/bin/python3 tests/fixtures/faulthandler_segv_fixture.py ) > "$TMP/l6_crasher.out"|( ulimit -c 0; exec /usr/bin/python3 tests/fixtures/l6_no_crash_stub.py ) > "$TMP/l6_crasher.out"|' "$TMP/pinned_stub.sh"

# Run pinned pre-fix with stub
bash "$TMP/pinned_stub.sh" > "$TMP/h1_pre.out" 2>&1 || true
rc_h1_pre=$(grep -o 'gate rc: [0-9]*' "$TMP/h1_pre.out" | tail -1 | awk '{print $3}')
rc_h1_pre="${rc_h1_pre:-1}"

failing_legs_pre=$(grep -o 'L[0-9a-z-]* FAIL' "$TMP/h1_pre.out" | tr '\n' ' ')
echo "   pinned pre-fix gate rc=${rc_h1_pre} (failing: ${failing_legs_pre:-none})"

if [ "$rc_h1_pre" -ne 1 ]; then
  echo "   H1 FAIL: pinned pre-fix gate under stub returned rc=$rc_h1_pre (expected 1)"
  FAIL=1
fi
if ! grep -q "L6 FAIL: falsifier vacuous" "$TMP/h1_pre.out"; then
  echo "   H1 FAIL: pinned pre-fix gate under stub did not print 'L6 FAIL: falsifier vacuous'"
  FAIL=1
fi

# Pinned copy check: restored byte-identical
md5_pre_restored=$(md5sum "$TMP/pinned_gate.sh" | awk '{print $1}')
echo "   pinned pre-fix gate md5: orig=${md5_pre_orig} restored=${md5_pre_restored}"
if [ "$md5_pre_orig" != "$md5_pre_restored" ]; then
  echo "   H1 SETUP FAIL: pinned copy was altered!"
  exit 2
fi

# Run working-tree gate under stub
L6_CRASHER_FIXTURE=tests/fixtures/l6_no_crash_stub.py bash tools/gate_arc_lega_capture.sh > "$TMP/h1_wt.out" 2>&1 || true
rc_h1_wt=$(grep -o 'gate rc: [0-9]*' "$TMP/h1_wt.out" | tail -1 | awk '{print $3}')
rc_h1_wt="${rc_h1_wt:-1}"

failing_legs_wt=$(grep -o 'L[0-9a-z-]* FAIL' "$TMP/h1_wt.out" | tr '\n' ' ')
echo "   working tree gate rc=${rc_h1_wt} (failing: ${failing_legs_wt:-none})"

if ! grep -q "L6b-alt PASS: sweep necessity proven against a controlled fixture report" "$TMP/h1_wt.out"; then
  echo "   H1 FAIL: working tree gate did not print L6b-alt PASS"
  FAIL=1
fi
if ! grep -q "L6 ENV NOTE: apport did not record the deliberate crasher in 2 attempts" "$TMP/h1_wt.out"; then
  echo "   H1 FAIL: working tree gate did not print L6 ENV NOTE"
  FAIL=1
fi
if grep -q "L6 FAIL: falsifier vacuous" "$TMP/h1_wt.out"; then
  echo "   H1 FAIL: working tree gate unexpectedly printed 'L6 FAIL: falsifier vacuous'"
  FAIL=1
fi
if grep -q "L6 FAIL" "$TMP/h1_wt.out"; then
  echo "   H1 FAIL: working tree gate L6 leg reported FAIL"
  FAIL=1
fi
if ! grep -q "L6 PASS" "$TMP/h1_wt.out"; then
  echo "   H1 FAIL: working tree gate L6 leg did not print L6 PASS"
  FAIL=1
fi

if [ "$FAIL" -eq 0 ]; then
  echo "   H1 PASS: pre-fix observed RED (rc=1, vacuous FAIL); post-fix observed L6b-alt PASS + L6 ENV NOTE"
fi
check_crash_and_tracked_hygiene "H1"

# ---------------------------------------------------------------- H2 discrimination preserved
echo "-- H2 discrimination preserved: neutered sweep on stub-forced no-report path fails L6b-alt"
cp tools/gate_arc_lega_capture.sh "$TMP/gate_wt_neutered.sh"
md5_wt_before=$(md5sum "$TMP/gate_wt_neutered.sh" | awk '{print $1}')

# Neuter the sweep in the scratch copy
sed -i 's/sweep_fixture_reports() {/sweep_fixture_reports() { echo 0; return 0; /' "$TMP/gate_wt_neutered.sh"
md5_wt_after=$(md5sum "$TMP/gate_wt_neutered.sh" | awk '{print $1}')
echo "   working-tree scratch copy md5 before: ${md5_wt_before} after neutering: ${md5_wt_after}"

L6_CRASHER_FIXTURE=tests/fixtures/l6_no_crash_stub.py bash "$TMP/gate_wt_neutered.sh" > "$TMP/h2_neutered.out" 2>&1 || true
rc_h2=$(grep -o 'gate rc: [0-9]*' "$TMP/h2_neutered.out" | tail -1 | awk '{print $3}')
rc_h2="${rc_h2:-1}"

failing_legs_h2=$(grep -o 'L[0-9a-z-]* FAIL' "$TMP/h2_neutered.out" | tr '\n' ' ')
echo "   neutered gate rc=${rc_h2} (failing: ${failing_legs_h2:-none})"

if [ "$rc_h2" -ne 1 ]; then
  echo "   H2 FAIL: neutered gate rc was $rc_h2 (expected 1)"
  FAIL=1
fi
if ! grep -q "L6b-alt FAIL" "$TMP/h2_neutered.out"; then
  echo "   H2 FAIL: neutered gate did not print L6b-alt FAIL"
  FAIL=1
fi

if [ "$FAIL" -eq 0 ]; then
  echo "   H2 PASS: neutered sweep observed RED (rc=1, L6b-alt FAIL)"
fi
check_crash_and_tracked_hygiene "H2"

# ---------------------------------------------------------------- H3 real path still discriminates
echo "-- H3 the real path still discriminates: real fixture exercises crasher path"
cp tools/gate_arc_lega_capture.sh "$TMP/gate_h3.sh"
bash "$TMP/gate_h3.sh" > "$TMP/h3.out" 2>&1 || true
rc_h3=$(grep -o 'gate rc: [0-9]*' "$TMP/h3.out" | tail -1 | awk '{print $3}')
rc_h3="${rc_h3:-1}"

failing_legs_h3=$(grep -o 'L[0-9a-z-]* FAIL' "$TMP/h3.out" | tr '\n' ' ')
echo "   scratch gate rc=${rc_h3} (failing: ${failing_legs_h3:-none})"

has_red=0
has_note=0
if grep -q "L6b RED observed" "$TMP/h3.out"; then
  has_red=1
  echo "   H3: real crasher report recorded by apport (L6b RED observed)"
fi
if grep -q "L6 ENV NOTE" "$TMP/h3.out"; then
  has_note=1
  echo "   H3: real crasher report suppressed by apport; controlled necessity control observed (L6 ENV NOTE)"
fi

if [ "$has_red" -eq 0 ] && [ "$has_note" -eq 0 ]; then
  echo "   H3 FAIL: neither L6b RED observed nor L6 ENV NOTE was printed (silent pass disallowed)"
  FAIL=1
fi
if grep -q "L6 FAIL" "$TMP/h3.out"; then
  echo "   H3 FAIL: L6 leg reported FAIL in real path"
  FAIL=1
fi
if ! grep -q "L6 PASS" "$TMP/h3.out"; then
  echo "   H3 FAIL: L6 leg did not report L6 PASS in real path"
  FAIL=1
fi

if [ "$FAIL" -eq 0 ]; then
  echo "   H3 PASS: real fixture path discriminated and passed L6"
fi
check_crash_and_tracked_hygiene "H3"

# ---------------------------------------------------------------- H4 no regression / no pollution
echo "-- H4 no regression / no pollution: full gate and sibling gates run, /var/crash left clean"
bash tools/gate_arc_lega_capture.sh > "$TMP/h4_capture.out" 2>&1 || true
rc_capture=$(grep -o 'gate rc: [0-9]*' "$TMP/h4_capture.out" | tail -1 | awk '{print $3}')
rc_capture="${rc_capture:-1}"

failing_legs_capture=$(grep -o 'L[0-9a-z-]* FAIL' "$TMP/h4_capture.out" | tr '\n' ' ')
echo "   gate_arc_lega_capture.sh rc=${rc_capture} (failing: ${failing_legs_capture:-none})"

if ! grep -q "L6 PASS" "$TMP/h4_capture.out"; then
  echo "   H4 FAIL: gate_arc_lega_capture.sh L6 leg failed"
  FAIL=1
fi
if [ "$rc_capture" -ne 0 ]; then
  if [ "$failing_legs_capture" = "L5 FAIL " ]; then
    echo "   H4 NOTE: gate_arc_lega_capture.sh rc=${rc_capture} due to dirty-tree L5 check (expected pre-commit)"
  else
    echo "   H4 FAIL: unexpected failures in gate_arc_lega_capture.sh: ${failing_legs_capture}"
    FAIL=1
  fi
fi

bash tools/gate_arc_lega_naming.sh > "$TMP/h4_naming.out" 2>&1
rc_naming=$?
echo "   gate_arc_lega_naming.sh rc=${rc_naming}"
if [ "$rc_naming" -ne 0 ]; then
  echo "   H4 FAIL: gate_arc_lega_naming.sh failed"
  FAIL=1
fi

bash tools/gate_arc_lega_telemetry.sh > "$TMP/h4_telemetry.out" 2>&1
rc_telemetry=$?
echo "   gate_arc_lega_telemetry.sh rc=${rc_telemetry}"
if [ "$rc_telemetry" -ne 0 ]; then
  echo "   H4 FAIL: gate_arc_lega_telemetry.sh failed"
  FAIL=1
fi

bash tools/gate_arc_lega_record_survival.sh > "$TMP/h4_survival.out" 2>&1
rc_survival=$?
echo "   gate_arc_lega_record_survival.sh rc=${rc_survival}"
if [ "$rc_survival" -ne 0 ]; then
  echo "   H4 FAIL: gate_arc_lega_record_survival.sh failed"
  FAIL=1
fi

check_crash_and_tracked_hygiene "H4"
if [ "$FAIL" -eq 0 ]; then
  echo "   H4 PASS: all gates and hygiene checks passed"
fi

echo "-- gate rc: $FAIL (0 = all legs pass)"
exit "$FAIL"
