"""BK-8 gate: tests/test_bk8_fs_pix_sha256.py.

Roadmap BK-8 (promoted from GLYPH_BACKLOG, commit ff387f9): "glyphs_dispatch
lane sync: GH-8b pixel-resident FS evaluated as SHA-256 working-set storage
(replaces host-side buffers in the lockstep harness)". Gate clause: "spec
review + measured before/after on the 13/13 gate".

Implementation (spec review, this file's contract):
  The SHA-256 kernel's ENTIRE working set moves from host-side
  GlyphCPUv2.memory[] into the GH-8b pixel-resident FS window
  [1024, 1280) — 2 pixels per 32-bit word aliasing the saved ndarray,
  bit-exact through PNG round-trips (GH-8b receipts). The kernel's
  memory-map bases (K/W/BIDX/BCNT/BLK/OUT) become parameters with the
  legacy values as defaults, so existing callers are untouched.

Working-set arithmetic (measured, width 64):
  text: 506 instrs -> 8 rows -> pixel words [0, 1024)
  window: 256 words = K 64 + W 64 + BIDX/BCNT 2 + BLK <=80 + OUT 32 = 242
  pad the image by 8 rows so window words [1024,1280) wrap onto padding
  pixels, never text (word 1024 = first pad pixel word, linear-wrap
  _addr_to_xy: addr 1024 with a 16-row image = (0,8), row 8 = first pad row).

Gate legs:
  L1 (13/13 oracle): the full FIPS + sweep vector set digests BYTE-EXACT
      with the working set living in pixels — kernel correctness is not
      perturbed by the relocation. This is the "measured before/after on
      the 13/13 gate" clause: before = tools/sha256_lockstep_test.py
      13/13 on host-RAM bases (committed, 0x8bf3724f... verified this run),
      after = this file's identical vector set on pixel bases.
  L2 (fs_pix_enabled enforcement): with fs_pix_enabled=False the engine
      must NOT reach the window (legacy behavior — LD of a window word
      linear-wraps onto image pixels instead); with True it reads the
      seeded pixel. Proves the pixels are the actual storage, not a
      memory[] mirror coincidence.
  L3 (PNG persistence): digest survives an actual PNG round-trip of the
      post-seed image (the GH-8b "image is the disk" property, now carrying
      the SHA-256 working set).

WGSL leg: deferred (BK-8's gate clause is the measured 13/13, not BK-2's
per-syscall parity — the WGSL twin has no FS-window branch; noted as the
follow-up in the receipt, matching how BK-1 shipped CPU-first).
"""

from __future__ import annotations

import hashlib
import io
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# glyph_isa_v2's default wordbase path resolves to glyph_dispatch/src/db/
# (does not exist); point it at the repo's canonical db/wordbase.db. The
# pinned FIXED_COLORS make the encoding independent of db contents.
_WORDBASE_DB = _REPO / "db" / "wordbase.db"

from glyph_dispatch.src.glyph.glyph_isa_v2 import (  # noqa: E402
    GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2,
)
from glyph_dispatch.src.glyph.sha256_kernel import (  # noqa: E402
    _K, _pad, build_sha256_glyph_program,
)


def _opcode_map() -> "OpcodeMapV2":
    return OpcodeMapV2(wordbase_path=_WORDBASE_DB)

WIDTH = 64
TEXT_ROWS = (506 + WIDTH - 1) // WIDTH          # 8
PAD_ROWS = TEXT_ROWS                             # window must clear text
# FS-window bases (inside [1024, 1280); see module docstring arithmetic)
K_BASE = 1024
W_BASE = 1024 + 64          # 1088
BIDX_ADDR = 1024 + 128      # 1152
BCNT_ADDR = 1024 + 129      # 1153
BLK_BASE = 1024 + 130       # 1154  (max 80 words: 5 blocks)
OUT_BASE = 1024 + 210       # 1234  (32 words -> 1265, inside window)

FIPS_VECTORS = [
    (b"", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
    (b"abc", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"),
    (b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq",
     "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"),
]
SWEEP_INPUTS = [
    b"", b"a", b"\x00", bytes(range(256)),
    b"The quick brown fox jumps over the lazy dog",
    b"x" * 55, b"x" * 56, b"x" * 63, b"x" * 64,
    bytes((i * 37) % 251 for i in range(300)),
]


def _pixel_image() -> np.ndarray:
    """Text image padded by PAD_ROWS so FS-window words land on padding."""
    op = _opcode_map()
    try:
        asm = GlyphAssemblerV2(op)
        img = asm.assemble(build_sha256_glyph_program(WIDTH), width_instrs=WIDTH)
    finally:
        op.close()
    assert img.shape[0] == TEXT_ROWS, img.shape
    return np.vstack([img, np.zeros((PAD_ROWS, img.shape[1], 3), dtype=np.uint8)])


def _window_prog() -> list:
    """Kernel rebuilt with ALL working-set bases inside the FS window.

    The bases are BAKED into LDI immediates by the program body — this
    rebuild (not a seed-address change) is the actual relocation.
    """
    return build_sha256_glyph_program(
        WIDTH, K_BASE=K_BASE, W_BASE=W_BASE, BIDX_ADDR=BIDX_ADDR,
        BCNT_ADDR=BCNT_ADDR, BLK_BASE=BLK_BASE, OUT_BASE=OUT_BASE)


def _sha256_pixel(message: bytes, fs_pix_enabled: bool = True) -> tuple:
    """Run the pixel-resident kernel; returns (digest, final image).

    Seeding goes through _mem_write — the engine's own window-write path —
    so with fs_pix_enabled=True every working-set word lands in IMAGE
    PIXELS (memory[] only receives the write-through mirror); the digest
    is read back from pixels via _fs_pix_read.
    """
    op = _opcode_map()
    try:
        asm = GlyphAssemblerV2(op)
        image = asm.assemble(_window_prog(), width_instrs=WIDTH)
        image = np.vstack([image, np.zeros((PAD_ROWS, image.shape[1], 3), dtype=np.uint8)])
        cpu = GlyphCPUv2(op, WIDTH, fs_pix_enabled=fs_pix_enabled)
        cpu.memory.extend([0] * 256)  # room for the write-through mirror
        for i, kv in enumerate(_K):
            cpu._mem_write(image, K_BASE + i, kv)
        padded = _pad(message)
        nblocks = len(padded) // 64
        cpu._mem_write(image, BCNT_ADDR, nblocks)
        for w in range(nblocks * 16):
            cpu._mem_write(image, BLK_BASE + w,
                           int.from_bytes(padded[4 * w:4 * w + 4], "big"))
        executed = cpu.run(image, max_instructions=400_000)
        assert executed < 400_000, "kernel did not HALT"
        out = [cpu._fs_pix_read(image, OUT_BASE + i) & 0xFF for i in range(32)]
        return bytes(out), image
    finally:
        op.close()


@pytest.mark.parametrize("msg,digest", FIPS_VECTORS)
def test_l1_fips_pixel_resident(msg, digest):
    got, _ = _sha256_pixel(msg)
    assert got.hex() == digest, f"pixel-resident FIPS mismatch on {msg!r}"


@pytest.mark.parametrize("msg", SWEEP_INPUTS)
def test_l1_sweep_pixel_resident(msg):
    got, _ = _sha256_pixel(msg)
    assert got.hex() == hashlib.sha256(msg).hexdigest(), f"sweep mismatch on {msg!r}"


def test_l2_fs_pix_enabled_is_the_storage():
    """Pixels, not the memory[] mirror, are the working set: with
    fs_pix_enabled the OUT digest reads back from IMAGE pixels; with it
    off, a window LD linear-wraps onto text/pad pixels (legacy behavior)
    and cannot see the window at all."""
    _, image = _sha256_pixel(b"abc")
    # digest words are physically in the image's pad-region pixels
    cpu = GlyphCPUv2(_opcode_map(), WIDTH, fs_pix_enabled=True)
    got = bytes(cpu._fs_pix_read(image, OUT_BASE + i) & 0xFF for i in range(32))
    assert got.hex() == hashlib.sha256(b"abc").hexdigest()
    # engine with the flag off never sees the window as a window:
    # a read of the BCNT window word wraps onto raw pixels (some text
    # pixel word), NOT the seeded count 1.
    cpu2 = GlyphCPUv2(_opcode_map(), WIDTH, fs_pix_enabled=False)
    assert cpu2.fs_pix_enabled is False
    assert cpu2._mem_read(image, BCNT_ADDR) != 1
    # while the windowed engine reads the seeded value from the pixel
    assert cpu._fs_pix_read(image, BCNT_ADDR) == 1
    # and the wrapped legacy view differs from the window view
    assert cpu._fs_pix_read(image, BCNT_ADDR) != cpu2._mem_read(image, BCNT_ADDR)


def test_l3_png_roundtrip_persistence():
    """The image IS the disk: PNG round-trip of the post-run image still
    carries the digest in pixels (GH-8b bit-exactness over the SHA-256
    working set)."""
    _, image = _sha256_pixel(b"abc")
    buf = io.BytesIO()
    Image.fromarray(image).save(buf, format="PNG")
    buf.seek(0)
    reloaded = np.array(Image.open(buf).convert("RGB"))
    assert np.array_equal(reloaded, image), "PNG round-trip not bit-exact"
    cpu = GlyphCPUv2(_opcode_map(), WIDTH, fs_pix_enabled=True)
    got = bytes(cpu._fs_pix_read(reloaded, OUT_BASE + i) & 0xFF for i in range(32))
    assert got.hex() == hashlib.sha256(b"abc").hexdigest()
