#!/usr/bin/env bash
# TEST-COL-1 gate run (orchestrator, 2026-09-13) — option 3 + glyph_dispatch relative imports
cd /home/jericho/projects/zion/projects/visual_audio || exit 9
P=/usr/bin/python3
LOG=/tmp/tc1_g1_after2.txt
echo "===== binding probe: does importing glyph_dispatch still steal 'src'? ====="
$P - <<'PY'
import sys
sys.path.insert(0, ".")
import glyph_dispatch.src.glyph.glyph_isa_v2 as m
print("src in sys.modules:", "src" in sys.modules)
print("glyph_dispatch on sys.path:", any("glyph_dispatch" in p for p in sys.path))
PY

echo "===== G1: bare console-script collect-only (the row's gate leg 1) ====="
start=$(date +%s)
timeout 480 /home/jericho/.local/bin/pytest --collect-only -q > "$LOG" 2>&1
rc=$?
end=$(date +%s)
echo "G1_RC=$rc wall=$((end-start))s"
echo "G1_ERROR_LINES=$(grep -c '^ERROR' "$LOG")"
grep -E "tests collected|collected.*error|no tests ran" "$LOG" | tail -2
grep -E "Interrupted|INTERNALERROR" "$LOG" | tail -2

echo "===== G3: test_bk8 (spelling-only migration) ====="
$P -m pytest tests/test_bk8_fs_pix_sha256.py --collect-only -q 2>&1 | tail -1 | tee /tmp/tc1_bk8_after.txt
$P -m pytest tests/test_bk8_fs_pix_sha256.py -q 2>&1 | tail -2

echo "===== G4: collateral (regression legs) ====="
$P -m pytest tests/test_substor_boot_witness.py -q 2>&1 | tail -1
$P -m pytest tests/test_osskel_engine_switch.py tests/test_osskel_aspace_switch.py -q 2>&1 | tail -1
$P -m pytest tests/test_gh9_loader.py tests/test_bk11_coreutils.py tests/test_bk1_argv.py -q 2>&1 | tail -1

echo "===== G4b: glyph_dispatch's own suite (the library I edited) ====="
$P -m pytest glyph_dispatch/tests/test_dispatch.py glyph_dispatch/tests/test_item2_dispatch_sha256.py glyph_dispatch/tests/test_item3_mmio_bridge.py glyph_dispatch/tests/test_item3b_shader_mmio.py -q 2>&1 | tail -2

echo "===== G4c: the glyph_dispatch mmio verifier ====="
timeout 300 $P tools/verify_glyph_dispatch_mmio.py > /tmp/tc1_verify_mmio.txt 2>&1
echo "verify_mmio_rc=$?"
tail -4 /tmp/tc1_verify_mmio.txt
