#!/usr/bin/env bash
# TEST-COL-1: does test_dispatch.py pass at HEAD? (stash all 4 touched files, run, restore)
cd /home/jericho/projects/zion/projects/visual_audio || exit 9
P=/usr/bin/python3
FILES="glyph_dispatch/tests/test_dispatch.py glyph_dispatch/src/dispatch/dispatcher.py glyph_dispatch/src/offload/glyph_dispatch_host.py glyph_dispatch/src/offload/run_with_glyph_dispatch.py"

echo "===== BASELINE (HEAD versions of the 4 touched files) ====="
git stash push -m "tcol1-full-baseline" -- $FILES > /dev/null 2>&1
echo "stash_rc=$?"
$P -m pytest glyph_dispatch/tests/test_dispatch.py -q > /tmp/tc1_td_base.txt 2>&1
echo "baseline_rc=$?"
tail -3 /tmp/tc1_td_base.txt
git stash pop > /dev/null 2>&1
echo "pop_rc=$?"

echo "===== CURRENT (my edits) ====="
$P -m pytest glyph_dispatch/tests/test_dispatch.py -q > /tmp/tc1_td_cur.txt 2>&1
echo "current_rc=$?"
tail -3 /tmp/tc1_td_cur.txt
echo "--- first failure text (current) ---"
grep -E "sqlite3|Error|FAILED" /tmp/tc1_td_cur.txt | head -6

echo "===== tree state after pop ====="
git status --short | grep -v '^??'
