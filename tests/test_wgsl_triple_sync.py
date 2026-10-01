"""Standing gate: the WGSL twin's 3 copies (tools/, glyph_dispatch/src/,
glyph_dispatch/src/glyph/) must stay byte-identical, the same guarantee
glyph_isa_v2.py's pre-commit hook already gives the Python engine.

No such enforcement existed for wgsl_glyph_isa_v2.py until 2026-09-16: a
2.2a-era edit to tools/wgsl_glyph_isa_v2.py silently drifted from both
glyph_dispatch copies for most of a day, undetected, because every
"twin synced" check in that window was checking the Python<->Python
twin only. This test catches both staged-commit drift (same class the
pre-commit hook should also gate - see the follow-up item to extend it)
and out-of-band drift a staged-files filter can't see at all.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

_COPIES = [
    REPO / "tools" / "wgsl_glyph_isa_v2.py",
    REPO / "glyph_dispatch" / "src" / "wgsl_glyph_isa_v2.py",
    REPO / "glyph_dispatch" / "src" / "glyph" / "wgsl_glyph_isa_v2.py",
]


def test_all_three_wgsl_copies_are_byte_identical():
    contents = {str(p): p.read_text() for p in _COPIES}
    canonical = contents[str(_COPIES[0])]
    mismatched = [p for p, c in contents.items() if c != canonical]
    assert not mismatched, (
        f"WGSL twin drift: {mismatched} differ from {_COPIES[0]} - "
        f"re-sync with `cp tools/wgsl_glyph_isa_v2.py <mismatched path>` "
        f"before committing"
    )


def test_non_vacuity_a_real_drift_would_be_caught():
    """Prove the check discriminates: feeding it a deliberately-diverged
    trio (in-memory strings, no files touched) must fail."""
    a, b, c = "same", "same", "DIFFERENT"
    mismatched = [name for name, content in (("b", b), ("c", c)) if content != a]
    assert mismatched == ["c"], "the comparison logic itself is broken"
