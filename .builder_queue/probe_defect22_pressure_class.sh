#!/usr/bin/env bash
# .builder_queue/probe_defect22_pressure_class.sh — DEFECT-22, bounded experiment.
#
# QUESTION (the ticket has been circling this since 12:05): the two disturbed arc
# runs of 2026-09-13 (05:1x, SIGSEGV inside CPython's eval loop) sit inside an active
# worker-cgroup memory-pressure window. Every artifact so far is CORRELATION, and one
# thing has never been measured: WHAT FAILURE SHAPE DOES THE MEMORY CAP ACTUALLY
# PRODUCE for this workload? A cgroup cap is enforced by the kernel OOM killer, which
# sends SIGKILL — never SIGSEGV. If that holds, the pressure story cannot explain the
# defect's signature, and one mechanism is eliminated with evidence instead of prose.
#
# SECOND QUESTION (instrument, not defect): the arc's verdict lives in a sidecar written
# by a shell that runs INSIDE the same scope. The Hermes worker scope uses
# OOMPolicy=kill (tools/process_registry.py:273-308), so an OOM there may kill the
# writer too — in which case a memory-pressure arc red writes NO record at all. That is
# exactly the record loss SUITE-ISO-2 fixed for the pytest harness and nobody has
# checked for the arc.
#
# ARMS (same command, same cap, different OOM policy):
#   A) MemoryMax=2200M OOMPolicy=continue -> cap fires, the shell survives, sidecar expected
#   B) MemoryMax=2200M OOMPolicy=kill     -> mirrors the Hermes worker scope
#
# NON-VACUITY: the predicate this probe asserts (PRESSURE=yes / oom_kill_delta>=1) is
# ABSENT in an ordinary leg-A run — the negative control is the most recent green sidecar
# on a real run, which the probe prints alongside the arms.
#
# OUT-OF-TREE ARTIFACTS: the arc writes to /tmp (<- a deliberate kill must never enter the
# arc ledger as a fake red). Only this probe's own stdout copy lands in output/.
#
# Usage:  bash .builder_queue/probe_defect22_pressure_class.sh
set -u

REPO="/home/jericho/projects/zion/projects/visual_audio"
cd "$REPO" || exit 9

SEED="${SEED:-2026091306}"
CAP="${CAP:-2200M}"
OUT_EVIDENCE="${OUT_EVIDENCE:-output/d22_pressure_class_probe.txt}"
HEAD="$(git rev-parse --short HEAD)"
NEG_CONTROL="$(ls -t output/arc_lega_seed*_*.json 2>/dev/null | grep -v pressure | head -1)"

echo "probe :: DEFECT-22 pressure-class + record-survival :: head=${HEAD} seed=${SEED} cap=${CAP}"
echo "kernel OOM semantics under test: cgroup cap -> SIGKILL (128+9=137), NOT SIGSEGV (139)"
echo

run_arm() {
  local ARM="$1" POLICY="$2"
  local DIR="/tmp/d22_pressure_${ARM}"
  local STDOUT="/tmp/d22_pressure_${ARM}_stdout.txt"
  rm -rf "$DIR" "$STDOUT"; mkdir -p "$DIR"

  echo "-- ARM ${ARM}: MemoryMax=${CAP} OOMPolicy=${POLICY}"
  systemd-run --user --scope -q -p "MemoryMax=${CAP}" -p "OOMPolicy=${POLICY}" -- \
    bash -c "cd ${REPO} && OUTDIR=${DIR} SEED=${SEED} VERBOSE=0 bash tools/arc_lega.sh" \
    > "$STDOUT" 2>&1
  local SRC=$?
  echo "   systemd-run rc=${SRC}"

  local SIDE
  SIDE="$(ls "${DIR}"/arc_lega_seed*.json 2>/dev/null | head -1)"
  if [ -n "$SIDE" ]; then
    echo "   SIDECAR=present path=${SIDE}"
    /usr/bin/python3 - "$SIDE" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
ea = d.get("env_after") or {}
eb = d.get("env_before") or {}
print(f"   sidecar rc={d.get('rc')} crashes={d.get('crashes')} seconds={d.get('seconds')}")
print(f"   summary={str(d.get('summary'))[:160]}")
print(f"   oom_kill_delta={d.get('oom_kill_delta')} journal_oom_kill_delta={d.get('journal_oom_kill_delta')}")
print(f"   mem_peak_bytes={ea.get('mem_peak_bytes')} mem_limit_bytes={ea.get('mem_limit_bytes')}")
print(f"   cgroup_after={ea.get('cgroup')}")
print(f"   VERDICT rc_is_sigkill={d.get('rc') == 137} rc_is_sigsegv={d.get('rc') == 139}")
PY
  else
    echo "   SIDECAR=ABSENT (no arc_lega_seed*.json under ${DIR})"
  fi
  [ -s "$STDOUT" ] && { echo "   stdout tail:"; tail -6 "$STDOUT" | sed 's/^/     /'; }
  echo "   PRESSURE_marker_count=$(grep -c 'PRESSURE=yes' "$STDOUT" 2>/dev/null || echo 0)"
  echo
}

if [ -n "$NEG_CONTROL" ]; then
  echo "-- NEGATIVE CONTROL (ordinary run at a comparable head, cap never reached):"
  /usr/bin/python3 - "$NEG_CONTROL" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
print(f"   {sys.argv[1]}")
print(f"   rc={d.get('rc')} oom_kill_delta={d.get('oom_kill_delta')} "
      f"journal_oom_kill_delta={d.get('journal_oom_kill_delta')} "
      f"mem_peak_bytes={(d.get('env_after') or {}).get('mem_peak_bytes')} "
      f"mem_limit_bytes={(d.get('env_after') or {}).get('mem_limit_bytes')}")
print("   PREDICATE absent here => the marker is discriminating, not decorative")
PY
  echo
else
  echo "-- NEGATIVE CONTROL: none found (output/arc_lega_seed*_*.json missing)"
  echo
fi

run_arm A continue
run_arm B kill

echo "PASTE: this stdout is the probe's evidence; copy it with"
echo "  bash .builder_queue/probe_defect22_pressure_class.sh | tee ${OUT_EVIDENCE}"
