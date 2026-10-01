#!/usr/bin/env bash
# DEFECT-22 probe #3 (builder cron af3e62239ce2, 2026-09-13 06:0x tick):
# THE ORDERED CHEAPEST NEXT INSTRUMENT, per the ticket's next_step and commit 9e4bfa5:
# one full arc leg A under /usr/bin/python3 -X dev with PYTHONMALLOC=debug, so a
# dangling/freed-buffer SIGSEGV becomes a named abort instead of a signal.
# Records rc, wall clock, crash frames/fault, summary, per-test owner when it dies.
cd /home/jericho/projects/zion/projects/visual_audio || exit 9
FILES=$(ls tests/test_gh*.py tests/test_bk*.py tests/test_eng*.py tests/test_defect1*.py | grep -vE 'glass_box|gh24_s2_mcp')
echo "legA files: $(echo "$FILES" | wc -l)"
OUT="output/defect22_legA_pymalloc_debug_run1.txt"
LOAD_BEFORE=$(cut -d' ' -f1-3 /proc/loadavg)
T0=$(date +%s)
PYTHONMALLOC=debug /usr/bin/python3 -X dev -m pytest $FILES -v --tb=line > "$OUT" 2>&1
rc=$?
T1=$(date +%s)
LOAD_AFTER=$(cut -d' ' -f1-3 /proc/loadavg)
crash=$(grep -c 'Fatal Python error' "$OUT")
summary=$(grep -E 'passed|failed|error' "$OUT" | tail -1 | cut -c1-160)
last=$(grep -E '^tests/.*(PASSED|FAILED|ERROR)' "$OUT" | tail -1 | cut -c1-110)
echo "PYMALLOC_DEBUG rc=${rc} crash=${crash} wall=$((T1-T0))s load=${LOAD_BEFORE}->${LOAD_AFTER}"
echo "   summary: ${summary}"
[ -n "$last" ] && echo "   last-completed: ${last}"
if [ "$crash" != "0" ]; then
  echo "   --- crash frames ---"
  grep -A14 'Fatal Python error' "$OUT" | head -22
  echo "   --- fault line ---"
  grep -m1 'Current thread\|Segmentation fault\|Aborted' "$OUT"
fi
grep '^FAILED\|^ERROR' "$OUT" | head -5
