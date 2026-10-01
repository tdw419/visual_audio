#!/usr/bin/env bash
# DEFECT-22 probe #4 (builder cron af3e62239ce2, 2026-09-13 06:1x tick):
# COMPLEMENT to the PYTHONMALLOC=debug run (green, 155 s). The faulthandler
# traceback at 194844c named a C-level call under glyph_isa_v2.step with
# pure-Python frames above it — the dangling/freed-buffer signature — but
# PYTHONMALLOC=debug only guards PYTHON's allocator, not C-level buffers.
# MALLOC_PERTURB_ makes glibc fill freed memory, so a use-after-free in a
# C-allocated buffer becomes visible instead of silently plausibly correct.
cd /home/jericho/projects/zion/projects/visual_audio || exit 9
FILES=$(ls tests/test_gh*.py tests/test_bk*.py tests/test_eng*.py tests/test_defect1*.py | grep -vE 'glass_box|gh24_s2_mcp')
OUT="output/defect22_legA_mallocperturb_run1.txt"
T0=$(date +%s)
MALLOC_PERTURB_=42 /usr/bin/python3 -m pytest $FILES -v --tb=line > "$OUT" 2>&1
rc=$?
T1=$(date +%s)
crash=$(grep -c 'Fatal Python error' "$OUT")
summary=$(grep -E 'passed|failed|error' "$OUT" | tail -1 | cut -c1-160)
last=$(grep -E '^tests/.*(PASSED|FAILED|ERROR)' "$OUT" | tail -1 | cut -c1-110)
echo "MALLOC_PERTURB rc=${rc} crash=${crash} wall=$((T1-T0))s"
echo "   summary: ${summary}"
[ -n "$last" ] && echo "   last-completed: ${last}"
[ "$crash" != "0" ] && { echo "   --- crash frames ---"; grep -A14 'Fatal Python error' "$OUT" | head -22; }
grep '^FAILED\|^ERROR' "$OUT" | head -5
