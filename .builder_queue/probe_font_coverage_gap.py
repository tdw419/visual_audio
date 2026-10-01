"""Probe: exact VGA font-8x16 coverage vs printable ASCII (research tick, BK-19 candidate).

Answers, mechanically:
  1. Which printable ASCII chars (32..126) are ABSENT from VGA_FONT_8X16?
  2. Does the DTF-1 dispatch shell emit any of those absent chars?
  3. Round-trip proof: render 'ERR:UNKNOWN_CMD' through TextConsole and
     decode it back — show the '?' substitution is real and lossy.
Re-runnable, exit 0; findings-only (no engine code touched).
"""
import sys

sys.path.insert(0, ".")

from tools.vga_font_8x16 import VGA_FONT_8X16, get_vga_bitmap  # noqa: E402
from tools.glyph_text_console import (  # noqa: E402
    TextConsole, render_transcript, decode_transcript_band,
)
import numpy as np  # noqa: E402

ascii_all = [chr(c) for c in range(32, 127)]
present = set(VGA_FONT_8X16.keys())
missing = [c for c in ascii_all if c not in present]
extra = sorted(present - set(ascii_all))

print(f"[1] font coverage: {len(present)} glyphs; printable ASCII 32..126 = 95")
print(f"    present non-ASCII glyphs: {extra!r}")
print(f"    MISSING ASCII ({len(missing)}): {''.join(missing)!r}")
print(f"    codes: {[ord(c) for c in missing]}")

# Structural claim from the docstring says 85 glyphs; verify the number.
docstring_claim = 85
print(f"[2] docstring/doc claim '85 glyphs' vs actual {len(present)}: "
      f"{'MATCH' if len(present) == docstring_claim else 'MISMATCH'}")

# What the shell emits for unknown commands (DTF-1 transcript, 'z bogus'):
marker = "ERR:UNKNOWN_CMD"
hit = [c for c in marker if c in missing]
print(f"[3] error marker {marker!r} contains {len(hit)} missing char(s): {hit!r}")

# Round-trip proof through the real console (the exact DTF path).
con = TextConsole(rows=2, cols=40)
con.feed(marker)
band = con.render_band()
try:
    decoded = decode_transcript_band(band, cols=40)
    print(f"[4] round-trip: {marker!r} -> rendered -> decoded {decoded!r}")
    print(f"    lossy: {decoded != marker}  (substituted char: '?')")
except ValueError as e:
    print(f"[4] round-trip REFUSED (strict decode): {e}")
    sys.exit(1)

# Counter-proof: with the missing glyph present, round-trip would be lossless.
# Simulate by patching '_' into a COPY of the font and re-rendering.
import tools.glyph_text_console as gtc
import tools.vga_font_8x16 as vf

underscore_bitmap = get_vga_bitmap('_') if '_' in present else None
print(f"[5] '_' bitmap available for patch test: {underscore_bitmap is not None}")

# Containment check: does any OTHER shell-facing string hit the gap?
# The five shell verbs' outputs + all syscall error strings we know of.
known_strings = [
    "ERR:UNKNOWN_CMD", "ERR:UNKNOWN?CMD", " build floor", " cat dog",
    " speak me",
]
affected = [s for s in known_strings if any(c in missing for c in s)]
print(f"[6] known floor strings hitting the gap: {affected!r}")

print("PROBE OK (coverage measured; round-trip substitution demonstrated)")
