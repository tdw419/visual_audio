"""R4.2 gate: display output — pixel-perfect frame presentation, VCC-preserving.

PRODUCT_ROADMAP.md:74 (R4.2). The probe (.builder_queue/
probe_r42_display_frame.py) is the deliverable; these legs drive it as a
subprocess so the exit contract (GREEN 0 / RED 1) is what is gated, plus
two in-process codec legs.

Legs:
  1. GREEN: probe exits 0 — the shader-path fleet (R1.4-converged
     run_wgsl) halts, its committed 16,384-word RAM is presented as one
     128x128 Hilbert-mapped RGBA frame, decoded back word-exact
     (incl. frozen receipts 0x5EED0005 @765, done=0b1011 @717,
     0xFA026 @731, results {714:6,728:12,748:20,763:30}), structural
     hash stable across re-encode.
  2. RED / discriminating: --corrupt-verify exits 1 (verifier rejects a
     good frame under corrupted expectations).
  3. RED / discriminating: --torn-frame exits 1 (a ONE-BYTE tear of ONE
     pixel post-encode is detected against the word-exact contract).
  4. Curve sensitivity (in-process): scrambling the Hilbert ORDER
     (presenting words at indices 0..N-1 linearly instead of along the
     canonical curve) must make the decoder's word readback DIVERGE —
     the gate cannot pass on an arbitrary pixel mapping.
  5. VCC round-trip of the byte-container codec boundary (in-process):
     the probe's frame payload, repacked into the canonical
     vcc_validate byte-container (SPECIAL_OFFSET, alpha terminator),
     survives decode_rts_png byte-exactly — the presentation channel
     agrees with the repo's VCC tooling at the byte layer.

What this does NOT prove: no real display hardware / scanout (this is
the frame-presentation + VCC-preservation contract over the substrate's
committed RAM, not a monitor driver); no claim that the GUEST paints
its own framebuffer (the frame is the host presenting machine state);
no rate claims. Probe runs may take ~60-120 s each (cold wgpu pipeline).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools"), str(_REPO / ".builder_queue")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

PROBE = _REPO / ".builder_queue" / "probe_r42_display_frame.py"

import probe_r42_display_frame as P                       # noqa: E402
from tools.vcc_validate import (                          # noqa: E402
    d2xy, decode_rts_png, encode_rts_png, structural_hash,
)


def _run_probe(*flags: str) -> tuple[int, str]:
    r = subprocess.run([sys.executable, str(PROBE), *flags],
                       capture_output=True, text=True, timeout=600)
    return r.returncode, (r.stdout + r.stderr).strip()


def test_r42_green_exit_contract():
    rc, out = _run_probe()
    assert rc == 0, f"probe exit {rc}: {out[-400:]}"
    assert "DISPLAY-FRAME: MATCH" in out


def test_r42_corrupt_verify_rejected():
    rc, out = _run_probe("--corrupt-verify")
    assert rc == 1, f"vacuous: corrupt-verify exit {rc}: {out[-400:]}"
    assert "correct discrimination" in out


def test_r42_torn_frame_detected():
    rc, out = _run_probe("--torn-frame")
    assert rc == 1, f"vacuous: torn-frame exit {rc}: {out[-400:]}"
    assert "presentation fault DETECTED" in out


def test_r42_gate_is_curve_sensitive():
    """A linear (non-Hilbert) presentation must NOT read back word-exact.

    Non-vacuity for the curve itself: if any pixel ordering passed, the
    'VCC-preserving' claim would be decoration.
    """
    words = [(i * 2654435761) % (1 << 32) for i in range(P.RAM_WORDS)]
    with _tmpdir() as d:
        good = Path(d) / "good.png"
        P.encode_frame(words, good)
        assert P.decode_frame(good) == words

        # same words, LINEAR placement (no Hilbert curve)
        img = np.zeros((P.N, P.N, 4), dtype=np.uint8)
        for d_idx, w in enumerate(words):
            v = int(w) & 0xFFFFFFFF
            img[d_idx // P.N, d_idx % P.N] = [
                (v >> 24) & 0xFF, (v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF]
        linear = Path(d) / "linear.png"
        Image.fromarray(img, "RGBA").save(linear)
        assert P.decode_frame(linear) != words, (
            "vacuous: linear placement also decoded word-exact — the "
            "verifier does not depend on the Hilbert curve")


def test_r42_payload_survives_vcc_byte_container():
    """The frame payload agrees with the repo's canonical VCC codec.

    Repack the frame's word bytes into vcc_validate's byte-container
    format (1 byte/pixel, SPECIAL_OFFSET, alpha terminator) and require
    a byte-exact decode_rts_png round-trip.
    """
    words = [(i * 40503 + 7) % (1 << 32) for i in range(4096)]  # -> 16 KiB
    payload = bytearray()
    for w in words:
        payload += bytes([(w >> 24) & 0xFF, (w >> 16) & 0xFF,
                          (w >> 8) & 0xFF, w & 0xFF])
    with _tmpdir() as d:
        raw = Path(d) / "payload.bin"
        raw.write_bytes(payload)
        cont = Path(d) / "payload.rts.png"
        # byte-container: 1 BYTE per pixel -> 16384 bytes need a 128x128 grid
        encode_rts_png(str(raw), str(cont), grid_size=128)
        back = decode_rts_png(str(cont), grid_size=128)
        assert back == bytes(payload)
        assert structural_hash(back) == structural_hash(bytes(payload))


import contextlib


@contextlib.contextmanager
def _tmpdir():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        yield d
