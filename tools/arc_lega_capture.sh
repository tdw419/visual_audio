#!/usr/bin/env bash
# tools/arc_lega_capture.sh — live SIGSEGV capture instrument for arc leg A under GDB.
#
# Why this exists (DEFECT-22, 2026-09-13):
#   The intermittent arc leg A SIGSEGV leaves cores whose siginfo is consumed by Python's
#   faulthandler before re-raising, destroying si_addr and native frame context.
#   This instrument launches arc leg A directly under GDB with handle SIGSEGV stop nopass,
#   capturing the faulting instruction, si_addr, and concrete library symbols live.
#
set -u
cd /home/jericho/projects/zion/projects/visual_audio || exit 9

# Raise core limit (mirroring tools/arc_lega.sh:42) — cores are WANTED here: a real RED's raw
# core in /var/lib/apport/coredump is the fallback record if live capture misses.
#
# OPERATOR RULE for deliberate crasher probes (PY=<crasher stub>), measured 2026-09-13 09:23:
# `ulimit -c 0` suppresses the ~7 MB raw core but NOT the apport report — apport logs
# "core limit 0, dump mode 1" and writes /var/crash/<python3.12>.crash anyway. While such a
# report sits "unseen", apport refuses to record the NEXT crash of that executable ("already
# exists and unseen, skipping"), and the arc's interpreter IS python3.12. So after any
# deliberate-crash run, the fixture report must leave /var/crash:
#     ls /var/crash/*.crash && mv /var/crash/*.crash /tmp/d22q/
# The gate (tools/gate_arc_lega_capture.sh, L6) does this for itself, and since 2026-09-13 09:4x
# THIS path does it too (see the hygiene block below, `sweep_fixture_reports`) — before and after
# every run — so the manual move is a fallback, not a required step.
# Receipt: systems/RECEIPT_DEFECT22_APPORT_PATH_HYGIENE.md
ulimit -c unlimited 2>/dev/null || true

# Environmental knobs (mirroring tools/arc_lega.sh:44-46)
SEED="${SEED:-$RANDOM$RANDOM}"
VERBOSE="${VERBOSE:-1}"
PY="${PY:-/usr/bin/python3}"

# Mirror of tools/arc_lega.sh FILES selector (WIDENED 2026-09-16, DEFECT-30
# follow-up: test_defect1* predates the defect20/defect23 clusters).
# Keep byte-identical to prevent drift; parity is pinned by
# tests/test_arc_selector_parity.py:
FILES=$(ls tests/test_gh*.py tests/test_bk*.py tests/test_eng*.py tests/test_defect*.py \
        | grep -vE 'glass_box|gh24_s2_mcp')

HEAD=$(git rev-parse --short HEAD)
OUTDIR="${OUTDIR:-output}"
mkdir -p "$OUTDIR"

# Mirror of tools/arc_lega.sh:58-65 (artifact naming and no-clobber discipline)
TAG="${OUTDIR}/arc_lega_capture_seed${SEED}_${HEAD}"
if [ -e "${TAG}.json" ]; then
  N=2
  while [ -e "${TAG}_rerun${N}.json" ]; do N=$((N + 1)); done
  TAG="${TAG}_rerun${N}"
fi
LOG="${TAG}.txt"
JSON="${TAG}.json"
GDB_LOG="${TAG}.gdb.txt"
LOAD_BEFORE=$(cut -d' ' -f1-3 /proc/loadavg)

# ------------------------------------------------- apport capture-path hygiene (2026-09-13)
# The operator rule above (lines 13-24) told the operator to move the fixture report out of
# /var/crash by hand; this path did not, while the gate already swept for itself (its L6 leg).
# Measured 2026-09-13 09:35: the crasher legs occupy the shared apport report path for ~5.25 s
# of a 7.1 s run, and a real python3.12 crash landing in such a window has its report suppressed
# ("already exists and unseen, skipping to avoid disk usage DoS"). A real RED inside THIS
# instrument is the case the instrument exists for, so the sweep is now enforced here: before the
# run (clear a stale probe report) and after it (leave the path clear for the next crash).
# The predicate is the report's OWN ProcCmdline — the gate's L6a proves selectivity (a report that
# only MENTIONS the fixture in a body field survives). Nothing is deleted: swept reports are moved
# to the quarantine dir, because a swept report may still be evidence.
CRASH_DIR="${CRASH_DIR:-/var/crash}"
FIXTURE_TAG="${FIXTURE_TAG:-faulthandler_segv_fixture.py}"
QUARANTINE_DIR="${QUARANTINE_DIR:-/tmp/d22q}"

is_fixture_report() {
  grep -a -m 1 '^ProcCmdline:' "$1" 2>/dev/null | grep -qa "$FIXTURE_TAG"
}

sweep_fixture_reports() {
  local moved=0 f
  mkdir -p "$QUARANTINE_DIR" 2>/dev/null || { echo 0; return; }
  for f in "$CRASH_DIR"/*.crash; do
    [ -f "$f" ] || continue
    if is_fixture_report "$f"; then
      mv "$f" "$QUARANTINE_DIR/$(basename "$f").$RANDOM" 2>/dev/null && moved=$((moved + 1))
    fi
  done
  echo "$moved"
}

count_fixture_reports() {
  local n=0 f
  for f in "$CRASH_DIR"/*.crash; do
    [ -f "$f" ] || continue
    is_fixture_report "$f" && n=$((n + 1))
  done
  echo "$n"
}

SWEPT_BEFORE=$(sweep_fixture_reports)

# Mirror of tools/arc_lega.sh:70-71 (pytest ARGS block)
# Keep byte-identical to prevent drift:
ARGS=(-q --tb=line -m "not live_smoke" -p randomly --randomly-seed="$SEED")
if [ "$VERBOSE" = "1" ]; then ARGS=(-v --tb=line -m "not live_smoke" -p randomly --randomly-seed="$SEED"); fi

T0=$(date +%s)
START_ISO=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# Verdict survival (DEFECT-22c, follow-on to 9ef7b49, 2026-09-13): the capture instrument
# runs under GDB inside a Hermes worker scope (MemoryMax 4 GiB, OOMPolicy=kill) where leg A
# peaks at 2.97-3.93 GB (91.5% in the heavier sample). Under OOMPolicy=kill the kernel kills
# the whole scope including this shell before the terminal parse block is reached.
# This start record is written BEFORE GDB/pytest starts and is overwritten by the full
# record on normal exit, so a killed run leaves a parseable JSON naming its seed+head
# instead of nothing.
# Written with printf, not $PY: a third interpreter invocation would have to be routed
# by the stub-PY legs in tools/gate_arc_lega_naming.sh.
printf '{"state": "RUNNING", "seed": %s, "head": "%s", "started_utc": "%s", "rc": null, "crashes": null, "note": "start record - a run killed inside a scope with OOMPolicy=kill stops here; replay with SEED=<seed> tools/arc_lega_capture.sh"}\n' \
  "$SEED" "$HEAD" "$START_ISO" > "$JSON"

BEFORE=$(bash tools/arc_env_telemetry.sh "$START_ISO")

# If PY is a script rather than an ELF binary (e.g. gate stub), run via /bin/bash so GDB can load it
GDB_EXEC=("$PY")
if [ -f "$PY" ] && ! head -c 4 "$PY" | grep -q $'\x7fELF'; then
  GDB_EXEC=(/bin/bash "$PY")
fi

if [ "${TELEMETRY_ONLY:-0}" = "1" ]; then
  T1=$(date +%s)
  AFTER=$(bash tools/arc_env_telemetry.sh "$START_ISO")
  LOG=""
  GDB_LOG=""
  PARSE_OUT=$("${GDB_EXEC[@]}" - "$JSON" "$SEED" "$HEAD" "$((T1 - T0))" "$LOG" "$GDB_LOG" "$LOAD_BEFORE" "$START_ISO" "$BEFORE" "$AFTER" <<'PY'
import json, sys
json_path, seed, head, seconds, log_path, gdb_log_path, load_before, start_iso, before_raw, after_raw = sys.argv[1:11]

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

capture_obj = {
    "segv_caught": False,
    "signal": None,
    "pc": None,
    "si_addr": None,
    "pc_symbol": None,
}

sidecar = {
    "state": "DONE",
    "seed": int(seed),
    "head": head,
    "rc": None,
    "crashes": 0,
    "faulthandler_crashes": 0,
    "crash_count_source": "none",
    "seconds": int(seconds),
    "summary": "",
    "log": log_path,
    "gdb_log": gdb_log_path,
    "started_utc": start_iso,
    "loadavg_before": load_before,
    "dry_run": True,
    "capture": capture_obj,
    "env_before": before,
    "env_after": after,
    "oom_kill_delta": oom_delta,
    "journal_oom_kill_delta": j_delta,
}

with open(json_path, "w") as f:
    json.dump(sidecar, f, indent=2)

oom_s = str(oom_delta) if oom_delta is not None else "null"
j_s = str(j_delta) if j_delta is not None else "null"
peak_s = str(mem_peak) if mem_peak is not None else "null"
load_s = str(load_after) if load_after is not None else "null"
pressure = " PRESSURE=yes" if ((oom_delta is not None and oom_delta > 0) or (j_delta is not None and j_delta > 0)) else ""

print("0 no none none")
print(f"env: oom_kill_delta={oom_s} journal_oom_kill_delta={j_s} mem_peak={peak_s} loadavg_after={load_s}{pressure}")
PY
  )
  read -r RC SEGV_STR SI_ADDR_STR PC_STR <<< "$PARSE_OUT"
  ENV_LINE=$(sed -n '2p' <<< "$PARSE_OUT")
  echo "arc leg A (live capture) :: seed=${SEED} head=${HEAD} rc=null segv=${SEGV_STR} si_addr=${SI_ADDR_STR} pc=${PC_STR}"
  echo "  apport path: fixture reports swept before=${SWEPT_BEFORE} after=0, still present=0 (quarantine ${QUARANTINE_DIR})"
  echo "  Using --randomly-seed=${SEED} (telemetry only)"
  echo "  <no summary line>"
  echo "  log=${LOG} sidecar=${JSON} gdb_log=${GDB_LOG}"
  echo "$ENV_LINE"
  exit 0
fi

# Run under GDB using tools/gdb_segv_capture.gdb
gdb -q -batch -iex "set debuginfod enabled off" -x tools/gdb_segv_capture.gdb \
    --args "${GDB_EXEC[@]}" -m pytest $FILES "${ARGS[@]}" > "$GDB_LOG" 2>&1
GDB_RC=$?
T1=$(date +%s)
AFTER=$(bash tools/arc_env_telemetry.sh "$START_ISO")

# Extract run log from gdb transcript (strip gdb capture block at footer)
sed '/^DEFECT22_CAPTURE_START/,$d' "$GDB_LOG" > "$LOG"

CRASHES=$(grep -c 'Fatal Python error' "$LOG")
SUMMARY=$(grep -E '[0-9]+ (passed|failed)' "$LOG" | tail -1)
SEEDLINE=$(grep -m1 'Using --randomly-seed' "$LOG" || echo "Using --randomly-seed=${SEED} (header suppressed)")

# Parse GDB transcript and write sidecar JSON.
# The parse step is launched the same way the inferior is (GDB_EXEC): a non-ELF PY (a gate stub
# script) must go through /bin/bash here too. Measured 2026-09-13 09:1x: with a bare `"$PY" - ...`
# and a non-executable stub, this step died with "Permission denied", the run left a capture
# transcript with NO sidecar, and the summary printed an empty rc — an instrument failure that
# looked like a verdict. Same guard as the gdb leg, so the two can never disagree.
PARSE_OUT=$("${GDB_EXEC[@]}" - "$GDB_LOG" "$JSON" "$SEED" "$HEAD" "$CRASHES" "$((T1 - T0))" "${SUMMARY:-}" "$LOG" "$LOAD_BEFORE" "$START_ISO" "$GDB_RC" "$BEFORE" "$AFTER" <<'PY'
import json, re, sys

gdb_log_path = sys.argv[1]
json_path = sys.argv[2]
seed = int(sys.argv[3])
head = sys.argv[4]
crashes = int(sys.argv[5])
seconds = int(sys.argv[6])
summary = sys.argv[7]
log_path = sys.argv[8]
load_before = sys.argv[9]
start_iso = sys.argv[10]
gdb_rc = int(sys.argv[11])
before_raw = sys.argv[12]
after_raw = sys.argv[13]

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

segv_caught = False
signal_name = None
pc = None
si_addr = None
pc_symbol = None
exitcode_raw = None

try:
    with open(gdb_log_path, "r", errors="replace") as f:
        content = f.read()
except Exception:
    content = ""

for line in content.splitlines():
    line = line.strip()
    if line.startswith("DEFECT22_CAPTURE: segv_caught="):
        val = line.split("=", 1)[1].strip()
        segv_caught = (val.lower() in ("true", "yes", "1"))
    elif line.startswith("DEFECT22_CAPTURE: signal="):
        val = line.split("=", 1)[1].strip()
        if val and val.lower() != "none":
            signal_name = val
    elif line.startswith("DEFECT22_CAPTURE: pc="):
        val = line.split("=", 1)[1].strip()
        m = re.search(r'(0x[0-9a-fA-F]+)', val)
        if m:
            pc = m.group(1)
        elif val and val.lower() != "none":
            pc = val
    elif line.startswith("DEFECT22_CAPTURE: si_addr="):
        val = line.split("=", 1)[1].strip()
        m = re.search(r'(0x[0-9a-fA-F]+)', val)
        if m:
            si_addr = m.group(1)
        elif val and val.lower() != "none":
            si_addr = val
    elif line.startswith("DEFECT22_CAPTURE: pc_symbol="):
        val = line.split("=", 1)[1].strip()
        if val and val.lower() != "none":
            pc_symbol = val
    elif line.startswith("DEFECT22_CAPTURE: exitcode="):
        val = line.split("=", 1)[1].strip()
        m = re.search(r'=\s*([0-9]+)', val)
        if m:
            exitcode_raw = int(m.group(1))
        elif val.isdigit():
            exitcode_raw = int(val)

# Crash count that cannot contradict the capture. `crashes` is the grep count of the inferior's own
# "Fatal Python error" lines — which is necessarily 0 for exactly the RED this instrument exists to
# record, because gdb's `handle SIGSEGV stop` fires BEFORE Python's faulthandler runs and the process
# never prints anything. Measured pre-fix at d62e96a: a captured SIGSEGV produced
# {"capture": {"segv_caught": true}, "crashes": 0} — a record that reads as "no crash". Keep the raw
# count as `faulthandler_crashes` for audit, count the live capture as the crash it is, and state
# which rule was used.
faulthandler_crashes = crashes
if segv_caught:
    crashes = max(crashes, 1)
    crash_count_source = "live_capture"
elif crashes > 0:
    crash_count_source = "faulthandler"
else:
    crash_count_source = "none"

# Exit code: a caught SIGSEGV must be unmistakable — exit 139 when capture.segv_caught is true;
# otherwise propagate the inferior's exit code from $_exitcode (state the fallback in a comment if gdb
# does not supply it — e.g. gdb's own rc). Do not swallow rc=0 into success when a SIGSEGV was caught.
if segv_caught:
    final_rc = 139
elif exitcode_raw is not None:
    final_rc = exitcode_raw
else:
    # Fallback: GDB did not provide $_exitcode (e.g. debugger failure); fall back to gdb process exit code
    final_rc = gdb_rc

capture_obj = {
    "segv_caught": segv_caught,
    "signal": signal_name,
    "pc": pc,
    "si_addr": si_addr,
    "pc_symbol": pc_symbol,
}

sidecar = {
    "state": "DONE",
    "seed": seed,
    "head": head,
    "rc": final_rc,
    "crashes": crashes,
    "faulthandler_crashes": faulthandler_crashes,
    "crash_count_source": crash_count_source,
    "seconds": seconds,
    "summary": summary,
    "log": log_path,
    "gdb_log": gdb_log_path,
    "started_utc": start_iso,
    "loadavg_before": load_before,
    "dry_run": False,
    "capture": capture_obj,
    "env_before": before,
    "env_after": after,
    "oom_kill_delta": oom_delta,
    "journal_oom_kill_delta": j_delta,
}

with open(json_path, "w") as f:
    json.dump(sidecar, f, indent=2)

oom_s = str(oom_delta) if oom_delta is not None else "null"
j_s = str(j_delta) if j_delta is not None else "null"
peak_s = str(mem_peak) if mem_peak is not None else "null"
load_s = str(load_after) if load_after is not None else "null"
pressure = " PRESSURE=yes" if ((oom_delta is not None and oom_delta > 0) or (j_delta is not None and j_delta > 0)) else ""

segv_str = "yes" if segv_caught else "no"
si_addr_str = si_addr if si_addr else "none"
pc_str = pc if pc else "none"
print(f"{final_rc} {segv_str} {si_addr_str} {pc_str}")
print(f"env: oom_kill_delta={oom_s} journal_oom_kill_delta={j_s} mem_peak={peak_s} loadavg_after={load_s}{pressure}")
PY
)

# An instrument failure must not read as a run verdict: without a completed sidecar (state="DONE")
# there is no terminal record of what happened, and the summary line below would print an empty rc.
# After DEFECT-22c a start record (state="RUNNING") exists from the beginning of the run, so mere file
# existence ([ -s "$JSON" ]) no longer proves the parse step completed — a file left in state="RUNNING"
# is by definition a lost or failed run, not a verdict. Fail loudly and distinctively (2).
if [ ! -s "$JSON" ] || ! grep -q '"state": "DONE"' "$JSON"; then
  echo "FATAL: capture sidecar was not written or not completed ($JSON) — the parse step failed." >&2
  echo "       parse output: '${PARSE_OUT}'" >&2
  echo "       Refusing to print a verdict; transcript kept at $GDB_LOG" >&2
  exit 2
fi

read -r RC SEGV_STR SI_ADDR_STR PC_STR <<< "$PARSE_OUT"
ENV_LINE=$(sed -n '2p' <<< "$PARSE_OUT")

# Post-run sweep: the inferior just ran, so any deliberate crasher in it wrote a report that would
# otherwise sit "unseen" and suppress the NEXT real crash of python3.12 (see the hygiene block at
# the top). Loud when it could not clear the path — that is a condition the caller must know about,
# but it is NOT a run verdict: rc stays whatever the inferior's run said.
SWEPT_AFTER=$(sweep_fixture_reports)
FIXTURES_LEFT=$(count_fixture_reports)

echo "arc leg A (live capture) :: seed=${SEED} head=${HEAD} rc=${RC} segv=${SEGV_STR} si_addr=${SI_ADDR_STR} pc=${PC_STR}"
echo "  apport path: fixture reports swept before=${SWEPT_BEFORE} after=${SWEPT_AFTER}, still present=${FIXTURES_LEFT} (quarantine ${QUARANTINE_DIR})"
if [ "$FIXTURES_LEFT" -ne 0 ]; then
  echo "  WARNING: ${FIXTURES_LEFT} fixture report(s) still occupy ${CRASH_DIR} — apport may suppress the next REAL crash report" >&2
fi
echo "  ${SEEDLINE}"
echo "  ${SUMMARY:-<no summary line>}"
echo "  log=${LOG} sidecar=${JSON} gdb_log=${GDB_LOG}"
echo "$ENV_LINE"
exit "$RC"
