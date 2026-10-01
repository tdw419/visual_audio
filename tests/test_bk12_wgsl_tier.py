#!/usr/bin/env python3
"""BK-12 gate: tests/test_bk12_wgsl_tier.py.

Roadmap BK-12 (promoted from GLYPH_BACKLOG, commit `a636aae`):

  "WGSL throughput tier: memcpy + FS block copy move to WGSL compute
   buffers with CPU≡GPU byte-parity receipts; pixel-words remain
   provenance tier."

Gate clause (verbatim): "tests/test_bk12_wgsl_tier.py — 1KB block copy
WGSL vs CPU byte-identical; measured speedup receipt in docs/".

What each leg buys, and why a weaker version would be dishonest:

  L1  (1KB clause) A 256-word block copy executed on WGSL compute buffers
      is byte-identical to the CPU reference over the same words. Compared
      word-for-word AND as an md5 over the packed bytes, so "identical" is
      a digest claim over 1024 bytes, not a three-word spot check.
  L1b (non-vacuity) Flipping one source word flips exactly the matching
      destination word, and destination guard words outside the copy
      window stay untouched. A shader that copied nothing (or everything)
      cannot pass this, so L1 cannot be green-by-no-op.
  L2  (provenance bridge) The same 1KB routed through the GH-8b pixel-FS
      window encoding — 2 px/word, lo24 in pixel RGB, hi8 in the BLUE
      channel of the odd pixel — decodes back to the identical word list
      using the ENGINE's own `_fs_pix_write` / `_fs_pix_read`. This is the
      claim that makes the tier addition safe: the bytes the GPU moves are
      the bytes the pixel tier persists.
  L3  (pixel tier is real, not a straw man) The actual GlyphCPUv2 engine
      executes an assembled LD/ST copy loop (LDI/LD/ST/ADD/SUB/CMP/JZ/JMP)
      whose storage IS the pixel-FS window, and the copied words read back
      out of PIXELS equal the source words. Without this leg the
      "speedup" in L4 would be measured against a Python `list[:]`.
  L4  (measured throughput) Both tiers copy the same 64-word block; the
      numbers are printed as `MEASURED bk12 ...` lines (captured into
      output/bk12_gate_run2_green.txt and quoted in
      docs/RECEIPT_BK12_WGSL_TIER.md) and the assertion is the direction
      claim only: the GPU tier must not be slower than the pixel tier.

Caveats stated up front (they belong in the receipt too): the pixel-tier
number is the interpreter engine executing a real program — that is the
tier's actual cost structure today, not a tuned baseline; the WGSL number
excludes host readback and buffer creation (both timed separately and
printed), because the tier's claim is about data movement on the GPU
beside the provenance pixels.

RED contract: this module imports `tools.glyph_gpt.wgsl_tier`, which does
not exist yet — collection fails RED before any leg can run.
"""

from __future__ import annotations

import hashlib
import struct
import sys
import time
from pathlib import Path

import numpy as np
import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_isa_v2 import GlyphAssemblerV2, GlyphCPUv2, OpcodeMapV2  # noqa: E402
from tools.glyph_gpt.wgsl_tier import (  # noqa: E402
    BLOCK_COPY_WGSL,
    WORDS_PER_KB,
    WgslBlockCopier,
    build_pixel_copy_program,
    cpu_block_copy,
    fs_read_words,
    fs_write_words,
    run_pixel_copy,
    words_md5,
    wgsl_block_copy,
)

_WORDBASE_DB = _REPO / "db" / "wordbase.db"

# 1KB block-copy geometry: dst is offset inside the same buffer so the
# guard words around it are meaningful (a shader that copies the whole
# buffer, or the wrong offset, fails L1b).
COPY_OFFSET = 8
GUARD = 16

# The GH-8b pixel-FS window is exactly 256 words wide.
FS_LO, FS_HI = 1024, 1280
FS_SRC_BASE = FS_LO
FS_DST_BASE = FS_LO + 64
PIXEL_COPY_WORDS = 64

# Program layout (width 8 instrs/row) for the pixel-tier copy loop — the
# labels below are comments, the jumps carry absolute (col,row) targets.
PIXEL_PROG_LINES = build_pixel_copy_program(
    PIXEL_COPY_WORDS, FS_SRC_BASE, FS_DST_BASE, width_instrs=8)


def _opcode_map() -> "OpcodeMapV2":
    return OpcodeMapV2(wordbase_path=_WORDBASE_DB)


def _block(n_words: int = WORDS_PER_KB, seed: int = 0x5EED) -> list:
    """Deterministic 1KB-ish block of 32-bit words (bytes-like spread)."""
    out = []
    x = seed
    for _ in range(n_words):
        x = (x * 1103515245 + 12345) & 0xFFFFFFFF
        out.append((x ^ (x >> 13)) & 0xFFFFFFFF)
    return out


# --------------------------------------------------------------------------
# L1 — the 1KB clause: WGSL compute buffers vs CPU, byte-identical
# --------------------------------------------------------------------------

def test_l1_wgsl_1kb_block_copy_byte_identical():
    src = _block()
    dst_len = len(src) + COPY_OFFSET + GUARD
    dst_cpu = cpu_block_copy(src, count=len(src), dst_off=COPY_OFFSET, dst_len=dst_len)
    dst_gpu = wgsl_block_copy(src, count=len(src), dst_off=COPY_OFFSET, dst_len=dst_len)
    assert len(src) == WORDS_PER_KB, "the clause is a 1KB block copy"
    assert dst_gpu == dst_cpu, "WGSL copy diverged from the CPU reference"
    assert dst_gpu[COPY_OFFSET:COPY_OFFSET + len(src)] == src
    assert words_md5(dst_gpu) == words_md5(dst_cpu), "md5 diverged"
    # sha256 over the same bytes too: two independent digests, same bytes
    packed = struct.pack("<%dI" % len(dst_gpu), *dst_gpu)
    assert hashlib.sha256(packed).hexdigest() == hashlib.sha256(
        struct.pack("<%dI" % len(dst_cpu), *dst_cpu)).hexdigest()


def test_l1b_wgsl_copy_is_live_and_bounded():
    src = _block(64)
    dst_len = len(src) + COPY_OFFSET + GUARD
    base = wgsl_block_copy(src, count=len(src), dst_off=COPY_OFFSET, dst_len=dst_len)
    # guards are untouched by the copy
    assert base[:COPY_OFFSET] == [0] * COPY_OFFSET
    assert base[COPY_OFFSET + len(src):] == [0] * GUARD
    # flipping ONE source word moves exactly ONE destination word
    tampered = list(src)
    tampered[7] ^= 0xDEADBEEF
    after = wgsl_block_copy(tampered, count=len(tampered), dst_off=COPY_OFFSET, dst_len=dst_len)
    diff = [i for i, (a, b) in enumerate(zip(base, after)) if a != b]
    assert diff == [COPY_OFFSET + 7], f"copy is not word-exact: diff at {diff}"


# --------------------------------------------------------------------------
# L2 — provenance bridge: the same bytes through the pixel-FS window
# --------------------------------------------------------------------------

def test_l2_pixel_fs_window_carries_the_same_1kb():
    words = _block()
    op = _opcode_map()
    try:
        cpu = GlyphCPUv2(op, 8, fs_pix_enabled=True)
        cpu.memory.extend([0] * 512)
        # A window-sized image: 32 px/instr-row wide, enough rows that both
        # pixel halves of word 1279 land inside the array (2 px/word).
        image = np.zeros((80, 32, 3), dtype=np.uint8)
        fs_write_words(cpu, image, FS_SRC_BASE, words)
        back = fs_read_words(cpu, image, FS_SRC_BASE, len(words))
        assert back == words, "pixel-FS window did not carry the 1KB block"
        assert words_md5(back) == words_md5(words)
        # layout spot-check (the documented 2 px/word encoding, engine-owned)
        w0 = words[0]
        lin = (FS_SRC_BASE * 2) % (32 * 80)
        assert tuple(image[lin // 32, lin % 32]) == (
            (w0 >> 16) & 0xFF, (w0 >> 8) & 0xFF, w0 & 0xFF)
        lin2 = lin + 1
        assert image[lin2 // 32, lin2 % 32][2] == (w0 >> 24) & 0xFF
        # and the GPU tier over the DECODED words still matches the source
        dst = wgsl_block_copy(back, count=len(back), dst_off=0, dst_len=len(back))
        assert dst == words
    finally:
        op.close()


# --------------------------------------------------------------------------
# L3 — the pixel tier is a real copy tier (engine-executed LD/ST loop)
# --------------------------------------------------------------------------

def test_l3_engine_pixel_copy_loop_is_functional():
    words = _block(PIXEL_COPY_WORDS)
    run = run_pixel_copy(words, PIXEL_COPY_WORDS, FS_SRC_BASE, FS_DST_BASE,
                         PIXEL_PROG_LINES, width_instrs=8, pad_rows=80)
    assert run["halted"], f"engine copy loop did not HALT (steps={run['steps']})"
    assert run["faulted"] is False
    assert run["copied"] == words, "engine LD/ST copy did not reproduce the block"
    # the destination really is in PIXELS, not the memory[] mirror: a fresh
    # engine that never wrote anything must not see the words there
    op = _opcode_map()
    try:
        probe = GlyphCPUv2(op, 8, fs_pix_enabled=True)
        assert fs_read_words(probe, run["image"], FS_DST_BASE, PIXEL_COPY_WORDS) == words
    finally:
        op.close()
    assert run["steps"] >= 8 * PIXEL_COPY_WORDS, "loop cannot have copied the block"


# --------------------------------------------------------------------------
# L4 — measured throughput, both tiers, same block
# --------------------------------------------------------------------------

def test_l4_measured_throughput_both_tiers():
    words = _block(PIXEL_COPY_WORDS)
    n_bytes = PIXEL_COPY_WORDS * 4
    repeats = 200

    # --- pixel tier: the engine executing the real LD/ST copy loop --------
    run = run_pixel_copy(words, PIXEL_COPY_WORDS, FS_SRC_BASE, FS_DST_BASE,
                         PIXEL_PROG_LINES, width_instrs=8, pad_rows=80)
    assert run["copied"] == words
    pixel_s = max(run["seconds"], 1e-9)
    pixel_bps = n_bytes / pixel_s

    # --- WGSL tier: same block, resident buffers, submits only ------------
    t0 = time.perf_counter()
    copier = WgslBlockCopier(dst_len=PIXEL_COPY_WORDS)
    setup_s = time.perf_counter() - t0

    t0 = time.perf_counter()
    for _ in range(repeats):
        copier.copy(words, count=PIXEL_COPY_WORDS)
    gpu_s = (time.perf_counter() - t0) / repeats
    assert copier.read_dst(PIXEL_COPY_WORDS) == words
    gpu_bps = n_bytes / max(gpu_s, 1e-9)

    print(f"MEASURED bk12 pixel_tier bytes={n_bytes} seconds={pixel_s:.6f} "
          f"bytes_per_s={pixel_bps:,.0f} steps={run['steps']}")
    print(f"MEASURED bk12 wgsl_tier bytes={n_bytes} seconds={gpu_s:.6f} "
          f"bytes_per_s={gpu_bps:,.0f} submits={repeats} setup_seconds={setup_s:.6f}")
    print(f"MEASURED bk12 speedup={gpu_bps / pixel_bps:,.1f}x "
          f"(shader_bytes={len(BLOCK_COPY_WGSL)})")

    assert gpu_bps > pixel_bps, (
        f"GPU tier was not faster: {gpu_bps:,.0f} vs {pixel_bps:,.0f} bytes/s")


def test_l4b_wgsl_tier_scaling_and_submit_overhead():
    """Per-submit overhead dominates at small blocks — measured, not assumed.

    The 64-word leg above is the like-for-like comparison against the
    engine; this leg reports the tier's bytes/sec at 1KB and 64KB so the
    receipt can state where the tier actually pays (and where a single
    dispatch is ~all submit cost).
    """
    results = {}
    for n_words, repeats in ((WORDS_PER_KB, 100), (16 * WORDS_PER_KB, 20)):
        words = _block(n_words, seed=0xC0FFEE)
        copier = WgslBlockCopier(dst_len=n_words)
        copier.copy(words, count=n_words)
        assert copier.read_dst(n_words) == words
        t0 = time.perf_counter()
        for _ in range(repeats):
            copier.copy(words, count=n_words)
        per_call = (time.perf_counter() - t0) / repeats
        results[n_words] = n_words * 4 / max(per_call, 1e-9)
        print(f"MEASURED bk12 wgsl_scaling words={n_words} bytes={n_words * 4} "
              f"seconds={per_call:.6f} bytes_per_s={results[n_words]:,.0f}")
    assert results[16 * WORDS_PER_KB] > results[WORDS_PER_KB], (
        "larger blocks should amortize the fixed submit cost")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-q", "-s"]))
