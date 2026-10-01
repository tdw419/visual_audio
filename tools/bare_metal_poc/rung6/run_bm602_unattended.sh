#!/usr/bin/env bash
# run_bm602_unattended.sh -- drive the Rung 6 gate to a verdict without anybody
# watching: detached, sleep-inhibited, up to 2 passes, --resume on the second,
# and a single status file at the end that says which one happened.
#
# Why a loop at all: bm602_gate.py already retries the ONE flake that is real
# (Tiny Core's autologin race, 8 boots per anchor leg), and refuses to retry a
# wrong loader line. What it cannot retry is the machine -- a lane that turned
# out to be busy, or a box loaded by another session, costs a leg its budget for
# reasons that have nothing to do with the medium. So a second pass exists for
# exactly that, and no more.
set -u
cd "$(dirname "$0")"
LOG=bm602_unattended.log
: > "$LOG"
say() { echo "$(date -Is) $*" | tee -a "$LOG"; }

say "start: $(pwd)"
rc=1
for i in 1 2; do
  if [[ $i -gt 1 ]]; then
    say "pass 2 with --resume: green legs are not re-paid for"
    ./run_bm602_e2e.sh --resume > "bm602_e2e_pass$i.log" 2>&1
  else
    say "pass 1"
    ./run_bm602_e2e.sh > "bm602_e2e_pass$i.log" 2>&1
  fi
  rc=$?
  say "pass $i rc=$rc  $(grep -m1 '^GREEN' "bm602_e2e_pass$i.log" || echo 'no summary line')"
  [[ $rc -eq 0 ]] && break
  [[ $i -lt 2 ]] && { say 'retrying in 60 s'; sleep 60; }
done

if [[ $rc -eq 0 ]]; then
  say "BM602_RUN_STATUS=GREEN"
else
  say "BM602_RUN_STATUS=RED -- the RED lines, from the last pass:"
  grep -h '^\s*\[RED ' bm602_e2e_pass*.log 2>/dev/null | tail -20 | tee -a "$LOG" || true
fi
echo "BM602_RUN_STATUS=$([[ $rc -eq 0 ]] && echo GREEN || echo RED) rc=$rc $(date -Is)" \
  > BM602_RUN_STATUS.txt
