#!/bin/bash
# Bounded leak measurement, R trials of the REAL gate: does a fixture apport report land in
# /var/crash AFTER the gate exits (its L6c sweep runs before apport's asynchronous write)?
# Each trial:
#   1. record reports present at entry (a report at entry = the PREVIOUS trial leaked; quarantine it)
#   2. run tools/gate_arc_lega_capture.sh, capture rc
#   3. watch /var/crash for 15 s after exit; the first appearance = a leak, with its age after exit
R=${1:-4}
WATCH=${2:-15}
cd /home/jericho/projects/zion/projects/visual_audio || exit 9
CRASH=/var/crash
Q=/tmp/d22_leak_runs
mkdir -p "$Q"
is_fixture() { grep -a -m 1 '^ProcCmdline:' "$1" 2>/dev/null | grep -qa faulthandler_segv_fixture.py; }
clean_entry_count=0; leaks=0; refused=0

for t in $(seq 1 "$R"); do
  entry=0
  for f in "$CRASH"/*.crash; do
    [ -f "$f" ] || continue
    entry=$((entry + 1))
    echo "trial $t ENTRY report: $(basename "$f") fixture=$(is_fixture "$f" && echo yes || echo no) size=$(stat -c%s "$f")"
    mv "$f" "$Q/t${t}_entry_$(basename "$f").$(date +%s)" 2>/dev/null
  done
  [ "$entry" -eq 0 ] && clean_entry_count=$((clean_entry_count + 1))

  bash tools/gate_arc_lega_capture.sh > "$Q/t${t}_gate.log" 2>&1
  rc=$?
  T1=$(date '+%s')
  l6=$(grep -E "L6b|L6c|L6 PASS|L6 FAIL" "$Q/t${t}_gate.log" | tr '\n' '|')
  immed=$(ls "$CRASH"/*.crash 2>/dev/null | wc -l)

  leak=""
  for i in $(seq 1 "$WATCH"); do
    f=$(ls "$CRASH"/*.crash 2>/dev/null | head -1)
    if [ -n "$f" ]; then
      leak=$(basename "$f")
      age=$(( $(date +%s) - T1 ))
      echo "trial $t rc=$rc ENTRY_REPORTS=$entry LEAK +${age}s after exit: $leak fixture=$(is_fixture "$f" && echo yes || echo no)"
      mv "$f" "$Q/t${t}_leak_${leak}.${age}s.$(date +%s)" 2>/dev/null
      break
    fi
    sleep 1
  done
  [ -n "$leak" ] && leaks=$((leaks + 1))
  # apport refusing a write is the OTHER failure mode of the same path; count it from the log
  ref=$(tail -60 /var/log/apport.log | grep -c "already exists and unseen")
  [ "$ref" -gt 0 ] && refused=$((refused + 1))
  echo "trial $t rc=$rc entry=$entry immediate_after_exit=$immed leak=${leak:-none} L6=[$l6] apport_refusals_in_tail=$ref"
done

echo "== SUMMARY: trials=$R clean_entry=$clean_entry_count post_exit_leaks=$leaks trials_with_apport_refusal=$refused =="
echo "== final /var/crash count = $(ls "$CRASH"/*.crash 2>/dev/null | wc -l) =="
