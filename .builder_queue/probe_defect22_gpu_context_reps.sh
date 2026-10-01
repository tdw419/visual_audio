#!/usr/bin/env bash
# DEFECT-22 probe #5 (builder cron af3e62239ce2, 2026-09-13 06:2x tick):
# HYPOTHESIS being tested: the 194844c SIGSEGV is a *process-context* crash, not a
# file-local one (isolation sweep: 52/52 PASS), and the leading context candidate is
# GPU/wgpu device churn — 8 of the 52 leg-A files create wgpu/Vulkan devices
# (RTX 5090), the crash's innermost frame is `_check_alignment` at
# tools/glyph_isa_v2.py:561, a one-line `x % INSTR_WIDTH` check that cannot segfault
# on its own, i.e. the frame is a VICTIM of corruption originating elsewhere.
#
# METHOD: concentrate the suspect context. Run the 8 GPU-touching leg-A files PLUS
# the crashed owner module (tests/test_gh22_device_driver_abi.py, named by the
# faulthandler traceback) REPEATED R times inside ONE process. The GPU subset costs
# 5.33 s / 41 tests, so a rep is ~6 s; R=20 -> ~2 min, an order of magnitude more
# GPU-context churn per wall-clock second than a 140 s arc run gives.
#
# This is a probe, not a gate. It cannot close DEFECT-22; a negative is a negative
# for THIS context only. The point is to test a hypothesis cheaply, with -v so a
# crash names its own test.
set -u
cd /home/jericho/projects/zion/projects/visual_audio || exit 9

R="${R:-20}"
OWNER="tests/test_gh22_device_driver_abi.py"
GPU_FILES="tests/test_gh4_wgsl_parity.py tests/test_bk2_wgsl_syscall_parity.py tests/test_eng1_unknown_opcode.py tests/test_gh15_step4_baker_sb2.py tests/test_gh17_paging.py tests/test_gh25_hilbert_paging.py tests/test_gh5_launcher_final.py tests/test_bk1_argv.py"

ARGS=""
i=0
while [ "$i" -lt "$R" ]; do
  ARGS="$ARGS $OWNER $GPU_FILES"
  i=$((i + 1))
done

OUT="output/defect22_gpu_context_reps.txt"
HEAD=$(git rev-parse --short HEAD)
LOAD_BEFORE=$(cut -d' ' -f1-3 /proc/loadavg)
T0=$(date +%s)
PYTHONFAULTHANDLER=1 timeout 900 /usr/bin/python3 -m pytest $ARGS -v --tb=line \
  -p randomly --randomly-seed=20260913 > "$OUT" 2>&1
RC=$?
T1=$(date +%s)
CRASHES=$(grep -c 'Fatal Python error' "$OUT")
SUMMARY=$(grep -E '[0-9]+ (passed|failed)' "$OUT" | tail -1)
LAST=$(grep -E 'PASSED|FAILED' "$OUT" | tail -1)
echo "gpu-context reps probe :: R=${R} head=${HEAD} rc=${RC} crashes=${CRASHES} secs=$((T1 - T0)) load_before=${LOAD_BEFORE}"
echo "  ${SUMMARY:-<no summary>}"
echo "  last_event=${LAST}"
if [ "$CRASHES" != "0" ]; then
  grep -n -A 12 'Fatal Python error' "$OUT" | head -20
fi
echo "  log=${OUT}"
exit "$RC"
