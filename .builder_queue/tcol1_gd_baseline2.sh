#!/usr/bin/env bash
# TEST-COL-1: baseline check for glyph_dispatch/tests WITHOUT my glyph_dispatch/src edits (stash/restore)
cd /home/jericho/projects/zion/projects/visual_audio || exit 9
P=/usr/bin/python3
FILES="glyph_dispatch/tests/test_dispatch.py glyph_dispatch/tests/test_item2_dispatch_sha256.py glyph_dispatch/tests/test_item3_mmio_bridge.py glyph_dispatch/tests/test_item3b_shader_mmio.py"
GD="glyph_dispatch/src/dispatch/dispatcher.py glyph_dispatch/src/offload/glyph_dispatch_host.py glyph_dispatch/src/offload/run_with_glyph_dispatch.py"

echo "scratch worktree leftover size: $(du -sh /tmp/tc1_base 2>/dev/null | cut -f1)"

git stash push -m "tcol1-f1-baseline" -- $GD > /tmp/tc1_stash.txt 2>&1
echo "stash_rc=$? ($(head -1 /tmp/tc1_stash.txt))"
echo "--- baseline run: glyph_dispatch/src at HEAD ---"
$P -m pytest $FILES -q > /tmp/tc1_gd_base.txt 2>&1
echo "baseline_rc=$?"
grep -E "^ERROR|ModuleNotFoundError|ImportError|passed|failed|error" /tmp/tc1_gd_base.txt | head -8

git stash pop > /tmp/tc1_pop.txt 2>&1
echo "pop_rc=$?"
git status --short | grep -v '^??' | head -6
