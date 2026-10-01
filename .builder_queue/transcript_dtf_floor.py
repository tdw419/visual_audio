"""Floor-exit transcript (AMENDMENT_DTF1_desktop_floor.md, exit criteria):

ONE session, in sequence, exercising all four desktop-floor rows:

  DTF-1  dispatch shell: e/s/w/r + loud unknown-cmd  (the session surface)
  DTF-2  in-image text console: the session text renders into the pixel
         band and decodes back glyph-side
  DTF-3  FS grow: BK-7 SYS append — a file built across multiple appends
         read back whole (via the FS kernel image's own tasks)
  DTF-4  coreutils: cat/echo/wc/cmp/head real compiled programs, byte-exact

Run from the repo root:  .venv/bin/python .builder_queue/transcript_dtf_floor.py
Exit 0 = floor transcript PASS.

Blank-sentinel leg first (the amendment's RED-first discipline): the console
band is decoded BEFORE any turn runs and must be empty.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import scipy.io.wavfile as wavfile

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools"), str(REPO / "experiments")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from src.codec.phy import Phy16Tone  # noqa: E402
from glyph_interactive_shell import (  # noqa: E402
    DISPATCH_ERROR_MARKER,
    build_dispatch_shell,
    build_shell,
    repl,
)
from tools.glyph_text_console import TextConsole, compose_observation, save_png  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    tag = "PASS" if cond else "FAIL"
    print(f"[{tag}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


d = tempfile.mkdtemp(prefix="dtf_floor_")
write_path = str(Path(d) / "notes.dat")
audio_path = str(Path(d) / "a.wav")

# ── blank-sentinel RED-first leg (before any turn) ───────────────────────
console = TextConsole()
blank = console.render_band()
try:
    blank_text = console.decode_band(blank)
    check("T0 blank-sentinel band decodes to empty", blank_text == "",
          f"decoded={blank_text!r}")
except ValueError as e:
    check("T0 blank-sentinel band decodes to empty", False, str(e))

# ── DTF-1 + DTF-2: one dispatch-shell session, console attached ──────────
image = build_dispatch_shell(write_path, audio_path)
lines = ["e build floor", "w cat dog", "r", "s speak me", "z bogus command"]
out = repl(lines=lines, image=image, fs_pix_enabled=True, console=console)

check("DTF-1 L1 echo", out[0] == " build floor", repr(out[0]))
check("DTF-1 L3 write (bytes on disk)",
      Path(write_path).read_bytes() == b" cat dog",
      repr(Path(write_path).read_bytes()))
check("DTF-1 L4 read round-trip", out[2] == " cat dog", repr(out[2]))
rate, samples = wavfile.read(audio_path)
decoded = Phy16Tone.decode(samples)
check("DTF-1 L2 speak decode", decoded == b" speak me", f"{len(samples)} samples @ {rate} Hz -> {decoded!r}")
check("DTF-1 L5 loud unknown-cmd", out[4] == DISPATCH_ERROR_MARKER.decode("ascii"),
      repr(out[4]))

# ── DTF-2: the same session's PRT stream is IN the band, decoded glyph-side
# NOTE: the VGA font atlas covers printable ASCII EXCEPT the bracket/brace
# family [ \ ] ^ _ ` { | } ~ (85 glyphs). Any char the session emits that is
# NOT in the atlas renders as '?' (documented, never blank) — so the expected
# band text is derived from the font's actual coverage rather than hard-coded
# ASCII. DISPATCH_ERROR_MARKER contains '_', so its in-band rendering is
# ERR:UNKNOWN?CMD; that '?' IS the faithful record of what the machine printed.
from tools.vga_font_8x16 import VGA_FONT_8X16  # noqa: E402


def _font_expect(text: str) -> str:
    return "".join(ch if ch in VGA_FONT_8X16 else "?" for ch in text)


band = console.render_band()
band_text = console.decode_band(band)
raw_lines = [" build floor", "", " cat dog", "", DISPATCH_ERROR_MARKER.decode("ascii")]
# note: the 's speak me' turn PRTs nothing (AUDIO_OUT is silent output), so it
# contributes an EMPTY line to the band — the faithful record of the machine.
expected_lines = [_font_expect(ln) for ln in raw_lines]
marker_in_band = _font_expect(DISPATCH_ERROR_MARKER.decode("ascii")) in band_text
check("DTF-2 band decodes to the session's PRT stream", band_text == "\n".join(expected_lines),
      f"decoded={band_text!r}")
check("DTF-2 unknown-cmd marker present in band", marker_in_band)
obs = compose_observation(image, band)
check("DTF-2 composed observation carries program + band",
      obs.shape[0] >= image.shape[0] + band.shape[0])
band_png = Path(d) / "floor_console_band.png"
save_png(band, band_png)
check("DTF-2 band persisted to PNG", band_png.exists() and band_png.stat().st_size > 0)

# RED leg for DTF-2 decode: mutate ONE band pixel -> decode must refuse
mutated = band.copy()
mutated[0, 0] = (1, 2, 3)
try:
    console.decode_band(mutated)
    check("DTF-2 RED mutated band refused", False, "decode accepted a mutated band")
except ValueError:
    check("DTF-2 RED mutated band refused", True)

# ── DTF-3: FS grow via the BK-7 gate (in-image FS kernel, real engine) ───
r = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/test_bk7_fs_grow.py", "-q", "--no-header"],
    cwd=REPO, capture_output=True, text=True, timeout=600)
tail = (r.stdout + r.stderr).strip().splitlines()[-1] if (r.stdout or r.stderr) else ""
check("DTF-3 BK-7 gate green (write + appends + whole read-back; hole reuse)",
      r.returncode == 0, tail)

# ── DTF-4: coreutils via the BK-11 gate (cross-gcc + transpiler + engine) ─
r2 = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/test_bk11_coreutils.py", "-q", "--no-header"],
    cwd=REPO, capture_output=True, text=True, timeout=900)
tail2 = (r2.stdout + r2.stderr).strip().splitlines()[-1] if (r2.stdout or r2.stderr) else ""
check("DTF-4 BK-11 gate green (cat/echo/wc/cmp/head byte-exact)",
      r2.returncode == 0, tail2)

# ── mutation leg: neutered always-echo build must NOT produce the dispatch
neut = repl(lines=["z bogus command"], image=build_shell(), fs_pix_enabled=False)
check("mutation: always-echo build echoes verbatim, marker absent",
      DISPATCH_ERROR_MARKER.decode("ascii") not in neut[0] and neut == ["z bogus command"],
      repr(neut))

print(f"\nconsole band: {band_png}")
print(f"session dir:  {d}")
if FAILURES:
    print(f"\nDTF_FLOOR_TRANSCRIPT FAIL ({len(FAILURES)} leg(s): {', '.join(FAILURES)})")
    sys.exit(1)
print("\nDTF_FLOOR_TRANSCRIPT PASS — all four floor rows exercised in sequence")
sys.exit(0)
