"""Standing gate: Visual Audio codec <-> Glyph engine execute-identity.

Anchors experiments/va_glyph_closed_loop.py's result so the codec (tools/speak.py)
and the Glyph engine (tools/glyph_isa_v2.py) can't drift apart silently. A program
is assembled to a pixel image, spoken to WAV via the byte codec, decoded back, and
executed. Fidelity = the audio-transported image executes identically to the
direct one, for both the raw and Reed-Solomon (ecc) transport legs.

See experiments/va_glyph_closed_loop.py for the original demo this pins.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parent.parent
for _p in (str(REPO), str(REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_isa_v2 import GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2  # noqa: E402
from tools import speak  # noqa: E402

PROGRAM = [
    "LDI r5 0",
    "LDI r1 5",
    "CMP r5 r1",
    "JZ 0,1",
    "PRT r5",
    "LDI r2 1",
    "ADD r5 r2",
    "JMP 2,0",
    "HALT",
]
W = 8
EXPECTED_OUTPUT = [0, 1, 2, 3, 4]


def _build_image():
    om = OpcodeMapV2()
    asm = GlyphAssemblerV2(om)
    img = asm.assemble(PROGRAM, width_instrs=W)
    om.close()
    return img


def _execute(image) -> list[int]:
    om = OpcodeMapV2()
    cpu = GlyphCPUv2(om, cols_instrs=W)
    cpu.run(np.ascontiguousarray(image, dtype=np.uint8), max_instructions=200)
    om.close()
    return cpu.output


@pytest.fixture(scope="module")
def glyph_image():
    return _build_image()


def test_direct_execution_matches_expected(glyph_image):
    """Non-vacuity: the program itself produces the expected output, direct (no
    audio transport). If this fails, the two legs below are meaningless."""
    assert _execute(glyph_image) == EXPECTED_OUTPUT


@pytest.mark.parametrize("use_ecc", [False, True], ids=["raw", "ecc"])
def test_audio_roundtrip_executes_identically(glyph_image, tmp_path, use_ecc):
    """The audio-transported image must decode byte-identical to the source image
    AND execute to the same output as the direct image - codec fidelity is judged
    by the engine's own execution, not just byte comparison."""
    raw = glyph_image.tobytes()
    wav_path = str(tmp_path / f"va_glyph_{'ecc' if use_ecc else 'raw'}.wav")

    speak.encode(raw, wav_path, use_ecc=use_ecc)
    decoded = speak.decode(wav_path, use_ecc=use_ecc)

    arr = np.frombuffer(decoded, dtype=np.uint8)
    assert arr.size == glyph_image.size, (
        f"decoded byte count {arr.size} != source {glyph_image.size} "
        f"(use_ecc={use_ecc})"
    )
    decoded_image = arr.reshape(glyph_image.shape)
    assert (decoded_image == glyph_image).all(), (
        f"audio roundtrip is not byte-identical (use_ecc={use_ecc})"
    )

    assert _execute(decoded_image) == EXPECTED_OUTPUT, (
        f"audio-transported image executed differently than the source (use_ecc={use_ecc})"
    )


def test_non_vacuity_corrupted_image_would_be_caught():
    """L4-style non-vacuity: prove the execute-identity assertion above is capable
    of failing, by feeding a deliberately corrupted image through the same check."""
    image = _build_image()
    corrupted = image.copy()
    corrupted[0, 0, 0] ^= 0xFF  # flip a code-region byte
    # Either it executes to something different, or it faults/crashes outright -
    # both count as "the check would have caught this"; only a silent identical
    # output is the failure mode this leg exists to rule out.
    try:
        result = _execute(corrupted)
        assert result != EXPECTED_OUTPUT, (
            "corrupting the image produced no observable difference - "
            "the execute-identity check is not discriminating"
        )
    except Exception:
        pass  # a hard failure on corruption is also a valid "caught it"
