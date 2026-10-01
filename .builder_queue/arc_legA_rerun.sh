#!/usr/bin/env bash
# Arc leg A stability probe at HEAD 194844c (builder cron af3e62239ce2, 2026-09-13)
# Purpose: measure whether the 52-file canonical arc is reliably green at HEAD
# after TEST-COL-1 changed pytest.ini + tests/** (arc dependency closure).
cd /home/jericho/projects/zion/projects/visual_audio || exit 9
FILES=$(ls tests/test_gh*.py tests/test_bk*.py tests/test_eng*.py tests/test_defect1*.py | grep -vE 'glass_box|gh24_s2_mcp')
for i in 4 5; do
  OUT="output/arc_legA_194844c_run${i}.txt"
  /usr/bin/python3 -m pytest $FILES -q --junitxml="output/arc_verify_194844c_run${i}.xml" > "$OUT" 2>&1
  rc=$?
  crash=$(grep -c 'Fatal Python error' "$OUT")
  summary=$(grep -E 'passed|failed' "$OUT" | tail -1)
  echo "RUN${i} rc=${rc} crashes=${crash} :: ${summary}"
  grep '^FAILED' "$OUT" | head -3
done
