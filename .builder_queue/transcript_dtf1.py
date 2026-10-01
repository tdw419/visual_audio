"""DTF-1 receipt transcript: all five legs on ONE shell instance.

Run for RECEIPT_DTF1_shell_dispatch.md. One repl() run, no restart between
turns: e / s / w / r + one unrecognized byte. Prints each turn's observable
effect, verifies the WAV via Phy16Tone.decode and the file byte-exactly.
"""
import sys
import tempfile
from pathlib import Path

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

d = tempfile.mkdtemp(prefix="dtf1_receipt_")
write_path = str(Path(d) / "w.dat")
audio_path = str(Path(d) / "a.wav")

image = build_dispatch_shell(write_path, audio_path)
lines = ["e hello", "s hi there", "w payload text", "r", "z bogus command"]
out = repl(lines=lines, image=image, fs_pix_enabled=True)  # ONE run, no restart

print("=== DTF-1 one-instance transcript (build_dispatch_shell) ===")
for turn, result in zip(lines, out):
    print(f"turn {turn!r:22} -> {result!r}")

print("\n--- leg verification ---")
print(f"L1 echo: out[0] == {out[0]!r} (expect ' hello')")
rate, samples = wavfile.read(audio_path)
decoded = Phy16Tone.decode(samples)
print(f"L2 speak: wav {len(samples)} samples @ {rate} Hz, decoded={decoded!r}")
file_bytes = Path(write_path).read_bytes()
print(f"L3 write: {write_path} bytes={file_bytes!r}")
print(f"L4 read:  out[3] == {out[3]!r} (round-trip of {file_bytes!r})")
print(f"L5 unrecognized: out[4] == {out[4]!r}"
      f" (DISPATCH_ERROR_MARKER={DISPATCH_ERROR_MARKER.decode('ascii')!r})")

print("\n--- mutation (RED) leg: neutered always-echo build (build_shell) ---")
neut = repl(lines=["z bogus command"], image=build_shell(), fs_pix_enabled=False)
print(f"neutered turn -> {neut!r}")
marker_absent = DISPATCH_ERROR_MARKER.decode("ascii") not in neut[0]
echoed = neut == ["z bogus command"]
print(f"marker absent in neutered output: {marker_absent}; echoed verbatim: {echoed}")
ok = (
    out[0] == " hello"
    and b" hi there" == decoded
    and file_bytes == b" payload text"
    and out[3] == " payload text"
    and out[4] == DISPATCH_ERROR_MARKER.decode("ascii")
    and marker_absent and echoed
)
print(f"\nDTF1_TRANSCRIPT {'PASS' if ok else 'FAIL'}")
sys.exit(0 if ok else 1)
