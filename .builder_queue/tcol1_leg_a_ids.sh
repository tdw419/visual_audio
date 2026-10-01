#!/usr/bin/env bash
# TEST-COL-1 ruling leg (a): test_bk8 collected test-id set identical before/after
cd /home/jericho/projects/zion/projects/visual_audio || exit 9
P=/usr/bin/python3
F=tests/test_bk8_fs_pix_sha256.py
$P -m pytest $F --collect-only -q 2>/dev/null | grep "::" | sort > /tmp/tc1_ids_after.txt
git stash push -m "tcol1-bk8-ids" -- $F > /dev/null 2>&1
$P -m pytest $F --collect-only -q 2>/dev/null | grep "::" | sort > /tmp/tc1_ids_before.txt
git stash pop > /dev/null 2>&1
echo "before=$(wc -l < /tmp/tc1_ids_before.txt) after=$(wc -l < /tmp/tc1_ids_after.txt)"
if diff -q /tmp/tc1_ids_before.txt /tmp/tc1_ids_after.txt > /dev/null; then echo "LEG_A: IDENTICAL (diff empty)"; else echo "LEG_A: DIFFERENT"; diff /tmp/tc1_ids_before.txt /tmp/tc1_ids_after.txt | head -10; fi
md5sum /tmp/tc1_ids_before.txt /tmp/tc1_ids_after.txt
echo "--- scratch worktree leftover ---"
ls -d /tmp/tc1_base 2>/dev/null && du -sh /tmp/tc1_base 2>/dev/null || echo "absent"
