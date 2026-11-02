#!/usr/bin/env bash
# tools/gate_arc_lega_capture.sh — gate for DEFECT-22 live SIGSEGV capture instrument.
#
# What it decides: can the instrument capture live SIGSEGV with intact si_addr and
# concrete library attribution before Python's faulthandler destroys the context?
#
# Follows conventions of tools/gate_arc_lega_naming.sh:
#   set -u, REPO=, cd, exit 0 = red observed AND green holds, 1 = gate failed, 2 = setup failure.
#
# Legs:
#   L1 — capture works on the real mechanism (fixture under instrument gdb command file)
#   L2 — what it buys: neutralised run without live capture produces Fatal Python error, no si_addr
#   L3 — instrument plumbing + no-clobber (stub run x2 at same seed+head produces _rerun2)
#   L4 — explicit falsifier: gdb command file without stop clause goes RED
#   L5 — hygiene: git status shows only the four in-scope files
#   L6 — the gate must not leave the crash-capture path polluted: a deliberate crasher
#        DOES write /var/crash/<python3.12>.crash (measured, even under `ulimit -c 0`),
#        so the gate sweeps its own fixture reports, must not sweep a real one, and the
#        sweeper's necessity is proven by the crasher writing a report at all.
set -u
REPO=/home/jericho/projects/zion/projects/visual_audio
cd "$REPO" || exit 2

FAIL=0
SEED=999003
SHORT_HEAD=$(git rev-parse --short HEAD)

TMP=$(mktemp -d /tmp/gate_arc_capture.XXXXXX) || exit 2
cleanup() {
  rm -rf "$TMP"
}
trap cleanup EXIT

echo "== gate: arc_lega_capture live SIGSEGV instrument (seed=${SEED}) =="
echo "head=${SHORT_HEAD}"

# ---------------------------------------------------------------- L1 leg
echo "-- L1 leg: capture works on the real mechanism (faulthandler fixture under live capture)"
STUB_L1="$TMP/pystub_l1.sh"
cat > "$STUB_L1" <<'STUBEOF'
#!/usr/bin/env bash
if [ "${1:-}" = "-m" ]; then
  exec /usr/bin/python3 tests/fixtures/faulthandler_segv_fixture.py
fi
exec /usr/bin/python3 "$@"
STUBEOF
chmod +x "$STUB_L1"

OUTDIR="$TMP/l1" PY="$STUB_L1" SEED=$SEED bash tools/arc_lega_capture.sh > "$TMP/l1_run.out" 2>&1
L1_RC=$?
L1_GDB_LOG=$(ls "$TMP"/l1/arc_lega_capture_seed${SEED}_*.gdb.txt 2>/dev/null | head -1)

if [ -z "$L1_GDB_LOG" ] || [ ! -f "$L1_GDB_LOG" ]; then
  echo "L1 SETUP FAIL: no gdb transcript written to $TMP/l1"
  exit 2
fi

L1_HAS_MARKER=$(grep -c "DEFECT22_CAPTURE_START" "$L1_GDB_LOG" || true)
L1_SI_ADDR=$(grep "DEFECT22_CAPTURE: si_addr=" "$L1_GDB_LOG" | sed 's/.*=\s*//' | head -1)
L1_PC=$(grep "DEFECT22_CAPTURE: pc=" "$L1_GDB_LOG" | sed 's/.*=\s*//' | head -1)
L1_PC_SYM=$(grep "DEFECT22_CAPTURE: pc_symbol=" "$L1_GDB_LOG" | sed 's/.*pc_symbol=\s*//' | head -1)
L1_FAULT_INST=$(grep -A 1 "DEFECT22_CAPTURE: fault_instruction=" "$L1_GDB_LOG" | tail -1)

echo "   parsed marker:           ${L1_HAS_MARKER} (expected >= 1)"
echo "   parsed si_addr:          ${L1_SI_ADDR:-<missing>}"
echo "   parsed pc:               ${L1_PC:-<missing>}"
echo "   parsed pc_symbol:        ${L1_PC_SYM:-<missing>}"
echo "   parsed fault instruction:${L1_FAULT_INST:-<missing>}"
echo "   instrument exit code:    ${L1_RC} (expected 139)"

L1_OK=1
if [ "$L1_HAS_MARKER" -lt 1 ]; then
  echo "   L1 FAIL: marker DEFECT22_CAPTURE_START missing from transcript"
  L1_OK=0
fi
if [[ "$L1_SI_ADDR" != *"0x"* ]]; then
  echo "   L1 FAIL: si_addr missing or empty: '${L1_SI_ADDR:-}'"
  L1_OK=0
fi
if [ -z "$L1_FAULT_INST" ] || [[ "$L1_FAULT_INST" == *"none"* ]]; then
  echo "   L1 FAIL: fault instruction missing: '${L1_FAULT_INST:-}'"
  L1_OK=0
fi
if [[ "$L1_PC_SYM" != *".so"* ]]; then
  echo "   L1 FAIL: pc_symbol does not name a shared object: '${L1_PC_SYM:-}'"
  L1_OK=0
fi
if [ "$L1_RC" -ne 139 ]; then
  echo "   L1 FAIL: exit code is ${L1_RC}, expected 139 on caught SIGSEGV"
  L1_OK=0
fi

if [ "$L1_OK" -eq 1 ]; then
  echo "   L1 PASS: live SIGSEGV captured, si_addr and shared-object attribution intact"
else
  FAIL=1
fi

# ---------------------------------------------------------------- L1b leg
echo "-- L1b leg: the sidecar's crash count agrees with the capture it records"
# Why this leg exists: a captured SIGSEGV never reaches Python's faulthandler (gdb stops the signal
# first), so the raw "Fatal Python error" grep count is 0 for exactly the RED this instrument exists
# to record. Measured on the pre-fix instrument (revision d62e96a, exercised below):
#   {"capture": {"segv_caught": true}, "crashes": 0}
# i.e. the one record a future RED produces read as "no crash".
cat > "$TMP/sidecar_consistency.py" <<'PYX'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception as e:
    print(f"cannot read sidecar: {e}", file=sys.stderr)
    sys.exit(2)
cap = d.get("capture") or {}
segv, crashes = cap.get("segv_caught"), d.get("crashes")
if segv is True and not (isinstance(crashes, int) and crashes >= 1):
    print(f"CONTRADICTION: segv_caught=true but crashes={crashes!r} "
          f"(faulthandler_crashes={d.get('faulthandler_crashes')!r}, "
          f"source={d.get('crash_count_source')!r})", file=sys.stderr)
    sys.exit(3)
if segv is not True and crashes != 0:
    print(f"CONTRADICTION: segv_caught={segv!r} but crashes={crashes!r}", file=sys.stderr)
    sys.exit(3)
sys.exit(0)
PYX

L1B_JSON=$(ls "$TMP"/l1/arc_lega_capture_seed${SEED}_*.json 2>/dev/null | head -1)
if [ -z "$L1B_JSON" ]; then
  echo "L1b SETUP FAIL: L1 produced no sidecar to check"
  exit 2
fi
/usr/bin/python3 "$TMP/sidecar_consistency.py" "$L1B_JSON" 2> "$TMP/l1b_green.err"
L1B_GREEN_PRED=$?

# Falsifier: run the PRE-FIX instrument (pinned revision) against the same crasher. Its sidecar must
# fail the same predicate — otherwise this leg proves nothing about the fix.
PREFIX_REV=d62e96a
git show "$PREFIX_REV:tools/arc_lega_capture.sh" > "$TMP/prefix_capture.sh" 2>/dev/null
if [ -s "$TMP/prefix_capture.sh" ] && ! grep -q 'crash_count_source' "$TMP/prefix_capture.sh"; then
  PREFIX_PREMISE_OK=1
else
  PREFIX_PREMISE_OK=0
fi

L1B_PREFIX_PRED=99
if [ "$PREFIX_PREMISE_OK" -eq 1 ]; then
  OUTDIR="$TMP/l1b_prefix" PY="$STUB_L1" SEED=$((SEED + 1)) bash "$TMP/prefix_capture.sh" > "$TMP/l1b_prefix.out" 2>&1
  L1B_PREFIX_JSON=$(ls "$TMP"/l1b_prefix/arc_lega_capture_seed*.json 2>/dev/null | head -1)
  if [ -n "$L1B_PREFIX_JSON" ]; then
    /usr/bin/python3 "$TMP/sidecar_consistency.py" "$L1B_PREFIX_JSON" 2> "$TMP/l1b_prefix.err"
    L1B_PREFIX_PRED=$?
  fi
fi

echo "   green predicate rc:      ${L1B_GREEN_PRED} (expected 0)"
echo "   pre-fix predicate rc:    ${L1B_PREFIX_PRED} (expected 3 = contradiction observed)"
echo "   pre-fix premise (pinned $PREFIX_REV lacks crash_count_source): ${PREFIX_PREMISE_OK} (expected 1)"

L1B_OK=1
if [ "$L1B_GREEN_PRED" -ne 0 ]; then
  echo "   L1b FAIL: fixed instrument's sidecar is self-contradictory:"
  cat "$TMP/l1b_green.err"
  L1B_OK=0
fi
if [ "$L1B_PREFIX_PRED" -ne 3 ]; then
  echo "   L1b FAIL: pre-fix instrument did not show the contradiction (predicate rc=${L1B_PREFIX_PRED}) — leg vacuous"
  [ -f "$TMP/l1b_prefix.err" ] && cat "$TMP/l1b_prefix.err"
  L1B_OK=0
fi

if [ "$L1B_OK" -eq 1 ]; then
  echo "   L1b PASS: a captured crash is counted as a crash; the pre-fix record is shown self-contradictory"
else
  FAIL=1
fi

# ---------------------------------------------------------------- L2 leg
echo "-- L2 leg: what it buys (neutralised run without live capture loses si_addr and attribution)"
# Deliberate crasher, RLIMIT_CORE=0: MEASURED 2026-09-13 09:23 — apport is still invoked and
# still writes /var/crash/<python3.12>.crash (log: "core limit 0, dump mode 1" then "wrote
# report"); the limit only suppresses the multi-MB RAW core in /var/lib/apport/coredump.
# So the guard is a disk-size guard, NOT a report guard — the L6 leg is what protects the
# capture path from the report a deliberate crash leaves behind.
( ulimit -c 0; exec /usr/bin/python3 tests/fixtures/faulthandler_segv_fixture.py ) > "$TMP/l2_neutral.out" 2>&1 || true
L2_HAS_FAULTHANDLER=$(grep -c "Fatal Python error: Segmentation fault" "$TMP/l2_neutral.out" || true)
L2_HAS_SI_ADDR=$(grep -c -i "si_addr" "$TMP/l2_neutral.out" || true)
L2_HAS_SHARED_OBJ=$(grep -E -c "\.so(\.[0-9]+)?" "$TMP/l2_neutral.out" || true)

echo "   Fatal Python error present: ${L2_HAS_FAULTHANDLER} (expected >= 1)"
echo "   si_addr present:            ${L2_HAS_SI_ADDR} (expected 0)"
echo "   shared object attribution:  ${L2_HAS_SHARED_OBJ} (expected 0)"

L2_OK=1
if [ "$L2_HAS_FAULTHANDLER" -lt 1 ]; then
  echo "   L2 FAIL: Fatal Python error line missing in neutralised output"
  L2_OK=0
fi
if [ "$L2_HAS_SI_ADDR" -ne 0 ]; then
  echo "   L2 FAIL: neutralised run unexpectedly contained si_addr (gate cannot discriminate)"
  L2_OK=0
fi
if [ "$L2_HAS_SHARED_OBJ" -ne 0 ]; then
  echo "   L2 FAIL: neutralised run unexpectedly contained shared-object attribution"
  L2_OK=0
fi

if [ "$L2_OK" -eq 1 ]; then
  echo "   L2 PASS: gate discriminates — neutralised run confirms faulthandler destroys native context"
else
  FAIL=1
fi

# ---------------------------------------------------------------- L3 leg
echo "-- L3 leg: instrument plumbing and no-clobber"
STUB_L3="$TMP/pystub_l3.sh"
cat > "$STUB_L3" <<'STUBEOF'
#!/usr/bin/env bash
if [ "${1:-}" = "-m" ]; then
  echo "gate-stub nonce=${GATE_NONCE:-none}"
  echo "gate-stub core-limit=$(ulimit -c)"
  exit 0
fi
exec /usr/bin/python3 "$@"
STUBEOF
chmod +x "$STUB_L3"

# Run 1
OUTDIR="$TMP/l3" GATE_NONCE=r1 PY="$STUB_L3" SEED=$SEED bash tools/arc_lega_capture.sh > "$TMP/l3_run1.out" 2>&1
L3_RC1=$?
L3_F1_JSON=$(ls "$TMP"/l3/arc_lega_capture_seed${SEED}_${SHORT_HEAD}.json 2>/dev/null | head -1)
L3_F1_TXT=$(ls "$TMP"/l3/arc_lega_capture_seed${SEED}_${SHORT_HEAD}.txt 2>/dev/null | head -1)
L3_F1_GDB=$(ls "$TMP"/l3/arc_lega_capture_seed${SEED}_${SHORT_HEAD}.gdb.txt 2>/dev/null | head -1)

if [ -z "$L3_F1_JSON" ] || [ -z "$L3_F1_TXT" ] || [ -z "$L3_F1_GDB" ]; then
  echo "   L3 FAIL: run 1 did not write all three artifacts (.txt, .json, .gdb.txt)"
  FAIL=1
fi

L3_M1=$(md5sum "$L3_F1_JSON" "$L3_F1_TXT" "$L3_F1_GDB" | cut -d' ' -f1 | tr '\n' ':')

# Validate JSON sidecar
/usr/bin/python3 - "$L3_F1_JSON" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
need_keys = {"seed", "head", "rc", "crashes", "seconds", "summary", "log", "gdb_log", "started_utc", "loadavg_before", "capture"}
missing = need_keys - data.keys()
if missing:
    print(f"JSON missing keys: {missing}", file=sys.stderr)
    sys.exit(1)
cap = data["capture"]
need_cap = {"segv_caught", "signal", "pc", "si_addr", "pc_symbol"}
missing_cap = need_cap - cap.keys()
if missing_cap:
    print(f"capture object missing keys: {missing_cap}", file=sys.stderr)
    sys.exit(1)
if cap["segv_caught"] is not False:
    print(f"expected segv_caught == false, got {cap['segv_caught']}", file=sys.stderr)
    sys.exit(1)
if cap["si_addr"] is not None:
    print(f"expected si_addr == null, got {cap['si_addr']}", file=sys.stderr)
    sys.exit(1)
if data["rc"] != 0:
    print(f"expected rc == 0, got {data['rc']}", file=sys.stderr)
    sys.exit(1)
PY
L3_JSON_OK=$?

# Run 2 (same seed and head, rerun guard must kick in)
OUTDIR="$TMP/l3" GATE_NONCE=r2 PY="$STUB_L3" SEED=$SEED bash tools/arc_lega_capture.sh > "$TMP/l3_run2.out" 2>&1
L3_RC2=$?
L3_F2_JSON=$(ls "$TMP"/l3/arc_lega_capture_seed${SEED}_${SHORT_HEAD}_rerun2.json 2>/dev/null | head -1)
L3_F2_TXT=$(ls "$TMP"/l3/arc_lega_capture_seed${SEED}_${SHORT_HEAD}_rerun2.txt 2>/dev/null | head -1)
L3_F2_GDB=$(ls "$TMP"/l3/arc_lega_capture_seed${SEED}_${SHORT_HEAD}_rerun2.gdb.txt 2>/dev/null | head -1)
L3_M2=$(md5sum "$L3_F1_JSON" "$L3_F1_TXT" "$L3_F1_GDB" | cut -d' ' -f1 | tr '\n' ':')

L3_SUMMARY_OK=$(grep -c "arc leg A (live capture) :: seed=" "$TMP/l3_run1.out" || true)

echo "   run 1 rc:                ${L3_RC1} (expected 0)"
echo "   run 2 rc:                ${L3_RC2} (expected 0)"
echo "   summary line present:    ${L3_SUMMARY_OK}"
echo "   rerun2 artifact exists:  $([ -n "$L3_F2_JSON" ] && echo "yes" || echo "no")"
echo "   first record md5 match:  $([ "$L3_M1" = "$L3_M2" ] && echo "identical" || echo "changed")"

L3_OK=1
if [ "$L3_RC1" -ne 0 ] || [ "$L3_RC2" -ne 0 ]; then
  echo "   L3 FAIL: expected exit code 0 matching stub"
  L3_OK=0
fi
if [ "$L3_JSON_OK" -ne 0 ]; then
  echo "   L3 FAIL: sidecar JSON keys or values invalid"
  L3_OK=0
fi
if [ -z "$L3_F2_JSON" ]; then
  echo "   L3 FAIL: rerun2 sidecar artifact missing"
  L3_OK=0
fi
if [ "$L3_M1" != "$L3_M2" ]; then
  echo "   L3 FAIL: rerun overwrote initial run artifacts (clobber detected)"
  L3_OK=0
fi
if [ "$L3_SUMMARY_OK" -lt 1 ]; then
  echo "   L3 FAIL: stdout summary line missing"
  L3_OK=0
fi

if [ "$L3_OK" -eq 1 ]; then
  echo "   L3 PASS: instrument plumbing and no-clobber verified"
else
  FAIL=1
fi

# ---------------------------------------------------------------- L4 leg
echo "-- L4 leg: explicit falsifier (removing stop clause goes RED on L1 assertions)"
# GDB's built-in default for SIGSEGV is stop print pass; neutralising the stop clause to
# 'handle SIGSEGV nostop pass' removes the stop behavior so the process terminates under faulthandler.
FALSIFIER_GDB="$TMP/falsifier.gdb"
sed -e 's/handle SIGSEGV stop.*/handle SIGSEGV nostop pass/' tools/gdb_segv_capture.gdb > "$FALSIFIER_GDB"

# The point of this leg is the missing stop clause, not a core — hence the same `ulimit -c 0`
# disk-size guard (it does not stop the apport report; L6 sweeps that).
( ulimit -c 0; exec gdb -q -batch -iex "set debuginfod enabled off" -x "$FALSIFIER_GDB" \
    --args /usr/bin/python3 tests/fixtures/faulthandler_segv_fixture.py ) > "$TMP/l4_transcript.txt" 2>&1 || true

L4_SI_ADDR=$(grep "DEFECT22_CAPTURE: si_addr=" "$TMP/l4_transcript.txt" | sed 's/.*=\s*//' | head -1)
L4_PC_SYM=$(grep "DEFECT22_CAPTURE: pc_symbol=" "$TMP/l4_transcript.txt" | sed 's/.*pc_symbol=\s*//' | head -1)
L4_FAULT_INST=$(grep -A 1 "DEFECT22_CAPTURE: fault_instruction=" "$TMP/l4_transcript.txt" | tail -1)

echo "   L1 observation (with stop):     si_addr=${L1_SI_ADDR}, pc_symbol=${L1_PC_SYM}"
echo "   L4 observation (falsifier RED): si_addr=${L4_SI_ADDR:-none}, pc_symbol=${L4_PC_SYM:-none}"

L4_WENT_RED=0
if [[ "$L4_SI_ADDR" != *"0x"* ]] && [[ "$L4_PC_SYM" != *".so"* ]]; then
  L4_WENT_RED=1
fi

if [ "$L4_WENT_RED" -eq 1 ]; then
  echo "   RED CONFIRMED: without stop clause, live capture fails and L1 assertions go RED"
  echo "   L4 PASS: explicit falsifier observed RED"
else
  echo "   RED NOT OBSERVED: falsifier unexpectedly retained si_addr or attribution"
  echo "   L4 FAIL: gate cannot discriminate failure"
  FAIL=1
fi

# ---------------------------------------------------------------- L5 leg
echo "-- L5 leg: hygiene"
MODIFIED_COUNT=$(git diff --name-only | wc -l)
if [ "$MODIFIED_COUNT" -ne 0 ]; then
  echo "   L5 FAIL: existing tracked files were modified:"
  git diff --name-only
  FAIL=1
else
  echo "   tracked modifications: 0 (clean)"
fi

# Verify exactly the four in-scope files exist
IN_SCOPE_MISSING=0
for f in tools/gdb_segv_capture.gdb tools/arc_lega_capture.sh tools/gate_arc_lega_capture.sh tests/fixtures/faulthandler_segv_fixture.py; do
  if [ ! -f "$f" ]; then
    echo "   L5 FAIL: required deliverable missing: $f"
    IN_SCOPE_MISSING=1
  fi
done

if [ "$MODIFIED_COUNT" -eq 0 ] && [ "$IN_SCOPE_MISSING" -eq 0 ]; then
  echo "   L5 PASS: working tree clean and four in-scope files present"
else
  FAIL=1
fi

# ---------------------------------------------------------------- L6 leg
echo "-- L6 leg: the gate must not leave the crash-capture path polluted (/var/crash)"
CRASH_DIR=/var/crash
L6_CRASHER_FIXTURE="${L6_CRASHER_FIXTURE:-tests/fixtures/faulthandler_segv_fixture.py}"
FIXTURE_TAG=$(basename "$L6_CRASHER_FIXTURE")
echo "   crasher fixture: $L6_CRASHER_FIXTURE (tag: $FIXTURE_TAG)"
# Measured 2026-09-13 09:23: a deliberate crasher writes /var/crash/<python3.12>.crash even
# under `ulimit -c 0`. While that report sits there "unseen", apport REFUSES to record the
# next crash of the same executable ("already exists and unseen, skipping to avoid disk usage
# DoS" — /var/log/apport.log) and the arc's interpreter IS python3.12. So the loop's own gate
# silently disarms the apport capture path it was built to feed. This leg makes that a checked
# property: sweep only OUR reports, prove the sweep was necessary, and leave the path clean.

# Echoes the ProcCmdline of a /var/crash report (short), or '?' if unreadable.
report_cmdline() {
  head -c 200000 "$1" 2>/dev/null | grep -a -m 1 '^ProcCmdline:' | cut -c1-110
}

# True iff the report's OWN ProcCmdline names the fixture. Deliberately the narrow field: a REAL
# crash report must survive the sweep even if some other field (stack frame, file list) mentions
# the fixture path. The sweep is destructive, so its predicate is the strictest one that is true
# of every fixture report.
is_fixture_report() {
  grep -a -m 1 '^ProcCmdline:' "$1" 2>/dev/null | grep -qa "$FIXTURE_TAG"
}

# Moves fixture-caused reports out of CRASH_DIR (instrument junk by definition — the fixture
# is a deliberate crasher, never evidence of a new arc crash). Echoes how many it moved.
sweep_fixture_reports() {
  local moved=0 f
  for f in "$CRASH_DIR"/*.crash; do
    [ -f "$f" ] || continue
    if is_fixture_report "$f"; then
      if mv "$f" "$QUARANTINE/$(basename "$f").$RANDOM" 2>/dev/null; then
        moved=$((moved + 1))
      fi
    fi
  done
  echo "$moved"
}

QUARANTINE="$TMP/quarantine"
mkdir -p "$QUARANTINE" 2>/dev/null || true
L6_OK=1
L6_DECIDED=0

if [ ! -d "$CRASH_DIR" ] || [ ! -w "$CRASH_DIR" ]; then
  echo "   L6 SKIP: $CRASH_DIR absent or not writable — leg cannot be decided here (NOT a pass)"
elif ! command -v apport > /dev/null 2>&1 && [ ! -e /usr/share/apport/apport ]; then
  echo "   L6 SKIP: no apport on this host — leg cannot be decided here (NOT a pass)"
else
  L6_SWEPT=$(sweep_fixture_reports)
  OCCUPIED=0
  for f in "$CRASH_DIR"/*.crash; do
    [ -f "$f" ] || continue
    if is_fixture_report "$f"; then OCCUPIED=$((OCCUPIED + 1)); fi
  done
  echo "   stale fixture reports swept: ${L6_SWEPT}; fixture reports still present: ${OCCUPIED}"

  if [ "$OCCUPIED" -ne 0 ]; then
    echo "   L6 FAIL: could not sweep a fixture report (permissions?) — a stale report blocks the apport path"
    L6_OK=0
  else
    # L6a — sweeper selectivity: a report that is NOT ours must survive the sweep, even when it
    # mentions the fixture path in a body field (the sweep keys on ProcCmdline only).
    SYNTH="$CRASH_DIR/_usr_bin_python3.12.1000.crash"
    printf 'ProblemType: Crash\nExecutablePath: /usr/bin/python3.12\nProcCmdline: /usr/bin/python3 -m pytest tests/test_gh22_device_driver_abi.py\nStacktraceTop: %s (mentioned in a body field, must not matter)\n' "$FIXTURE_TAG" > "$SYNTH" 2>/dev/null || true
    if [ -f "$SYNTH" ]; then
      sweep_fixture_reports > /dev/null
      if [ -f "$SYNTH" ]; then
        echo "   L6a PASS: sweeper selectivity — a non-fixture report survives, even mentioning the fixture path in a body field"
      else
        echo "   L6a FAIL: the sweep removed a report that was not the fixture — it could destroy a real crash record"
        L6_OK=0
      fi
      rm -f "$SYNTH"
    else
      echo "   L6a FAIL: could not plant the synthetic report in $CRASH_DIR — selectivity undecided"
      L6_OK=0
    fi

    # L6b — necessity/falsifier: the deliberate crasher MUST leave a report, else L6 is vacuous.
    if [ "$L6_OK" -eq 1 ]; then
      L6_RED=0
      for attempt in 1 2; do
        if [ "$attempt" -gt 1 ]; then
          sweep_fixture_reports > /dev/null
        fi
        ( ulimit -c 0; exec /usr/bin/python3 "$L6_CRASHER_FIXTURE" ) > "$TMP/l6_crasher.out" 2>&1
        crasher_rc=$?
        sleep 2
        L6_RED=0
        for f in "$CRASH_DIR"/*.crash; do
          [ -f "$f" ] || continue
          if is_fixture_report "$f"; then L6_RED=$((L6_RED + 1)); fi
        done
        echo "   attempt=${attempt} crasher_rc=${crasher_rc} fixture_reports_after=${L6_RED}"
        if [ "$L6_RED" -gt 0 ]; then
          echo "   L6b RED observed (attempt ${attempt}): the deliberate crasher left $L6_RED fixture report(s) — the sweep is necessary"
          break
        fi
      done
      if [ "$L6_RED" -eq 0 ]; then
        OTHER=$(ls "$CRASH_DIR"/*.crash 2>/dev/null | head -1)
        if [ -n "$OTHER" ]; then
          echo "   L6 SKIP: a pre-existing non-fixture report occupies the apport path ($(report_cmdline "$OTHER")) —"
          echo "            that IS the pollution this leg exists to prevent, and apport is skipping new reports."
        else
          SYNTH_NECESSITY="$CRASH_DIR/_usr_bin_python3.12.1000.fixture_control.crash"
          printf 'ProblemType: Crash\nExecutablePath: /usr/bin/python3.12\nProcCmdline: /usr/bin/python3 %s\n' "$L6_CRASHER_FIXTURE" > "$SYNTH_NECESSITY" 2>/dev/null || true
          if [ -f "$SYNTH_NECESSITY" ]; then
            SW_RES=$(sweep_fixture_reports)
            if [ ! -f "$SYNTH_NECESSITY" ]; then
              echo "   L6b-alt PASS: sweep necessity proven against a controlled fixture report"
              echo "   L6 ENV NOTE: apport did not record the deliberate crasher in 2 attempts (evidence above) — environment condition, not a tree verdict"
            else
              echo "   L6b-alt FAIL: sweep failed to remove controlled fixture report"
              L6_OK=0
              rm -f "$SYNTH_NECESSITY"
            fi
          else
            echo "   L6b-alt FAIL: could not plant controlled fixture report in $CRASH_DIR"
            L6_OK=0
          fi
        fi
      fi
    fi

    # L6c — cleanup: after sweeping, the path must be clear for a real crash.
    if [ "$L6_OK" -eq 1 ]; then
      L6_SWEPT2=$(sweep_fixture_reports)
      L6_LEFT=$(ls "$CRASH_DIR"/*.crash 2>/dev/null | wc -l)
      if [ "$L6_LEFT" -eq 0 ]; then
        echo "   L6c PASS: swept ${L6_SWEPT2} report(s); $CRASH_DIR left clean ($L6_LEFT) — apport can record the next real crash"
        L6_DECIDED=1
      else
        echo "   L6c FAIL: $L6_LEFT report(s) left in $CRASH_DIR: $(ls "$CRASH_DIR"/*.crash 2>/dev/null | head -1)"
        L6_OK=0
      fi
    fi
  fi
fi

if [ "$L6_OK" -eq 1 ]; then
  if [ "$L6_DECIDED" -eq 1 ]; then
    echo "   L6 PASS"
  else
    echo "   L6 NOT DECIDED (see SKIP above) — counted as no-failure, but not as a verified property"
  fi
else
  FAIL=1
fi

echo "-- gate rc: $FAIL (0 = red observed and green holds)"
exit "$FAIL"
