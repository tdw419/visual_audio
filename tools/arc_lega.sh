#!/usr/bin/env bash
# tools/arc_lega.sh — canonical, REPLAYABLE arc leg A runner.
#
# Why this exists (DEFECT-22, 2026-09-13):
#   pytest-randomly 4.0.1 is loaded for /usr/bin/python3 (MEASURED this tick:
#   `--co -q --randomly-seed=111` vs `=222` on tests/test_gh6_syscalls.py gives
#   different collection orders), so every arc leg A run so far ran the 52 files
#   in a DIFFERENT order — and the `-q` runs never recorded which order. That is
#   why the 2026-09-13 SIGSEGV (2 of 11 runs, both at 194844c) cannot be replayed:
#   its seed was never logged. A gate whose order varies run to run produces reds
#   that cannot be reproduced, and greens that do not mean the same thing twice.
#
# This runner always pins AND records the seed, so any future red is replayable:
#   tools/arc_lega.sh                 # fresh random seed, logged to the log + sidecar
#   SEED=1210907384 tools/arc_lega.sh # replay exactly that order
#
# Every run gets its OWN artifact pair, named <OUTDIR>/arc_lega_seed<SEED>_<HEAD>
# (plus _rerun<N> if that exact seed+head already has a record). Rationale, measured
# 2026-09-13: the first version keyed the name on the SEED ALONE, so replaying a seed
# at a new head overwrote and destroyed the earlier head's record
# (output/arc_lega_seed1210907384.* moved 81f0a42 -> 6868694). A replay is precisely
# the experiment whose verdict you want to COMPARE, so it must never clobber.
#   OUTDIR=/tmp/x SEED=… tools/arc_lega.sh   # redirect artifacts (used by the gate)
#
# Exit code is pytest's. Crash count and a JSON sidecar are written next to the log.
# NOTE: this is an instrument, not a fix. It does not remove the order dependence;
# it makes the order knowable. Unpinned gate runs keep the intermittency.
set -u
cd /home/jericho/projects/zion/projects/visual_audio || exit 9

# Core capture (added 2026-09-13, DEFECT-22): a SIGSEGV in this run is the only
# evidence of the arc's intermittent crash, and a core is written only if
# RLIMIT_CORE is non-zero when the process dies. Measured (apport.log
# 2026-09-13): the 05:18 pytest SIGSEGV left a recoverable 1.19 GB core in
# /var/crash/..._pytest___init__.py.1000.crash, while later same-day crashes
# logged "core limit 0" and left nothing. This shell's soft limit is set
# explicitly so the property is deterministic instead of environmental.
# Recover a core with:  /usr/bin/python3 tools/apport_core_unpack.py <report.crash> <out.core>
# Caveat: apport still refuses a SECOND report for the same executable while the
# first is unseen ("skipping to avoid disk usage DoS") — see
# systems/RECEIPT_DEFECT22_CORE_RECOVERED.md.
ulimit -c unlimited 2>/dev/null || true

SEED="${SEED:-$RANDOM$RANDOM}"
VERBOSE="${VERBOSE:-1}"
PY="${PY:-/usr/bin/python3}"

# Selector. WIDENED 2026-09-16 (DEFECT-30 follow-up): the old test_defect1* glob
# predates the defect20/defect23/defect-d clusters — a stale-red pin in
# tests/test_defect23_pte_acceptance.py survived arc-green for a full tick
# because the file was invisible to this selector. Kept as a GLOB (not a hand
# list) so future test_defect* files are covered by construction; parity with
# the mirrored copy in tools/arc_lega_capture.sh and with the audit's
# _get_arc_files() is pinned by tests/test_arc_selector_parity.py.
# Exclusions come from the arc's own dependency closure: glass_box needs a live
# surface, gh24_s2_mcp needs py3.12-only mcp transport coverage elsewhere;
# live_smoke is non-blocking model probe excluded via -m "not live_smoke").
FILES=$(ls tests/test_gh*.py tests/test_bk*.py tests/test_eng*.py tests/test_defect*.py \
        | grep -vE 'glass_box|gh24_s2_mcp')

HEAD=$(git rev-parse --short HEAD)
OUTDIR="${OUTDIR:-output}"
mkdir -p "$OUTDIR"
TAG="${OUTDIR}/arc_lega_seed${SEED}_${HEAD}"
# Never clobber a record: a same-(seed,head) replay is the run whose verdict you
# want to compare against, so it gets its own file instead of overwriting.
if [ -e "${TAG}.json" ]; then
  N=2
  while [ -e "${TAG}_rerun${N}.json" ]; do N=$((N + 1)); done
  TAG="${TAG}_rerun${N}"
fi
LOG="${TAG}.txt"
JSON="${TAG}.json"
LOAD_BEFORE=$(cut -d' ' -f1-3 /proc/loadavg)

ARGS=(-q --tb=line -m "not live_smoke" -p randomly --randomly-seed="$SEED")
if [ "$VERBOSE" = "1" ]; then ARGS=(-v --tb=line -m "not live_smoke" -p randomly --randomly-seed="$SEED"); fi

T0=$(date +%s)
START_ISO=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# Verdict survival (added 2026-09-13 13:0x, from a MEASURED loss): the arc normally
# runs inside a Hermes worker scope (MemoryMax 4 GiB, OOMPolicy=kill;
# tools/process_registry.py:273-308) and leg A's own peak is 2.97-3.93 GB of that cap
# (91.5% in the heavier sample) — so a cap OOM is a live possibility for this very run.
# Under OOMPolicy=kill the kernel kills the WHOLE scope, this shell included, so the
# sidecar written after pytest was never reached: measured with
# .builder_queue/probe_defect22_pressure_class.sh arm B (MemoryMax=2200M,
# OOMPolicy=kill) -> SIDECAR=ABSENT, only a partial .txt left, PRESSURE marker never
# printed. This start record is written BEFORE pytest starts and is overwritten by the
# full record on a normal exit, so a killed run leaves a parseable JSON naming its
# seed+head (a recoverable "this run existed and was killed") instead of nothing.
# Written with printf, not $PY: a third interpreter invocation would have to be routed
# by the stub-PY legs in tools/gate_arc_lega_naming.sh.
printf '{"state": "RUNNING", "seed": %s, "head": "%s", "started_utc": "%s", "rc": null, "crashes": null, "note": "start record - a run killed inside a scope with OOMPolicy=kill stops here; replay with SEED=<seed> tools/arc_lega.sh"}\n' \
  "$SEED" "$HEAD" "$START_ISO" > "$JSON"

BEFORE=$(bash tools/arc_env_telemetry.sh "$START_ISO")

if [ "${TELEMETRY_ONLY:-0}" = "1" ]; then
  T1=$(date +%s)
  AFTER=$(bash tools/arc_env_telemetry.sh "$START_ISO")
  LOG=""
  PARSE_OUT=$("$PY" - "$JSON" "$SEED" "$HEAD" "$((T1 - T0))" "$LOG" "$LOAD_BEFORE" "$START_ISO" "$BEFORE" "$AFTER" <<'PY'
import json, sys
j, seed, head, secs, log, load, start, before_raw, after_raw = sys.argv[1:10]

try:
    before = json.loads(before_raw)
except Exception:
    before = None

try:
    after = json.loads(after_raw)
except Exception:
    after = None

oom_delta = None
if before and after and before.get("oom_kill_total") is not None and after.get("oom_kill_total") is not None:
    oom_delta = after["oom_kill_total"] - before["oom_kill_total"]

j_delta = after.get("journal_oom_kill_window") if after else None

mem_peak = after.get("mem_peak_bytes") if after else None
load_after = after.get("loadavg") if after else None

sidecar = {
    "state": "DONE",
    "seed": int(seed),
    "head": head,
    "rc": None,
    "crashes": 0,
    "seconds": int(secs),
    "summary": "",
    "log": log,
    "loadavg_before": load,
    "started_utc": start,
    "dry_run": True,
    "env_before": before,
    "env_after": after,
    "oom_kill_delta": oom_delta,
    "journal_oom_kill_delta": j_delta,
    "note": "seed pins pytest-randomly order; replay with SEED=<seed> tools/arc_lega.sh "
            "(each run writes its own seed+head artifact, never clobbering)"
}
with open(j, "w") as f:
    json.dump(sidecar, f, indent=2)

oom_s = str(oom_delta) if oom_delta is not None else "null"
j_s = str(j_delta) if j_delta is not None else "null"
peak_s = str(mem_peak) if mem_peak is not None else "null"
load_s = str(load_after) if load_after is not None else "null"
pressure = " PRESSURE=yes" if ((oom_delta is not None and oom_delta > 0) or (j_delta is not None and j_delta > 0)) else ""
print(f"env: oom_kill_delta={oom_s} journal_oom_kill_delta={j_s} mem_peak={peak_s} loadavg_after={load_s}{pressure}")
PY
  )
  echo "arc leg A :: seed=${SEED} head=${HEAD} rc=null crashes=0 secs=$((T1 - T0))"
  echo "  Using --randomly-seed=${SEED} (telemetry only)"
  echo "  <no summary line>"
  echo "  log=${LOG} sidecar=${JSON}"
  echo "$PARSE_OUT"
  exit 0
fi

"$PY" -m pytest $FILES "${ARGS[@]}" > "$LOG" 2>&1
RC=$?
T1=$(date +%s)
AFTER=$(bash tools/arc_env_telemetry.sh "$START_ISO")

CRASHES=$(grep -c 'Fatal Python error' "$LOG")
SUMMARY=$(grep -E '[0-9]+ (passed|failed)' "$LOG" | tail -1)
SEEDLINE=$(grep -m1 'Using --randomly-seed' "$LOG" || echo "Using --randomly-seed=${SEED} (header suppressed)")

ENV_LINE=$("$PY" - "$JSON" "$SEED" "$HEAD" "$RC" "$CRASHES" "$((T1 - T0))" "$SUMMARY" "$LOG" "$LOAD_BEFORE" "$START_ISO" "$BEFORE" "$AFTER" <<'PY'
import json, sys
j, seed, head, rc, crashes, secs, summary, log, load, start, before_raw, after_raw = sys.argv[1:13]

try:
    before = json.loads(before_raw)
except Exception:
    before = None

try:
    after = json.loads(after_raw)
except Exception:
    after = None

oom_delta = None
if before and after and before.get("oom_kill_total") is not None and after.get("oom_kill_total") is not None:
    oom_delta = after["oom_kill_total"] - before["oom_kill_total"]

j_delta = after.get("journal_oom_kill_window") if after else None

mem_peak = after.get("mem_peak_bytes") if after else None
load_after = after.get("loadavg") if after else None

sidecar = {
    "state": "DONE",
    "seed": int(seed),
    "head": head,
    "rc": int(rc),
    "crashes": int(crashes),
    "seconds": int(secs),
    "summary": summary,
    "log": log,
    "loadavg_before": load,
    "started_utc": start,
    "dry_run": False,
    "env_before": before,
    "env_after": after,
    "oom_kill_delta": oom_delta,
    "journal_oom_kill_delta": j_delta,
    "note": "seed pins pytest-randomly order; replay with SEED=<seed> tools/arc_lega.sh "
            "(each run writes its own seed+head artifact, never clobbering)"
}
with open(j, "w") as f:
    json.dump(sidecar, f, indent=2)

oom_s = str(oom_delta) if oom_delta is not None else "null"
j_s = str(j_delta) if j_delta is not None else "null"
peak_s = str(mem_peak) if mem_peak is not None else "null"
load_s = str(load_after) if load_after is not None else "null"
pressure = " PRESSURE=yes" if ((oom_delta is not None and oom_delta > 0) or (j_delta is not None and j_delta > 0)) else ""
print(f"env: oom_kill_delta={oom_s} journal_oom_kill_delta={j_s} mem_peak={peak_s} loadavg_after={load_s}{pressure}")
PY
)

echo "arc leg A :: seed=${SEED} head=${HEAD} rc=${RC} crashes=${CRASHES} secs=$((T1 - T0))"
echo "  ${SEEDLINE}"
echo "  ${SUMMARY:-<no summary line>}"
echo "  log=${LOG} sidecar=${JSON}"
echo "$ENV_LINE"
exit "$RC"
