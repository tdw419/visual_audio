#!/usr/bin/env bash
# TEST-COL-1 verification runner (orchestrator, 2026-09-13)
cd /home/jericho/projects/zion/projects/visual_audio || exit 9
LOG=/tmp/tc1_after.txt
start=$(date +%s)
timeout 480 /home/jericho/.local/bin/pytest --collect-only -q > "$LOG" 2>&1
rc=$?
end=$(date +%s)
echo "G1_RC=$rc wall=$((end-start))s"
echo "G1_ERRORS=$(grep -c '^ERROR' "$LOG")"
tail -3 "$LOG" | cut -c1-160
echo "=== git status (tracked) ==="
git status --short | grep -v '^??'
echo "=== poison/ini ==="
git status --short | grep -E 'pytest.ini|buffer_p|test_buffer'
echo "=== pytest.ini ==="
cat pytest.ini
