#!/usr/bin/env bash
# TEST-COL-1: find what binds sys.modules['src'] (orchestrator probe, 2026-09-13)
cd /home/jericho/projects/zion/projects/visual_audio || exit 9
echo "=== repo/src layout ==="
ls src/ | head -12
echo "has __init__.py: $(test -f src/__init__.py && echo yes || echo no)"
echo "=== absolute src imports inside glyph_dispatch/src ==="
grep -rn "^from src\|^import src\|^    from src\|^  from src" glyph_dispatch/src --include=*.py | head -20
echo "=== what triggers the binding ==="
/usr/bin/python3 - <<'PY'
import sys
sys.path.insert(0, ".")
print("path entries with glyph_dispatch:", [p for p in sys.path if "glyph_dispatch" in p])
import glyph_dispatch.src.glyph.glyph_isa_v2 as m
print("after import, src ->", getattr(sys.modules.get("src"), "__path__", None))
print("path entries with glyph_dispatch:", [p for p in sys.path if "glyph_dispatch" in p])
PY
echo "=== who imports dispatcher ==="
grep -rn "dispatch\.dispatcher\|dispatch import dispatcher" --include=*.py . 2>/dev/null | grep -v "/db/" | head -10
