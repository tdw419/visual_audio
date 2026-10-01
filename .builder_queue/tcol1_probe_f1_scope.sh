#!/usr/bin/env bash
# TEST-COL-1: scope probe for the glyph_dispatch relative-import fix (orchestrator, 2026-09-13)
cd /home/jericho/projects/zion/projects/visual_audio || exit 9
echo "=== _GD_ROOT uses in dispatcher.py ==="
grep -n "_GD_ROOT" glyph_dispatch/src/dispatch/dispatcher.py
echo "=== _GD_ROOT uses in glyph_dispatch_host.py ==="
grep -n "_GD_ROOT" glyph_dispatch/src/offload/glyph_dispatch_host.py
echo "=== ALL top-level 'src' imports anywhere in glyph_dispatch (incl db/) ==="
grep -rn "^ *\(from\|import\) src\b\|^ *\(from\|import\) src\." glyph_dispatch/ --include=*.py | head -30
echo "=== glyph_dispatch/src/db imports ==="
ls glyph_dispatch/src/db/*.py 2>/dev/null | head -5
grep -rn "^ *\(from\|import\) " glyph_dispatch/src/db/*.py 2>/dev/null | head -10
echo "=== wordbase default in glyph_isa_v2 ==="
grep -n "wordbase_path\|parents\[" glyph_dispatch/src/glyph/glyph_isa_v2.py | head -10
echo "=== glyph_dispatch/tests roster ==="
ls glyph_dispatch/tests/*.py | head -20
echo "=== verify tool ==="
ls -la tools/verify_glyph_dispatch_mmio.py
