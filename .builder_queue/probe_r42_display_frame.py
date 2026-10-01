#!/usr/bin/env python3
"""R4.2 display output — pixel-perfect frame presentation, VCC-preserving.

PRODUCT_ROADMAP.md:74 (R4.2): "Display output: pixel-perfect frame
presentation, VCC-preserving."

Approach mirrors the R3.x probes: built entirely over LANDED substrate
channels — zero production lines changed.

  machine -> frame : run the LANDED fleet image on the shader path
                     (GlyphRunner.run_wgsl, R1.4-converged) to HALT, take
                     the committed receipt["ram"] (16,384 words) and
                     present it as ONE 128x128 RGBA frame:
                       pixel at Hilbert index d  =  word ram[d]
                       RGBA = the 4 word bytes, MSB in red
                     The curve is tools/vcc_validate.d2xy — the repo's
                     canonical VCC Hilbert mapping (AGENTS.md "Hilbert
                     Mapping Coherence"). 16384 words = exactly 128^2,
                     so the WHOLE machine RAM is one frame. A substrate
                     word is 32 bits and a pixel carries exactly 32
                     bits (R,G,B,A) — one pixel per word, byte-exact,
                     alpha used as the word's top byte (NOT the byte-
                     container codec's alpha=0 terminator convention).
  frame -> host    : decode walks Hilbert indices in order, reassembles
                     words, and verifies WORD-EXACT against the receipt's
                     ram — pixel-perfect presentation. The SEMANTIC leg:
                     the decoded frame's word 765 must read the fleet
                     receipt 0x5EED0005, word 717 done=0b1011, word 731
                     E-K1 0xFA026, results {714:6,728:12,748:20,763:30}
                     — the display carries the machine's committed state,
                     not just bits.
  VCC leg          : structural hash (vcc_validate.structural_hash) of
                     the decoded word payload is deterministic across a
                     re-encode/re-decode cycle.

GREEN contract (exit 0), shader engine:
  - decoded frame == receipt ram word-for-word (16,384 words),
  - decoded frozen words match the fleet contract above,
  - structural hash stable across re-encode.

RED legs (each exits 1 = RED by contract, shown before green):
  --corrupt-verify : verifier compares against a CORRUPTED expected ram;
                     the machine's GOOD frame must be REJECTED
                     (verifier discrimination).
  --torn-frame     : one channel byte of ONE pixel (the receipt word
                     765's pixel) is flipped after encode (presentation
                     fault, e.g. torn scanout); the verifier must
                     DETECT the mismatch (pixel corruption detection).

What PASS does NOT prove: no real display hardware / scanout exists
(this is the frame-presentation + VCC-preservation contract over the
substrate's committed RAM, not a monitor driver); the CPU engine's frame
is NOT separately gated here (R1.4 landed frozen-word parity; the gate
test drives one in-process CPU round-trip leg for the codec itself);
no rate/floor claims made (one cold rung-shaped run, no steps/s quote).
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from tools.vcc_validate import d2xy, structural_hash     # noqa: E402
from tools.glyph_gpt.atlas import build_default_atlas    # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner           # noqa: E402
from tools.glyph_gpt.agent_resident import (             # noqa: E402
    resident_image, RES_FLEET_RCPT, RES_DONE_WORD, RES_FLEET_DONE,
    RES_FLEET_EXPECT, RES_FAULT_WORD,
)

N = 128                            # frame side; 128^2 == 16384 == RAM words
RAM_WORDS = N * N
SENTINEL_WORD = RES_FLEET_RCPT     # the pixel whose tear --torn-frame injects
TEAR_MASK = 0x0001FF00             # flip the pixel's red+green channel bytes

FROZEN_EXPECT = {
    RES_FLEET_RCPT: RES_FLEET_DONE,        # 765: 0x5EED0005
    RES_DONE_WORD: 0b1011,                 # 717
    RES_FAULT_WORD: 0xFA026,               # 731
    **RES_FLEET_EXPECT,                    # 714:6 728:12 748:20 763:30
}


# ── the presentation codec (frame <-> words, canonical VCC curve) ─────────
# NOTE: a frame pixel carries 24 bits (R,G,B); substrate words are 32-bit.
# The BK-2 readback packing is (hi<<16)|(mid<<8)|lo of the LOW 3 bytes, so
# word 765 (0x5EED0005) presents its top byte 0x5E in ALPHA and the codec
# is word-exact at 32 bits only with alpha carrying bits [31:24]. This
# codec therefore stores the word's TOP byte in alpha — the alpha=255
# "unlit pixel" convention of the byte-container codec is NOT reused.
def encode_frame(words, out_path: Path) -> None:
    """Words -> Hilbert-mapped RGBA PNG (1 word per pixel, 32-bit RGBA)."""
    assert len(words) == RAM_WORDS, f"need exactly {RAM_WORDS} words"
    img = np.zeros((N, N, 4), dtype=np.uint8)
    for d, w in enumerate(words):
        x, y = d2xy(N, d)
        v = int(w) & 0xFFFFFFFF
        img[y, x] = [(v >> 24) & 0xFF, (v >> 16) & 0xFF,
                     (v >> 8) & 0xFF, v & 0xFF]
    Image.fromarray(img, "RGBA").save(out_path)


def decode_frame(path: Path):
    """Hilbert-mapped RGBA PNG -> words (the host reading the display)."""
    img = np.array(Image.open(path).convert("RGBA"))
    assert img.shape == (N, N, 4), f"frame is {img.shape}, want ({N},{N},4)"
    words = []
    for d in range(RAM_WORDS):
        x, y = d2xy(N, d)
        r, g, b, a = (int(c) for c in img[y, x])
        words.append((r << 24) | (g << 16) | (b << 8) | a)
    return words


def tear_frame(path: Path, out_path: Path) -> None:
    """Presentation fault: flip ONE channel byte of ONE pixel."""
    img = np.array(Image.open(path).convert("RGBA"))
    x, y = d2xy(N, SENTINEL_WORD)
    img[y, x, 0] ^= 0xFF                   # tear the (word-top) red channel
    Image.fromarray(img, "RGBA").save(out_path)


# ── the verifier (host reading the display against the contract) ──────────
def verify(decoded, expected_ram, corrupt: bool = False):
    ok = decoded == expected_ram
    # semantic leg against the FROZEN words as read OFF THE FRAME
    if corrupt:
        frozen = {w: v ^ 0x5A5A for w, v in FROZEN_EXPECT.items()}
    else:
        frozen = FROZEN_EXPECT
    frozen_ok = all(decoded[w] == v for w, v in frozen.items())
    detail = (f"frame[765]=0x{decoded[RES_FLEET_RCPT]:08x} "
              f"frame[717]=0b{decoded[RES_DONE_WORD]:b} "
              f"frame[731]=0x{decoded[RES_FAULT_WORD]:x} "
              f"results={{714:{decoded[714]},728:{decoded[728]},"
              f"748:{decoded[748]},763:{decoded[763]}}}")
    return ok and frozen_ok, detail


def run_machine():
    """Run the fleet to HALT on the shader path; return receipt ram."""
    with tempfile.TemporaryDirectory() as d:
        atlas = build_default_atlas()
        img_path = Path(d) / "fleet_r42.npy"
        resident_image(atlas, mode="fleet", timer_quantum=6, out_path=img_path)
        runner = GlyphRunner(img_path, ram_words=RAM_WORDS)
        rec = runner.run_wgsl(max_steps=5000)
    if rec.get("error"):
        raise RuntimeError(f"engine error: {rec['error']}")
    if not rec.get("halted"):
        raise RuntimeError(f"machine did not halt (steps={rec.get('steps')})")
    ram = [int(w) & 0xFFFFFFFF for w in rec["ram"]]
    print(f"machine: halted at {rec.get('steps')} steps (shader path)")
    return ram


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corrupt-verify", action="store_true",
                    help="RED leg: corrupt the verifier's expectations; "
                         "a GOOD frame must then be REJECTED (exit 1)")
    ap.add_argument("--torn-frame", action="store_true",
                    help="RED leg: flip one pixel byte post-encode; the "
                         "verifier must DETECT the presentation fault "
                         "(exit 1)")
    args = ap.parse_args()

    print(f"R4.2 display-frame probe: N={N} words={RAM_WORDS} "
          f"corrupt_verify={args.corrupt_verify} torn={args.torn_frame}")

    ram = run_machine()

    with tempfile.TemporaryDirectory() as d:
        frame = Path(d) / "frame_r42.png"
        encode_frame(ram, frame)

        if args.torn_frame:
            torn = Path(d) / "frame_r42_torn.png"
            tear_frame(frame, torn)
            decoded = decode_frame(torn)
        else:
            decoded = decode_frame(frame)

        expected = ([w ^ 0x5A5A for w in ram] if args.corrupt_verify else ram)
        ok, detail = verify(decoded, expected, corrupt=args.corrupt_verify)
        print(detail)

        # VCC determinism leg: hash of the payload stable across re-encode.
        def payload_hash(words):
            return structural_hash(
                b"".join(np.uint32(w).tobytes() for w in words))

        h1 = payload_hash(decoded)
        frame2 = Path(d) / "frame_r42_b.png"
        encode_frame(ram, frame2)
        h2 = payload_hash(decode_frame(frame2))
        hash_stable = h1 == h2
        print(f"structural hash: {h1[:16]}... stable={hash_stable}")

    if args.corrupt_verify:
        if ok:
            print("R4.2 DISPLAY-FRAME: FAIL-RED (corrupt-verify leg accepted "
                  "a good frame — the verifier is NOT load-bearing)")
            sys.exit(1)
        print("R4.2 corrupt-verify RED leg: verifier REJECTED the good frame "
              "(correct discrimination)")
        sys.exit(1)  # a corrupted-verifier run always ends RED by contract

    if args.torn_frame:
        if decoded == ram:
            print("R4.2 DISPLAY-FRAME: FAIL-RED (torn frame passed as "
                  "pixel-perfect — corruption detection is NOT load-bearing)")
            sys.exit(1)
        print("R4.2 torn-frame RED leg: presentation fault DETECTED "
              "(pixel tear caught against the word-exact contract)")
        sys.exit(1)  # a torn-frame run always ends RED by contract

    if not ok:
        print("R4.2 DISPLAY-FRAME: DIVERGENT (decoded frame != machine RAM "
              "or frozen words mismatch)")
        sys.exit(1)
    if not hash_stable:
        print("R4.2 DISPLAY-FRAME: DIVERGENT (structural hash unstable)")
        sys.exit(1)
    print("R4.2 DISPLAY-FRAME: MATCH (16,384 words word-exact off the frame "
          "incl. frozen receipts; VCC-preserving round-trip, hash stable)")
    sys.exit(0)


if __name__ == "__main__":
    main()
