#!/usr/bin/env bash
# TEST-COL-1: are the glyph_dispatch/tests collection errors pre-existing? (baseline worktree at HEAD)
cd /home/jericho/projects/zion/projects/visual_audio || exit 9
P=/usr/bin/python3
FILES="glyph_dispatch/tests/test_dispatch.py glyph_dispatch/tests/test_item2_dispatch_sha256.py glyph_dispatch/tests/test_item3_mmio_bridge.py glyph_dispatch/tests/test_item3b_shader_mmio.py"

echo "===== CURRENT TREE error texts ====="
$P -m pytest $FILES -q > /tmp/tc1_gd_current.txt 2>&1
echo "rc=$?"
grep -E "^ERROR|ModuleNotFoundError|ImportError" /tmp/tc1_gd_current.txt | head -8

echo "===== BASELINE worktree (HEAD, my edits absent) ====="
rm -rf /tmp/tc1_base
git worktree add --detach /tmp/tc1_base HEAD > /tmp/tc1_wt.txt 2>&1
echo "worktree_rc=$?"
cd /tmp/tc1_base || exit 9
$P -m pytest $FILES -q > /tmp/tc1_gd_base.txt 2>&1
echo "rc=$?"
grep -E "^ERROR|ModuleNotFoundError|ImportError|passed|failed|error" /tmp/tc1_gd_base.txt | head -8
cd /home/jericho/projects/zion/projects/visual_audio && git worktree remove --force /tmp/tc1_base >/dev/null 2>&1; echo "worktree_removed=$?"
