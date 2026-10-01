#!/usr/bin/env python3
"""tests/test_bk24_streaming_write.py — BK-24 streaming sys_write gate.

Item 18 (CLAIM QUEUE ROUND 9, PRODUCT_LANE_STATE.md): generalize the GH-23
sys_write tile beyond the 16-byte single-flush window into STREAMING append.

RED (shown pre-landing, this repo, output/bk24_red_probe.txt):
  the fixed-window tile re-copies words 718..721 on EVERY write call, so a
  second flush overwrites the first at byte 17 of the stream — the probe's
  two-flush fixture left the window holding only flush 2's bytes.

GREEN contract (this file):
  L1  (toolchain-free) the tile text appends at the cursor: it reads
      mem[724], stores 4 words through it, stores cursor+4 back, and
      mirrors 718..721 — structural pins so the gate discriminates even
      without riscv64-unknown-elf-gcc.
  L2  (toolchain) TWO flushes: the ring holds BOTH flushes' bytes in
      order ('AAAAAAAA' then 'BBBBBBBB' at ring words 768..771, 772..775)
      and the cursor advanced 768 -> 776. Under the old contract flush 1
      was lost — this leg is the item's RED-first core.
  L3  (toolchain) the item-18 GREEN line verbatim: write(1, buf, 64)
      delivers all 64 bytes byte-exact through the ring.
  L4  (toolchain) the legacy 718..721 window mirror still works (BK-11
      consumers), and the GH-23 C-suite regression (malloc/qsort/printf)
      still passes with the streaming tile in place.
  L5  ABI version bumped 0x0002001A -> 0x0002001B (toolchain-free).
"""
from __future__ import annotations

import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO), str(_REPO / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tools.glyph_gpt.atlas import build_default_atlas            # noqa: E402
from tools.glyph_gpt.runner import GlyphRunner                   # noqa: E402
from tools.glyph_gpt.baker import libc_runtime_kernel_image      # noqa: E402
from tools.glyph_gpt.libc_runtime import (                       # noqa: E402
    _gh23_sys_write_tile,
    GH23_WRITE_CURSOR,
    GH23_WRITE_RING_BASE,
)
from tests.test_gh23_libc_runtime import (                       # noqa: E402
    FIXTURE_C, LIBC_C, _compile_elf, _load_posix_program,
    GH23_STDOUT_WORDS, GH23_EXIT_CODE,
)

_GCC = "riscv64-unknown-elf-gcc"


def _require_toolchain() -> None:
    if shutil.which(_GCC) is None:
        pytest.skip("riscv64-unknown-elf-gcc not installed")


def _ring_bytes(mem, start_word: int, n_words: int) -> bytes:
    return b"".join(
        int(mem[w]).to_bytes(4, "little") for w in range(start_word, start_word + n_words)
    )


# ── L1: structural pins (toolchain-free) ─────────────────────────────────

def test_l1_tile_is_streaming_append():
    """The write tile reads the cursor (mem[724]), appends THROUGH it, and
    writes cursor+4 back — not a fixed 718..721 re-copy."""
    tile = _gh23_sys_write_tile()
    body = [ln.split(";")[0].strip() for ln in tile.splitlines()]
    body = [ln for ln in body if ln and not ln.startswith(":")]
    # reads the cursor
    assert "LDI r15 724" in body
    idx_ld_cursor = body.index("LD r11 r15")
    # appends at the cursor (store through r11) BEFORE storing cursor+4 back
    assert "ST r11 r7" in body
    idx_st_back = body.index("ST r15 r11", idx_ld_cursor)
    assert body.index("ST r11 r7", idx_ld_cursor) < idx_st_back
    # and mirrors the legacy window
    for w, reg in ((718, "r7"), (719, "r8"), (720, "r9"), (721, "r10")):
        assert f"LDI r15 {w}" in body
        assert f"ST r15 {reg}" in body
    # the gate is not vacuous: the OLD tile had no cursor LD at all
    old_tile_shape = ("LDI r15 718" in body) and ("LD r11 r15" not in body)
    assert not old_tile_shape, "tile still looks like the fixed-window copy"


def test_l5_abi_version_bumped():
    """The libc-mode image carries ABI 0x0002001B (streaming write)."""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "bk24.npy"
        libc_runtime_kernel_image(build_default_atlas(), out_path=out)
        runner = GlyphRunner(out, ram_words=16384)
        receipt = runner.run(max_instructions=60000, trace=True)
        assert receipt["halted"] is True, receipt.get("error", receipt)
        assert receipt["faulted"] is False, receipt
        assert receipt["memory"][952] == 0x0002001B, hex(receipt["memory"][952])


# ── the two-flush fixture (the item's RED-first core) ────────────────────

TWO_FLUSH_C = r"""\
extern void exit(int code);
extern void printf(const char *fmt, long a, long b);
extern void stdout_flush(void);

void _start(void) {
    printf("AAAAAAAA", 0, 0);
    stdout_flush();
    printf("BBBBBBBB", 0, 0);
    stdout_flush();
    exit(0);
}
"""

WIDE_FLUSH_C = r"""\
extern void exit(int code);
extern int write(int fd, const void *buf, unsigned len);

/* 64 bytes: '01234567' x8, delivered with ONE write call. The spatial
   libc's out_buf is 64 bytes (BK-24), so the flush rides one ECALL. */
static char big[64] __attribute__((aligned(16)));

void _start(void) {
    for (unsigned i = 0; i < 64; i++) big[i] = '0' + (char)(i & 7);
    write(1, big, 64);
    exit(0);
}
"""


def _bake_and_run(tmp: Path, c_text: str, libc_text: str):
    elf = _compile_elf(tmp, c_text, libc_text=libc_text)
    program = _load_posix_program(elf)
    out = tmp / "bk24.npy"
    libc_runtime_kernel_image(build_default_atlas(), out_path=out,
                              user_program=program)
    runner = GlyphRunner(out, ram_words=16384)
    receipt = runner.run(max_instructions=300000, trace=True)
    assert receipt["halted"] is True, receipt.get("error", receipt)
    assert receipt["faulted"] is False, receipt
    return receipt


# ── L2: two flushes BOTH survive, in order (was RED under the old tile) ──

@pytest.mark.skipif(shutil.which(_GCC) is None,
                    reason="riscv64-unknown-elf-gcc not installed")
def test_l2_two_flushes_both_survive_in_order():
    with tempfile.TemporaryDirectory() as d:
        receipt = _bake_and_run(Path(d), TWO_FLUSH_C, LIBC_C)
        mem = receipt["memory"]
        assert mem[GH23_EXIT_CODE] == 0
        # Frame ABI (test_gh23_libc_runtime.py FRAME 16): the wrapper's
        # out_flush writes the whole 16-byte window per flush, so each
        # flush lands as ONE 4-word frame — 8 data bytes + 8 zero-pad
        # bytes. Flush 1 = words 768..771, flush 2 = words 772..775.
        ring = _ring_bytes(mem, GH23_WRITE_RING_BASE, 8)
        assert ring[0:8] == b"AAAAAAAA", ring[0:8]
        assert ring[8:16] == b"\0" * 8, ring[8:16]      # frame-1 tail pad
        assert ring[16:24] == b"BBBBBBBB", ring[16:24]  # flush 2 SURVIVES
        assert ring[24:32] == b"\0" * 8, ring[24:32]    # frame-2 tail pad
        # cursor advanced by exactly 2 flushes x 4 words
        assert mem[GH23_WRITE_CURSOR] == GH23_WRITE_RING_BASE + 8, \
            hex(mem[GH23_WRITE_CURSOR])
        # legacy mirror holds the LAST flush (documented contract)
        window = _ring_bytes(mem, GH23_STDOUT_WORDS[0], 4)
        assert window[:8] == b"BBBBBBBB"


# ── L3: the item-18 GREEN line — write(1, buf, 64) delivers 64 bytes ─────

WIDE_LIBC_DELTA = r"""
/* BK-24: widen the libc's output buffer to the streaming span (64 bytes)
   and flush with ONE write call. */
void out_flush(void) {
    if (out_n == 0) return;
    write(1, out_buf, 64);
    out_n = 0;
}
"""


@pytest.mark.skipif(shutil.which(_GCC) is None,
                    reason="riscv64-unknown-elf-gcc not installed")
def test_l3_write64_delivers_all_64_bytes():
    # LIBC_C's out_buf is 16 bytes and out_flush writes 16 — rebuild the
    # libc text with the widened buffer instead of patching text.
    libc_text = LIBC_C.replace(
        "static char out_buf[16] __attribute__((aligned(16)));",
        "static char out_buf[64] __attribute__((aligned(16)));").replace(
        "    if (out_n == 0) return;\n    write(1, out_buf, 16);",
        "    if (out_n == 0) return;\n    write(1, out_buf, 64);").replace(
        "    if (out_n == 16) out_flush();",
        "    if (out_n == 64) out_flush();")
    assert 'out_buf[64]' in libc_text and "write(1, out_buf, 64)" in libc_text
    with tempfile.TemporaryDirectory() as d:
        receipt = _bake_and_run(Path(d), WIDE_FLUSH_C, libc_text)
        mem = receipt["memory"]
        assert mem[GH23_EXIT_CODE] == 0
        stream = _ring_bytes(mem, GH23_WRITE_RING_BASE, 16)
        want = bytes((ord('0') + (i & 7)) for i in range(64))
        assert stream == want, (stream[:16], want[:16])
        assert mem[GH23_WRITE_CURSOR] == GH23_WRITE_RING_BASE + 16
        # the legacy window mirrors the last 16 bytes of the stream
        window = _ring_bytes(mem, GH23_STDOUT_WORDS[0], 4)
        assert window == want[48:64]


# ── L4: GH-23 C-suite regression — streaming tile preserves the old legs ─

@pytest.mark.skipif(shutil.which(_GCC) is None,
                    reason="riscv64-unknown-elf-gcc not installed")
def test_l4_gh23_suite_still_green_on_streaming_image():
    """The landed GH-23 leg-2 contract (printf through the spatial libc,
    qsort, clean exit 0) still holds — through the ring AND the window
    mirror, so the old assertions stay byte-identical."""
    with tempfile.TemporaryDirectory() as d:
        receipt = _bake_and_run(Path(d), FIXTURE_C, LIBC_C)
        mem = receipt["memory"]
        assert mem[GH23_EXIT_CODE] == 0
        b = bytes(b"n=10,20!C") + b"\0" * 7
        stream = _ring_bytes(mem, GH23_WRITE_RING_BASE, 4)
        assert stream == b, stream
        window = _ring_bytes(mem, GH23_STDOUT_WORDS[0], 4)
        assert window == b, window
        assert mem[723] >= 2560 + 4
