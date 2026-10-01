#!/usr/bin/env bash
cd /home/jericho/projects/zion/projects/visual_audio || exit 9
git add pytest.ini tests/test_bk8_fs_pix_sha256.py \
  glyph_dispatch/src/dispatch/dispatcher.py \
  glyph_dispatch/src/offload/glyph_dispatch_host.py \
  glyph_dispatch/src/offload/run_with_glyph_dispatch.py \
  glyph_dispatch/tests/test_dispatch.py \
  systems/RECEIPT_TESTCOL1_COLLECTION_SWEEP_GREEN.md \
  systems/RECEIPT_TESTCOL1_COLLECTION_SWEEP_RED.md \
  systems/GLYPH_SELF_HOSTING_ROADMAP.md \
  .builder_queue/brief_testcol1_ruling_option3.md \
  .builder_queue/tcol1_probe_src_binding.sh \
  .builder_queue/tcol1_gate_run2.sh || exit 1
git mv .builder_queue/REPAIR_PENDING_testcol1_sweep_scope.md \
       .builder_queue/resolved/REPAIR_PENDING_testcol1_sweep_scope_RESOLVED.md || exit 2
echo "=== staged ==="
git diff --cached --name-status | head -20
echo "=== commit ==="
git commit -F /tmp/tcol1_commit_msg.txt | tail -3
echo "=== head ==="
git log --oneline -1 | cat
