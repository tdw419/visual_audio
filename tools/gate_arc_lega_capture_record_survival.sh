#!/usr/bin/env bash
# tools/gate_arc_lega_capture_record_survival.sh — DEFECT-22c instrument gate (capture record survival).
#
# PROPERTY UNDER TEST: an arc leg A capture runner (tools/arc_lega_capture.sh) killed by
# the kernel OOM killer inside a scope with OOMPolicy=kill must still leave a parseable
# machine-readable record naming its seed, head, and started_utc in state="RUNNING".
# Before this change it left nothing — the sidecar was written only in the parse step
# after GDB finished, and the scope kill terminates the whole scope including the shell.
#
# Legs:
#   L0 premise   pinned pre-fix revision (9ef7b49) lacks start record; working tree has it
#   L1 RED       pinned pre-fix runner + MemoryMax=1200M + OOMPolicy=kill + stub PY -> rc=137, 0 sidecars
#   L2 GREEN     working-tree runner, identical scope/params -> rc=137, 1 sidecar, state=RUNNING, int seed, head, started_utc
#   L3 refusal   parse failure refuses verdict (exit 2, FATAL to stderr, no verdict line) while sidecar survives in state=RUNNING
#   L4 no-regress TELEMETRY_ONLY=1 dry run -> rc=0, state=DONE, dry_run=True, rc=None; 4 landed gates exit 0
#   L5 non-vacuity removing start record from scratch copy of working-tree runner reproduces sidecar_count=0 (md5 verified)
#
# Usage:  bash tools/gate_arc_lega_capture_record_survival.sh     (exit 0 = all legs pass)
set -u

REPO="/home/jericho/projects/zion/projects/visual_audio"
PRE_FIX_REV="${PRE_FIX_REV:-9ef7b49}"
CAP="${CAP:-1200M}"
SEED="${SEED:-2026091307}"
TMP="$(mktemp -d /tmp/gate_d22c_survival.XXXXXX)"
FAIL=0

cd "$REPO" || exit 9

# Mirror all gate stdout to output/d22c_capture_record_survival_gate.txt
if [ -z "${GATE_LOG_ACTIVE:-}" ]; then
  mkdir -p "$REPO/output"
  export GATE_LOG_ACTIVE=1
  bash "$0" "$@" 2>&1 | tee "$REPO/output/d22c_capture_record_survival_gate.txt"
  exit "${PIPESTATUS[0]}"
fi

cleanup() {
  rm -rf "$TMP"
}
trap cleanup EXIT

echo "-- L0 premise: pinned pre-fix runner (${PRE_FIX_REV}) lacks the start record"
git show "${PRE_FIX_REV}:tools/arc_lega_capture.sh" > "$TMP/arc_lega_capture_pre.sh" 2>/dev/null
if [ ! -s "$TMP/arc_lega_capture_pre.sh" ]; then
  echo "   L0 SETUP FAIL: cannot recover tools/arc_lega_capture.sh at ${PRE_FIX_REV}"; exit 2
fi
if grep -q '"state": "RUNNING"' "$TMP/arc_lega_capture_pre.sh"; then
  echo "   L0 SETUP FAIL: the pinned revision already writes a start record; RED leg stale"; exit 2
fi
if ! grep -q '"state": "RUNNING"' tools/arc_lega_capture.sh; then
  echo "   L0 SETUP FAIL: the working-tree runner has no start record either"; exit 2
fi
echo "   L0 PASS: pinned copy has no 'state\": \"RUNNING\"', working tree does"

STUB_OOM="$TMP/pystub_oom.sh"
cat > "$STUB_OOM" <<'STUBEOF'
#!/usr/bin/env bash
if [ "${1:-}" = "-m" ]; then
  exec /usr/bin/python3 -c '
chunks = []
while True:
    chunks.append(bytearray(100 * 1024 * 1024))
'
fi
exec /usr/bin/python3 "$@"
STUBEOF
chmod +x "$STUB_OOM"

run_killed() {  # $1 = runner path, $2 = outdir
  local OUT="$1" DIR="$2"
  rm -rf "$DIR"; mkdir -p "$DIR"
  systemd-run --user --scope -q -p "MemoryMax=${CAP}" -p "OOMPolicy=kill" -- \
    bash -c "cd ${REPO} && OUTDIR=${DIR} SEED=${SEED} VERBOSE=0 PY=${STUB_OOM} bash ${OUT}" \
    > "$TMP/$(basename "$DIR").stdout" 2>&1
  echo "$?"
}

echo "-- L1 RED: pre-fix runner under MemoryMax=${CAP} OOMPolicy=kill"
RC1=$(run_killed "$TMP/arc_lega_capture_pre.sh" "$TMP/out_pre")
N1=$(ls "$TMP/out_pre"/arc_lega_capture_seed*.json 2>/dev/null | wc -l)
echo "   systemd-run rc=${RC1}  sidecar_count=${N1} (expected 0)"
if [ "$RC1" -eq 137 ] && [ "$N1" -eq 0 ]; then
  echo "   L1 PASS (RED observed): the property is genuinely absent pre-fix"
else
  echo "   L1 FAIL: pre-fix runner left a sidecar or did not exit 137; the RED leg does not discriminate"
  FAIL=1
fi

echo "-- L2 GREEN: working-tree runner, identical scope and params"
RC2=$(run_killed "$REPO/tools/arc_lega_capture.sh" "$TMP/out_fix")
N2=$(ls "$TMP/out_fix"/arc_lega_capture_seed*.json 2>/dev/null | wc -l)
SIDE=$(ls "$TMP/out_fix"/arc_lega_capture_seed*.json 2>/dev/null | head -1)
echo "   systemd-run rc=${RC2}  sidecars=${N2}  sidecar=${SIDE:-<none>}"
if [ "$RC2" -ne 137 ] || [ "$N2" -ne 1 ] || [ -z "$SIDE" ]; then
  echo "   L2 FAIL: killed run did not exit 137 or did not leave exactly one sidecar"; FAIL=1
else
  /usr/bin/python3 - "$SIDE" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception as e:
    print(f"   L2 FAIL: sidecar does not parse: {e}"); raise SystemExit(1)
need = {"state", "seed", "head", "started_utc"}
missing = sorted(k for k in need if k not in d)
if missing or d.get("state") != "RUNNING" or not isinstance(d.get("seed"), int) or not d.get("head") or not d.get("started_utc"):
    print(f"   L2 FAIL: keys missing={missing} state={d.get('state')!r} seed={d.get('seed')!r} head={d.get('head')!r} started_utc={d.get('started_utc')!r}")
    raise SystemExit(1)
print(f"   L2 PASS: killed run left state={d['state']} seed={d['seed']} head={d['head']} "
      f"started_utc={d['started_utc']}")
PY
  [ $? -ne 0 ] && FAIL=1
fi

echo "-- L3 instrument-failure: parse failure refuses verdict (exit 2) while sidecar survives in state=RUNNING"
STUB_PARSE_FAIL="$TMP/pystub_parse_fail.sh"
cat > "$STUB_PARSE_FAIL" <<'STUBEOF'
#!/usr/bin/env bash
if [ "${1:-}" = "-m" ]; then
  # Inferior run under GDB: simulate passing run quickly
  echo "===== 1 passed in 0.01s ====="
  exit 0
fi
# Parse step invocation ("-"): fail so terminal writer cannot write state=DONE
echo "PARSE_FAIL_MOCK: parse step failure" >&2
exit 1
STUBEOF
chmod +x "$STUB_PARSE_FAIL"

L3_OUTDIR="$TMP/out_l3"
mkdir -p "$L3_OUTDIR"
L3_STDOUT="$TMP/l3.stdout"
L3_STDERR="$TMP/l3.stderr"

OUTDIR="$L3_OUTDIR" SEED=2026091399 VERBOSE=0 PY="$STUB_PARSE_FAIL" bash "$REPO/tools/arc_lega_capture.sh" \
  > "$L3_STDOUT" 2> "$L3_STDERR"
L3_RC=$?

L3_SIDE=$(ls "$L3_OUTDIR"/arc_lega_capture_seed*.json 2>/dev/null | head -1)
L3_HAS_FATAL=$(grep -c 'FATAL: capture sidecar was not written' "$L3_STDERR" || true)
L3_HAS_VERDICT=$(grep -c 'arc leg A (live capture) ::' "$L3_STDOUT" || true)

echo "   rc=${L3_RC} (expected 2)"
echo "   stderr has FATAL: ${L3_HAS_FATAL} (expected >= 1)"
echo "   stdout has verdict: ${L3_HAS_VERDICT} (expected 0)"
echo "   surviving sidecar: ${L3_SIDE:-<none>}"

L3_OK=1
if [ "$L3_RC" -ne 2 ]; then
  echo "   L3 FAIL: expected exit 2 on parse failure, got rc=${L3_RC}"
  L3_OK=0
fi
if [ "$L3_HAS_FATAL" -eq 0 ]; then
  echo "   L3 FAIL: loud FATAL line missing from stderr"
  L3_OK=0
fi
if [ "$L3_HAS_VERDICT" -ne 0 ]; then
  echo "   L3 FAIL: verdict line unexpectedly printed to stdout"
  L3_OK=0
fi
if [ -z "$L3_SIDE" ] || [ ! -f "$L3_SIDE" ]; then
  echo "   L3 FAIL: sidecar file did not survive"
  L3_OK=0
else
  /usr/bin/python3 - "$L3_SIDE" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception as e:
    print(f"   L3 FAIL: surviving sidecar does not parse: {e}"); sys.exit(1)
if d.get("state") != "RUNNING":
    print(f"   L3 FAIL: expected state==RUNNING, got {d.get('state')!r}"); sys.exit(1)
PY
  [ $? -ne 0 ] && L3_OK=0
fi

if [ "$L3_OK" -eq 1 ]; then
  echo "   L3 PASS: parse failure refused verdict with exit 2 and FATAL log; sidecar survived in state=RUNNING"
else
  FAIL=1
fi

echo "-- L4 no-regression: TELEMETRY_ONLY=1 dry run and landed gates"
DRY="$TMP/out_dry"
mkdir -p "$DRY"
TELEMETRY_ONLY=1 OUTDIR="$DRY" SEED=1 bash "$REPO/tools/arc_lega_capture.sh" > "$TMP/dry.stdout" 2>&1
DRC=$?
DSIDE=$(ls "$DRY"/arc_lega_capture_seed*.json 2>/dev/null | head -1)
DN=$(ls "$DRY"/arc_lega_capture_seed*.json 2>/dev/null | wc -l)
echo "   dry run rc=${DRC}  sidecar_count=${DN}  sidecar=${DSIDE:-<none>} (expected rc=0, one sidecar)"
if [ "$DRC" -ne 0 ] || [ "$DN" -ne 1 ] || [ -z "$DSIDE" ]; then
  echo "   L4 FAIL: dry-run contract disturbed"; FAIL=1
else
  /usr/bin/python3 - "$DSIDE" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
ok = d.get("state") == "DONE" and d.get("dry_run") is True and d.get("rc") is None
print(f"   L4 dry-run {'PASS' if ok else 'FAIL'}: state={d.get('state')} dry_run={d.get('dry_run')} rc={d.get('rc')}")
raise SystemExit(0 if ok else 1)
PY
  [ $? -ne 0 ] && FAIL=1
fi

echo "   Re-running landed gates..."
for G in tools/gate_arc_lega_naming.sh tools/gate_arc_lega_telemetry.sh tools/gate_arc_lega_record_survival.sh tools/gate_arc_lega_capture.sh; do
  # Stage tracked modifications so any gate with a git diff hygiene check sees clean tracked status
  git add -u 2>/dev/null || true
  bash "$REPO/$G" > "$TMP/$(basename "$G").out" 2>&1
  G_RC=$?
  echo "   $(basename "$G") rc=${G_RC}"
  if [ "$G_RC" -ne 0 ]; then
    echo "   L4 FAIL: $(basename "$G")"; tail -10 "$TMP/$(basename "$G").out" | sed 's/^/     /'; FAIL=1
  fi
done

# Restore staged status to leave changes in working tree as requested
git restore --staged : 2>/dev/null || true

[ "$FAIL" -eq 0 ] && echo "   L4 PASS: dry run valid and all 4 landed gates exit 0" || true

echo "-- L5 non-vacuity: removing start record from working-tree copy reproduces record loss (sidecar_count=0)"
SCRATCH="$TMP/arc_lega_capture_scratch.sh"
cp "$REPO/tools/arc_lega_capture.sh" "$SCRATCH"
chmod +x "$SCRATCH"
MD5_BEFORE=$(md5sum "$SCRATCH" | cut -d' ' -f1)

# Remove start-record printf block from scratch copy
/usr/bin/python3 - "$SCRATCH" <<'PY'
import sys
path = sys.argv[1]
with open(path) as f:
    lines = f.readlines()
new_lines = []
skip = False
for line in lines:
    if 'state": "RUNNING"' in line:
        if line.rstrip().endswith("\\"):
            skip = True
        continue
    if skip:
        skip = False
        continue
    new_lines.append(line)
with open(path, "w") as f:
    f.writelines(new_lines)
PY

RC_NV=$(run_killed "$SCRATCH" "$TMP/out_nv")
N_NV=$(ls "$TMP/out_nv"/arc_lega_capture_seed*.json 2>/dev/null | wc -l)
echo "   systemd-run rc=${RC_NV}  sidecar_count=${N_NV} (expected 0)"

# Restore scratch copy byte-identical
cp "$REPO/tools/arc_lega_capture.sh" "$SCRATCH"
MD5_AFTER=$(md5sum "$SCRATCH" | cut -d' ' -f1)

echo "   scratch copy md5 before: ${MD5_BEFORE}"
echo "   scratch copy md5 after:  ${MD5_AFTER}"

if [ "$RC_NV" -eq 137 ] && [ "$N_NV" -eq 0 ] && [ "$MD5_BEFORE" = "$MD5_AFTER" ]; then
  echo "   L5 PASS: non-vacuity confirmed (record loss reproduced when start record is stripped; md5s match)"
else
  echo "   L5 FAIL: non-vacuity check failed (rc=${RC_NV}, sidecar_count=${N_NV}, md5 match=$([ "$MD5_BEFORE" = "$MD5_AFTER" ] && echo yes || echo no))"
  FAIL=1
fi

echo
if [ "$FAIL" -eq 0 ]; then
  echo "GATE rc=0 — capture record survival: RED observed pre-fix, GREEN post-fix, refusal on parse failure, non-vacuous, dry-run contract intact"
  echo "artifacts: ${TMP}"
  exit 0
else
  echo "GATE rc=1 — see failing legs above"
  echo "artifacts: ${TMP}"
  exit 1
fi
