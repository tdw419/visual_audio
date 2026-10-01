"""ITEM 11 GREEN transcript (re-runnable): the three natural-sentence pipes
after the grammar fix, plus the legibility contract. Exit 0 only if every
misexecution is gone AND legitimate commands still work. This is the
before/after receipt evidence generator (run pre-fix for the BEFORE side)."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "experiments"))
sys.path.insert(0, str(REPO))

from glyph_interactive_shell import build_dispatch_shell, repl  # noqa: E402
from src.codec.phy import Phy16Tone  # noqa: E402
import scipy.io.wavfile as wavfile  # noqa: E402

D = Path("/tmp/item11_transcript")
D.mkdir(exist_ok=True)
WP, AP = str(D / "w.dat"), str(D / "a.wav")
ERR = "ERR:UNKNOWN_CMD"

img = build_dispatch_shell(WP, AP)
ok = True

# AFTER-leg 1: 'what time is it' -> named error, no file
if Path(WP).exists():
    Path(WP).unlink()
out = repl(lines=["what time is it"], image=img, fs_pix_enabled=True)
wrote = Path(WP).exists()
print(f"pipe1 'what time is it' -> out={out!r} file_written={wrote}")
ok &= (out == [ERR] and not wrote)

# AFTER-leg 2: 'seems fine to me' -> named error, no WAV
if Path(AP).exists():
    Path(AP).unlink()
out = repl(lines=["seems fine to me"], image=img, fs_pix_enabled=True)
spoke = Path(AP).exists()
print(f"pipe2 'seems fine to me' -> out={out!r} audio_produced={spoke}")
ok &= (out == [ERR] and not spoke)

# AFTER-leg 3: 'read me the news' -> named error, no echo
Path(WP).write_bytes(b" stale prior content")
out = repl(lines=["read me the news"], image=img, fs_pix_enabled=True)
ok &= out == [ERR]
print(f"pipe3 'read me the news' -> out={out!r}")

# AFTER-leg 4: legit commands unharmed, incl. the round-trip
Path(WP).unlink(missing_ok=True)
Path(AP).unlink(missing_ok=True)
out = repl(lines=["e hello", "s hi there", "w payload text", "r"],
           image=img, fs_pix_enabled=True)
rate, samples = wavfile.read(AP)
decoded = Phy16Tone.decode(samples)
print(f"pipe4 legit session -> out={out!r} wav_decode={decoded!r} "
      f"file={Path(WP).read_bytes()!r}")
ok &= (out == [" hello", "", "", " payload text"]
       and decoded == b" hi there"
       and Path(WP).read_bytes() == b" payload text")

print("TRANSCRIPT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
