#!/usr/bin/env bash
# DEFECT-22 probe #6 (builder cron af3e62239ce2, 2026-09-13 06:5x tick):
#
# HYPOTHESIS being tested (the one context candidate probe #5 did NOT concentrate):
# the 194844c SIGSEGV needs the *LLM/escalation-router* path to have run earlier in the
# same process. Rationale, measured this tick:
#   - faulthandler named `tools/glyph_isa_v2.py:561 in step` and NO callee frame, although
#     line 561 at 194844c IS `self._check_alignment(x)` (git show 194844c:... | sed -n 561p,
#     identical at HEAD). A call in progress would normally show the callee frame too, so the
#     fault landed at frame-push/allocator territory, i.e. NOT inside the checker's Python body.
#   - `tools/glyph_gpt/generate.py:32 imports torch` and IS on the crash stack via
#     atlas.register -> run_generated; the crashed process had 35 native extensions resident
#     (faulthandler footer: torch._C x12, numpy, PIL, psutil, zstandard, _cffi_backend, ...).
#   - probe #5 concentrated 8 wgpu-touching files + owner x20 reps in one process (920 tests,
#     0 crashes) — so *GPU churn alone* did not reproduce. The LLM leg was never in a probe slice.
#
# METHOD: one process, R reps of: gh12 (live ollama admission leg) -> owner -> 8 GPU files.
# `-v` so a crash names its own test; pinned seed so the order is replayable; PYTHONFAULTHANDLER=1.
# This is a probe, not a gate. A negative is a negative for THIS context only, at THIS head,
# and n<=12 is not a rate (Jericho's single-trial rule).
set -u
cd /home/jericho/projects/zion/projects/visual_audio || exit 9

R="${R:-12}"
OWNER="tests/test_gh22_device_driver_abi.py"
LLM="tests/test_gh12_autoatlas.py"
GPU_FILES="tests/test_gh4_wgsl_parity.py tests/test_bk2_wgsl_syscall_parity.py tests/test_eng1_unknown_opcode.py tests/test_gh15_step4_baker_sb2.py tests/test_gh17_paging.py tests/test_gh25_hilbert_paging.py tests/test_gh5_launcher_final.py tests/test_bk1_argv.py"

ARGS=""
i=0
while [ "$i" -lt "$R" ]; do
  ARGS="$ARGS $LLM $OWNER $GPU_FILES"
  i=$((i + 1))
done

OUT="${OUT:-output/defect22_llm_context_reps.txt}"
HEAD=$(git rev-parse --short HEAD)
LOAD_BEFORE=$(cut -d' ' -f1-3 /proc/loadavg)
T0=$(date +%s)
PYTHONFAULTHANDLER=1 timeout 1500 /usr/bin/python3 -m pytest $ARGS -v --tb=line \
  -p randomly --randomly-seed=20260913 > "$OUT" 2>&1
RC=$?
T1=$(date +%s)
CRASHES=$(grep -c 'Fatal Python error' "$OUT")
SUMMARY=$(grep -E '[0-9]+ (passed|failed)' "$OUT" | tail -1)
LAST=$(grep -E 'PASSED|FAILED|ERROR' "$OUT" | tail -1)
SKIPPED=$(grep -c 'SKIPPED' "$OUT")
echo "llm-context reps probe :: R=${R} head=${HEAD} rc=${RC} crashes=${CRASHES} skipped=${SKIPPED} secs=$((T1 - T0)) load_before=${LOAD_BEFORE}"
echo "  ${SUMMARY:-<no summary>}"
echo "  last_event=${LAST}"
if [ "$CRASHES" != "0" ]; then
  grep -n -A 14 'Fatal Python error' "$OUT" | head -22
fi
echo "  log=${OUT}"
exit "$RC"
