#!/usr/bin/env bash
# DEFECT-22 probe #2 (builder cron af3e62239ce2, 2026-09-13):
# the 52-file arc leg A, run VERBOSE so a mid-run crash names its own owning
# test instead of being inferred from a dot count. Records rc, wall clock,
# the Fatal-Python-error verdict, and the last test line printed before death.
cd /home/jericho/projects/zion/projects/visual_audio || exit 9
FILES=$(ls tests/test_gh*.py tests/test_bk*.py tests/test_eng*.py tests/test_defect1*.py | grep -vE 'glass_box|gh24_s2_mcp')
for i in 1 2 3; do
  OUT="output/defect22_legA_v_run${i}.txt"
  LOAD_BEFORE=$(cut -d' ' -f1-3 /proc/loadavg)
  T0=$(date +%s)
  /usr/bin/python3 -m pytest $FILES -v --tb=line > "$OUT" 2>&1
  rc=$?
  T1=$(date +%s)
  LOAD_AFTER=$(cut -d' ' -f1-3 /proc/loadavg)
  crash=$(grep -c 'Fatal Python error' "$OUT")
  summary=$(grep -E '^[0-9]+ (passed|failed)|passed,|failed,' "$OUT" | tail -1)
  last=$(grep -E '^tests/.*(PASSED|FAILED|ERROR)' "$OUT" | tail -1 | cut -c1-90)
  echo "RUN${i} rc=${rc} crash=${crash} wall=$((T1-T0))s load=${LOAD_BEFORE}->${LOAD_AFTER} :: ${summary}"
  [ -n "$last" ] && echo "   last-completed: ${last}"
  if [ "$crash" != "0" ]; then
    echo "   --- crash frames ---"
    grep -A6 'Fatal Python error' "$OUT" | head -12
    echo "   --- last line before crash ---"
    grep -B2 -m1 'Fatal Python error' "$OUT" | head -4
  fi
  grep '^FAILED\|^ERROR' "$OUT" | head -3
done
