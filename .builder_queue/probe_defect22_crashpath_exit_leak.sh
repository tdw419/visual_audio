#!/bin/bash
# Bounded measurement: does gate_arc_lega_capture.sh leave a fixture apport report in
# /var/crash AFTER it exits? (Its L6c leg asserts the path is clean at the instant it checks.)
# Read-only w.r.t. the repo; any report it finds is quarantined out of /var/crash (a stale
# unreported .crash blocks apport's next write for the same executable).
set -u
cd /home/jericho/projects/zion/projects/visual_audio || exit 9
CRASH=/var/crash
Q=/tmp/d22_exit_leak_quarantine
mkdir -p "$Q"

is_fixture() { grep -a -m 1 '^ProcCmdline:' "$1" 2>/dev/null | grep -qa faulthandler_segv_fixture.py; }

echo "== pre-existing reports =="
for f in "$CRASH"/*.crash; do
  [ -f "$f" ] || continue
  echo "   present: $(basename "$f") fixture=$(is_fixture "$f" && echo yes || echo no)"
done
echo "   count before = $(ls "$CRASH"/*.crash 2>/dev/null | wc -l)"

bash tools/gate_arc_lega_capture.sh > /tmp/d22_exit_leak_gate.log 2>&1
RC=$?
T1=$(date '+%s')
echo "== gate rc=$RC exited at $(date -d @$T1 '+%H:%M:%S') =="
grep -E "L6|rc:" /tmp/d22_exit_leak_gate.log | sed 's/^/   /'
echo "   /var/crash immediately after exit: $(ls "$CRASH"/*.crash 2>/dev/null | wc -l) report(s)"

LEAK=""
for i in $(seq 1 30); do
  f=$(ls "$CRASH"/*.crash 2>/dev/null | head -1)
  if [ -n "$f" ]; then
    LEAK="$f"
    echo "   LEAK: report appeared +$(( $(date +%s) - T1 ))s AFTER gate exit: $(basename "$f") size=$(stat -c%s "$f")"
    echo "   LEAK cmdline: $(grep -a -m 1 '^ProcCmdline:' "$f" | cut -c1-120)"
    mv "$f" "$Q/$(basename "$f").$(date +%s)"
    break
  fi
  sleep 1
done
[ -z "$LEAK" ] && echo "   no post-exit report within 30 s (no leak observed this trial)"

# second look: a late write (settle) would show up here
for i in $(seq 1 6); do
  f=$(ls "$CRASH"/*.crash 2>/dev/null | head -1)
  if [ -n "$f" ]; then
    echo "   LATE report +$(( $(date +%s) - T1 ))s: $(basename "$f") — quarantined"
    mv "$f" "$Q/$(basename "$f").late.$(date +%s)"
  fi
  sleep 1
done
echo "   final /var/crash count = $(ls "$CRASH"/*.crash 2>/dev/null | wc -l)"
echo "== apport.log tail =="
tail -6 /var/log/apport.log | sed 's/^/   /'
echo "== quarantined (probe) =="
ls -l "$Q" 2>/dev/null | tail -3
