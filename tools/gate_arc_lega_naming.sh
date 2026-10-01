#!/usr/bin/env bash
# tools/gate_arc_lega_naming.sh — gate for the DEFECT-22 instrument's artifact naming.
#
# What it decides: does tools/arc_lega.sh preserve every run record, or can a later
# run silently destroy an earlier one? The first version keyed the artifact name on
# the SEED ALONE, so a replay (at a new head, or at the same head to confirm a red)
# overwrote the previous record — exactly the record you replay in order to COMPARE.
#
# Both legs re-execute the real script end to end. PY is a two-call stub (see below)
# so a leg costs <1 s instead of 138 s: the naming/clobbering property is exercised
# without running the 52-file arc.
#
#   RED   — the PRE-FIX script (pinned by SHA, see PREFIX_REV) run twice with the same
#           seed and a DIFFERENT stub nonce: the second run must land on the SAME path
#           and replace its content (md5 differs, one file for two runs). If it does
#           not, the premise of this gate is stale and the gate FAILS — loud.
#   GREEN — the WORKING-TREE script run three times with the same seed: three distinct
#           artifacts must exist and the first record's md5 must be byte-identical
#           afterwards.
#
# The pre-fix script is pinned by REVISION, not by `HEAD:` — measured the hard way: the
# gate was written against `git show HEAD:tools/arc_lega.sh` and, one commit after the
# fix landed (3b96989), it exited 2 with "gate premise stale" because HEAD now contains
# the FIXED script. A gate that cannot run after the change it guards is not a gate.
#
# Exit: 0 = red observed AND green holds. 1 = gate failed. 2 = setup failure.
set -u
REPO=/home/jericho/projects/zion/projects/visual_audio
cd "$REPO" || exit 2
SEED=999001
RUNS=3
# arc_lega.sh was introduced at 6868694 with the seed-only artifact name; that revision is
# the immutable record of the pre-fix behaviour this gate must reproduce.
PREFIX_REV=6868694
FAIL=0

TMP=$(mktemp -d /tmp/arc_lega_gate.XXXXXX) || exit 2
cleanup() {
  rm -f "output/arc_lega_seed${SEED}.txt" "output/arc_lega_seed${SEED}.json"
  rm -rf "$TMP"
}
trap cleanup EXIT

# PY stub: the instrument calls "$PY" twice — once as `-m pytest`, once as the sidecar
# writer. The pytest call is skipped (cheapness) but ECHOES a nonce, so the log at a
# given path has distinguishable content per run; that is what lets the RED leg prove
# "the second run replaced the first record" by content rather than by assumption
# (a plain `PY=/bin/echo` first attempt wrote no sidecar at all and produced a false
# SETUP FAIL — the stub is the instrument's own two-call contract).
STUB="$TMP/pystub.sh"
cat > "$STUB" <<'STUBEOF'
#!/usr/bin/env bash
if [ "${1:-}" = "-m" ]; then echo "gate-stub nonce=${GATE_NONCE:-none}"; echo "gate-stub core-limit=$(ulimit -c)"; exit 0; fi
exec /usr/bin/python3 "$@"
STUBEOF
chmod +x "$STUB"

echo "== gate: arc_lega artifact naming (seed=${SEED}) =="
echo "head=$(git rev-parse --short HEAD)"

# ---------------------------------------------------------------- RED leg
PREFIX="$TMP/arc_lega_prefix.sh"
git show "${PREFIX_REV}:tools/arc_lega.sh" > "$PREFIX" 2>/dev/null || {
  echo "SETUP FAIL: cannot recover the pre-fix script from ${PREFIX_REV}:tools/arc_lega.sh"
  echo "            (shallow clone / missing object? the RED leg needs that revision)"
  exit 2
}
if ! grep -q 'TAG="output/arc_lega_seed${SEED}"' "$PREFIX"; then
  echo "SETUP FAIL: ${PREFIX_REV}'s script does not carry the seed-only TAG line; gate premise stale"
  exit 2
fi
if grep -q '_rerun' "$PREFIX"; then
  echo "SETUP FAIL: ${PREFIX_REV}'s script already has the rerun guard — it is not the pre-fix"
  echo "            behaviour, so the RED leg would not reproduce the collision"
  exit 2
fi
echo "-- RED leg: pre-fix script (rev ${PREFIX_REV}, seed-only name), same seed twice"
GATE_NONCE=one PY="$STUB" SEED=$SEED bash "$PREFIX" >/dev/null 2>&1
RED_P1=$(ls output/arc_lega_seed${SEED}.json 2>/dev/null | head -1)
[ -n "$RED_P1" ] || { echo "SETUP FAIL: pre-fix run wrote no artifact"; exit 2; }
RED_L1="${RED_P1%.json}.txt"
RED_M1=$(md5sum "$RED_L1" | cut -d' ' -f1)
GATE_NONCE=two PY="$STUB" SEED=$SEED bash "$PREFIX" >/dev/null 2>&1
RED_P2=$(ls output/arc_lega_seed${SEED}.json 2>/dev/null | head -1)
RED_L2="${RED_P2%.json}.txt"
RED_M2=$(md5sum "$RED_L2" | cut -d' ' -f1)
RED_FILES=$(ls output/arc_lega_seed${SEED}*.txt output/arc_lega_seed${SEED}*.json 2>/dev/null | wc -l)
echo "   run1 path=$RED_P1 log-md5=$RED_M1"
echo "   run2 path=$RED_P2 log-md5=$RED_M2"
echo "   artifact files for 2 runs: $RED_FILES (pre-fix naming: 2 expected = one pair)"
if [ "$RED_P1" = "$RED_P2" ] && [ "$RED_M1" != "$RED_M2" ]; then
  echo "   RED CONFIRMED: run 2 reused run 1's path and replaced its content — the seed-only name loses history"
elif [ "$RED_M1" = "$RED_M2" ]; then
  echo "   RED NOT OBSERVED: run 2 did not change the record at $RED_P2 (stub nonce not reaching the log?)"
  FAIL=1
else
  echo "   RED NOT OBSERVED: pre-fix runs did not collide ($RED_P1 vs $RED_P2)"
  FAIL=1
fi

# -------------------------------------------------------------- GREEN leg
echo "-- GREEN leg: working-tree script, same seed x$RUNS, artifacts in $TMP"
OUTDIR="$TMP" GATE_NONCE=r1 PY="$STUB" SEED=$SEED bash tools/arc_lega.sh > "$TMP/run1.out" 2>&1
FIRST=$(ls "$TMP"/arc_lega_seed${SEED}*.json 2>/dev/null | head -1)
[ -n "$FIRST" ] || { echo "GREEN FAIL: run 1 wrote no artifact"; exit 1; }
GREEN_M1=$(md5sum "$FIRST" | cut -d' ' -f1)
for i in $(seq 2 "$RUNS"); do
  OUTDIR="$TMP" GATE_NONCE=r$i PY="$STUB" SEED=$SEED bash tools/arc_lega.sh > "$TMP/run$i.out" 2>&1
done
G_FILES=$(ls "$TMP"/arc_lega_seed${SEED}*.json 2>/dev/null | wc -l)
GREEN_M2=$(md5sum "$FIRST" | cut -d' ' -f1)
SHORT_HEAD=$(git rev-parse --short HEAD)
echo "   artifacts: $(ls "$TMP"/arc_lega_seed${SEED}*.json 2>/dev/null | xargs -n1 basename | tr '\n' ' ')"
echo "   first record ($(basename "$FIRST")) md5 before/after later runs: $GREEN_M1 / $GREEN_M2"
if [ "$G_FILES" -eq "$RUNS" ]; then
  echo "   GREEN: every run kept its own record ($G_FILES files for $RUNS runs)"
else
  echo "   GREEN FAIL: $G_FILES file(s) for $RUNS runs — the instrument still loses records"
  FAIL=1
fi
if [ "$GREEN_M1" = "$GREEN_M2" ]; then
  echo "   GREEN: the earlier record is byte-identical after $((RUNS - 1)) later run(s) (no clobber)"
else
  echo "   GREEN FAIL: a later run rewrote the earlier record"
  FAIL=1
fi
case "$(basename "$FIRST")" in
  arc_lega_seed${SEED}_${SHORT_HEAD}*) echo "   GREEN: name carries the head ($SHORT_HEAD)" ;;
  *) echo "   GREEN FAIL: name does not carry the head: $(basename "$FIRST")"; FAIL=1 ;;
esac
# Sidecar must still be loadable JSON with the expected keys (the record is the point).
"$STUB" - "$FIRST" <<'PY' || FAIL=1
import json, sys
d = json.load(open(sys.argv[1]))
need = {"seed", "head", "rc", "crashes", "seconds", "summary"}
missing = need - d.keys()
if missing:
    print(f"   GREEN FAIL: sidecar missing keys {sorted(missing)}"); raise SystemExit(1)
print(f"   GREEN: sidecar loads, seed={d['seed']} head={d['head']} rc={d['rc']} started_utc={d.get('started_utc')}")
PY

# ------------------------------------------------- CORE-CAPTURE leg (DEFECT-22)
# Added 2026-09-13. A SIGSEGV in this run is the only evidence of the arc's
# intermittent crash, and a core is written only when RLIMIT_CORE is non-zero at
# the moment the process dies. Measured (apport.log): the 05:18 pytest SIGSEGV
# left a recoverable 1.19 GB core; later same-day crashes logged "core limit 0"
# and left nothing. Both legs below start from an ambient limit of 0 — the only
# difference is whether the runner raises it.
PRE_INSTRUMENT_REV=cf9ae6d
CORE_SEED=999002
echo "-- CORE leg: runner must raise RLIMIT_CORE above an ambient 0 (seed=${CORE_SEED})"
PRE_CORE="$TMP/arc_lega_precore.sh"
git show "${PRE_INSTRUMENT_REV}:tools/arc_lega.sh" > "$PRE_CORE" 2>/dev/null || {
  echo "SETUP FAIL: cannot recover ${PRE_INSTRUMENT_REV}:tools/arc_lega.sh"
  exit 2
}
if grep -q 'ulimit -c' "$PRE_CORE"; then
  echo "SETUP FAIL: ${PRE_INSTRUMENT_REV} already raises the core limit — premise stale"
  exit 2
fi
( ulimit -c 0; OUTDIR="$TMP" GATE_NONCE=pre PY="$STUB" SEED=$CORE_SEED bash "$PRE_CORE" >/dev/null 2>&1 )
RED_CORE_LOG=$(ls "$TMP"/arc_lega_seed${CORE_SEED}*.txt 2>/dev/null | head -1)
if [ -z "$RED_CORE_LOG" ]; then echo "SETUP FAIL: pre-instrument run wrote no log"; exit 2; fi
RED_LIMIT=$(grep -o 'gate-stub core-limit=[^ ]*' "$RED_CORE_LOG" | head -1)
GREEN_CORE_LOG="${FIRST%.json}.txt"
GREEN_LIMIT=$(grep -o 'gate-stub core-limit=[^ ]*' "$GREEN_CORE_LOG" | head -1)
echo "   pre-instrument runner ($PRE_INSTRUMENT_REV): ${RED_LIMIT:-<no line>}"
echo "   working-tree runner:                        ${GREEN_LIMIT:-<no line>}"
if [ "$RED_LIMIT" = "gate-stub core-limit=0" ]; then
  echo "   RED CONFIRMED: without the line the ambient 0 passes through a crash (nothing to diagnose)"
else
  echo "   RED NOT OBSERVED: pre-instrument runner reported '${RED_LIMIT:-<none>}'"
  FAIL=1
fi
if [ "$GREEN_LIMIT" = "gate-stub core-limit=unlimited" ]; then
  echo "   GREEN: working-tree runner raises it to unlimited"
else
  echo "   GREEN FAIL: working-tree runner reported '${GREEN_LIMIT:-<none>}'"
  FAIL=1
fi

echo "-- gate rc: $FAIL (0 = RED observed and GREEN holds)"
exit "$FAIL"
