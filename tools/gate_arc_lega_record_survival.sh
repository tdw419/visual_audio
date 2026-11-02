#!/usr/bin/env bash
# tools/gate_arc_lega_record_survival.sh — DEFECT-22 instrument gate (record survival).
#
# PROPERTY UNDER TEST: a leg-A run that is killed by the kernel OOM killer inside a
# scope with OOMPolicy=kill must still leave a parseable machine-readable record naming
# its seed and head. Before this change it left nothing (measured: probe arm B,
# .builder_queue/probe_defect22_pressure_class.sh) — the sidecar was written only after
# pytest returned, and the kill takes the writing shell with it.
#
# Legs:
#   L0 premise   the pinned pre-fix revision really lacks the start record (else the
#                RED leg is stale and this gate would green itself forever)
#   L1 RED       pinned pre-fix runner + MemoryMax cap + OOMPolicy=kill -> NO *.json
#   L2 GREEN     working-tree runner, identical scope/params -> *.json parses,
#                state=RUNNING, int seed, head, started_utc
#   L3 no-regress TELEMETRY_ONLY=1 dry run -> rc 0 and a full sidecar with state=DONE,
#                dry_run=true (the added key did not disturb the landed contract)
#   L4 gates     the two landed instrument gates still exit 0
#
# NON-VACUITY: L1 is the falsifier — the same command at the pinned pre-fix revision
# genuinely loses the record, so L2 is not a tautology. The parameter CAP is the
# implementer's choice (any cap that OOMs works; 1200M just makes the leg fast): a
# tighter cap than the defect probe's 2200M, same mechanism.
#
# Usage:  bash tools/gate_arc_lega_record_survival.sh     (exit 0 = all legs pass)
set -u

REPO="/home/jericho/projects/zion/projects/visual_audio"
PRE_FIX_REV="${PRE_FIX_REV:-070e004}"   # HEAD when the loss was measured
CAP="${CAP:-1200M}"
TMP="$(mktemp -d /tmp/gate_d22_survival.XXXXXX)"
FAIL=0

cd "$REPO" || exit 9

echo "-- L0 premise: pinned pre-fix runner (${PRE_FIX_REV}) lacks the start record"
git show "${PRE_FIX_REV}:tools/arc_lega.sh" > "$TMP/arc_lega_pre.sh" 2>/dev/null
if [ ! -s "$TMP/arc_lega_pre.sh" ]; then
  echo "   L0 SETUP FAIL: cannot recover tools/arc_lega.sh at ${PRE_FIX_REV}"; exit 2
fi
if grep -q '"state": "RUNNING"' "$TMP/arc_lega_pre.sh"; then
  echo "   L0 SETUP FAIL: the pinned revision already writes a start record; RED leg stale"; exit 2
fi
if ! grep -q '"state": "RUNNING"' tools/arc_lega.sh; then
  echo "   L0 SETUP FAIL: the working-tree runner has no start record either"; exit 2
fi
echo "   L0 PASS: pinned copy has no 'state\": \"RUNNING\"', working tree does"

run_killed() {  # $1 = runner path, $2 = outdir
  local OUT="$1" DIR="$2"
  rm -rf "$DIR"; mkdir -p "$DIR"
  systemd-run --user --scope -q -p "MemoryMax=${CAP}" -p "OOMPolicy=kill" -- \
    bash -c "cd ${REPO} && OUTDIR=${DIR} SEED=${SEED} VERBOSE=0 bash ${OUT}" \
    > "$TMP/$(basename "$DIR").stdout" 2>&1
  echo "$?"
}

SEED="${SEED:-2026091307}"

echo "-- L1 RED: pre-fix runner under MemoryMax=${CAP} OOMPolicy=kill"
RC1=$(run_killed "$TMP/arc_lega_pre.sh" "$TMP/out_pre")
N1=$(ls "$TMP/out_pre"/arc_lega_seed*.json 2>/dev/null | wc -l)
echo "   systemd-run rc=${RC1}  sidecar_count=${N1} (expected 0)"
if [ "$N1" -eq 0 ]; then
  echo "   L1 PASS (RED observed): the property is genuinely absent pre-fix"
else
  echo "   L1 FAIL: pre-fix runner left a sidecar; the RED leg does not discriminate"
  FAIL=1
fi

echo "-- L2 GREEN: working-tree runner, identical scope and params"
RC2=$(run_killed "$REPO/tools/arc_lega.sh" "$TMP/out_fix")
SIDE=$(ls "$TMP/out_fix"/arc_lega_seed*.json 2>/dev/null | head -1)
echo "   systemd-run rc=${RC2}  sidecar=${SIDE:-<none>}"
if [ -z "$SIDE" ]; then
  echo "   L2 FAIL: killed run still leaves no record"; FAIL=1
else
  /usr/bin/python3 - "$SIDE" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception as e:
    print(f"   L2 FAIL: sidecar does not parse: {e}"); raise SystemExit(1)
need = {"state", "seed", "head", "started_utc"}
missing = sorted(k for k in need if k not in d)
if missing or d.get("state") != "RUNNING" or not isinstance(d.get("seed"), int):
    print(f"   L2 FAIL: keys missing={missing} state={d.get('state')!r} seed={d.get('seed')!r}")
    raise SystemExit(1)
print(f"   L2 PASS: killed run left state={d['state']} seed={d['seed']} head={d['head']} "
      f"started_utc={d['started_utc']}")
PY
  [ $? -ne 0 ] && FAIL=1
fi

echo "-- L3 no-regression: TELEMETRY_ONLY=1 dry run still writes the full record"
DRY="$TMP/out_dry"
TELEMETRY_ONLY=1 OUTDIR="$DRY" SEED=1 bash tools/arc_lega.sh > "$TMP/dry.stdout" 2>&1
DRC=$?
DSIDE=$(ls "$DRY"/arc_lega_seed*.json 2>/dev/null | head -1)
echo "   rc=${DRC} sidecar=${DSIDE:-<none>} (expected rc=0, one sidecar)"
if [ "$DRC" -ne 0 ] || [ -z "$DSIDE" ]; then
  echo "   L3 FAIL: dry-run contract disturbed"; FAIL=1
else
  /usr/bin/python3 - "$DSIDE" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
ok = d.get("state") == "DONE" and d.get("dry_run") is True and d.get("rc") is None
print(f"   L3 {'PASS' if ok else 'FAIL'}: state={d.get('state')} dry_run={d.get('dry_run')} rc={d.get('rc')}")
raise SystemExit(0 if ok else 1)
PY
  [ $? -ne 0 ] && FAIL=1
fi

echo "-- L4 no-regression: the two landed instrument gates still exit 0"
for G in tools/gate_arc_lega_naming.sh tools/gate_arc_lega_telemetry.sh; do
  bash "$G" > "$TMP/$(basename "$G").out" 2>&1
  G_RC=$?
  echo "   $(basename "$G") rc=${G_RC}"
  [ "$G_RC" -ne 0 ] && { echo "   L4 FAIL: $(basename "$G")"; tail -5 "$TMP/$(basename "$G").out" | sed 's/^/     /'; FAIL=1; }
done
[ "$FAIL" -eq 0 ] && echo "   L4 PASS" || true

echo
if [ "$FAIL" -eq 0 ]; then
  echo "GATE rc=0 — record survival: RED observed pre-fix, GREEN post-fix, dry-run contract intact"
else
  echo "GATE rc=1 — see failing legs above"; exit 1
fi
echo "artifacts: ${TMP}"
