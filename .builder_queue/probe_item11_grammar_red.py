"""ITEM 11 RED probe (2026-09-23, dispatch grammar collision).

Live reproduction on the PRE-FIX tree: natural sentences whose first byte
matches a command char are silently misexecuted:
  'what time is it'  -> parsed as 'w', WRITES 'hat time is it' to disk
  'seems fine to me' -> parsed as 's', SPEAKS 'eems fine to me' (WAV)
  'read me the news' -> parsed as 'r', echoes the file's prior content
No error anywhere. Exit 1 if any of the three misexecutions is observed
(post-fix this probe exits 0 because the misexecutions are gone).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "experiments"))

from glyph_interactive_shell import repl, build_dispatch_shell  # noqa: E402

D = Path("/tmp/item11_probe")
D.mkdir(exist_ok=True)
WP, AP = str(D / "w.dat"), str(D / "a.wav")

img = build_dispatch_shell(WP, AP)
misexecuted = []

# Pipe 1: 'what time is it' must NOT write any file
if Path(WP).exists():
    Path(WP).unlink()
out = repl(lines=["what time is it"], image=img, fs_pix_enabled=True)
if Path(WP).exists():
    misexecuted.append(
        f"pipe1 SILENT WRITE: 'what time is it' -> file {WP} = {Path(WP).read_bytes()!r}, output {out!r}")

# Pipe 2: 'seems fine to me' must NOT produce audio
if Path(AP).exists():
    Path(AP).unlink()
out = repl(lines=["seems fine to me"], image=img, fs_pix_enabled=True)
if Path(AP).exists():
    misexecuted.append(f"pipe2 SILENT SPEAK: 'seems fine to me' -> WAV created, output {out!r}")

# Pipe 3: 'read me the news' must NOT echo prior content silently
Path(WP).write_bytes(b" stale prior content")
out = repl(lines=["read me the news"], image=img, fs_pix_enabled=True)
if out and "stale" in out[0]:
    misexecuted.append(f"pipe3 SILENT ECHO-TAIL: 'read me the news' -> {out!r}")

if misexecuted:
    print("RED — dispatch grammar collision present at this tree:")
    for m in misexecuted:
        print("  " + m)
    sys.exit(1)
print("GREEN — no silent misexecution observed (grammar guard in place)")
sys.exit(0)
