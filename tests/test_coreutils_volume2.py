#!/usr/bin/env python3
"""tests/test_coreutils_volume2.py — round-9 supply item 19: coreutils
volume port #2 gate (grep, tr, tee, cut, sort).

Spec (.builder_queue/PRODUCT_LANE_STATE.md, CLAIM QUEUE ROUND 9, item 19):

  BK-25 label: coreutils volume port #2 — grep, tr, tee, cut, sort as
  real C, rv64-unknown-elf-gcc -> transpile -> byte-exact vs native
  POSIX fixtures. Depends on 18 (outputs exceed the window).

Item 18 (BK-24 streaming sys_write, merged e9f9ca4b) is the substrate
this gate consumes: each write(1, buf, n) ECALL appends a 16-byte frame
at the cursor (word 724) into the ring [768, 832), so a tool's WHOLE
output stream survives — not just the legacy 16-byte window 718..721.

Tool contracts (POSIX subsets, honest scope):
  grep PATTERN FILE   print lines containing PATTERN (substring)
  tr SET1 SET2        translate chars in input (|SET1| == |SET2|)
  tee [FILE]          copy input to stdout (stdin-duplication half of
                      tee; the file-write half needs an open() the
                      freestanding ECALL shim does not have — pinned
                      out of scope, see module docstring disclosure)
  cut -dD -fN         print field N of each line (single-char delim)
  sort FILE           sort lines ascending, BYTEWISE (C strcmp order,
                      not locale/numeric — pinned by the 10/9/100 leg)

Every tool is a real, stranger's-C-program-shaped clone embedded in
tools/glyph_gpt/coreutils_port.py (COREUTILS2_TOOL_SOURCES / fixtures)
— one source of truth shared by gate and implementation, same pattern
as BK-11's volume port #1. Output goes through the tool's own 64-byte
buffer flushed ONCE at exit (every landed fixture output is <= 48
bytes), so the stream lands as ceil(n/16) ring frames with the last
frame zero-padded — the gate reconstructs the stream byte-exactly from
ring + cursor.

RED contract: this file imports coreutils2_tool_elf /
COREUTILS2_TOOL_SOURCES / COREUTILS2_FIXTURES, which do not exist until
item 19 lands — collection fails RED. GREEN: per-tool x per-fixture
byte-exact vs the native POSIX reference, cursor arithmetic pinned,
exit 0. What the PASS does NOT prove: no WGSL twin leg (foreign to the
shader threat model per the 0x07/0x12 precedent), no live POSIX binary
diff (reference computed from the POSIX spec in the fixture table, the
BK-10/BK-11 oracle strategy), no file-write half of tee, no locale
collation in sort.
"""
from __future__ import annotations

import shutil
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
    GH23_WRITE_CURSOR,
    GH23_WRITE_RING_BASE,
)
from tools.glyph_gpt.coreutils_port import (                     # noqa: E402 (RED)
    coreutils2_tool_elf,
    COREUTILS2_FIXTURES,
    COREUTILS2_TOOLS,
)
from tests.test_gh23_libc_runtime import (                       # noqa: E402
    _load_posix_program,
    GH23_EXIT_CODE,
)

_GCC = "riscv64-unknown-elf-gcc"
RING_SPAN_WORDS = 64                     # [768, 832) — the BK-24 ring
STREAM_CAP = RING_SPAN_WORDS * 4         # 256 bytes of stream


# ── L0: table sanity + oracle non-vacuity (toolchain-free) ───────────────

def test_l0_fixture_table_sane_and_discriminating():
    """The table carries 3 fixtures per tool, stays inside the ring, has
    at least one >16-byte output per tool (the item's streaming premise:
    outputs exceed the BK-11 window), and the reference is NOT the
    identity (the tool actually transforms its input — the gate cannot
    pass on a pass-through)."""
    assert set(COREUTILS2_TOOLS) == {"grep", "tr", "tee", "cut", "sort"}
    for tool in COREUTILS2_TOOLS:
        fxs = COREUTILS2_FIXTURES[tool]
        assert len(fxs) == 3, f"{tool}: expected 3 fixtures"
        any_over_window = False
        for name, fx in fxs.items():
            want = fx["output"].encode("ascii")
            assert len(want) <= STREAM_CAP, f"{tool}/{name}: exceeds ring"
            if len(want) > 16:
                any_over_window = True
        assert any_over_window, (
            f"{tool}: no fixture output exceeds the 16-byte window — "
            f"the table no longer exercises item 18's streaming premise")
        # non-vacuity: at least one fixture's reference differs from its
        # raw input (the oracle transforms, it does not echo). tee is
        # EXEMPT: its POSIX contract is identity-to-stdout (the
        # duplication half of tee); its correctness is pinned byte-exact
        # by the parametrized leg instead.
        data_seen = {fx.get("data", "") for fx in fxs.values()}
        outs_seen = {fx["output"] for fx in fxs.values()}
        if tool != "tee":
            assert outs_seen - data_seen, (
                f"{tool}: every reference equals its input — vacuous oracle")


# ── the gate: per-tool x per-fixture, byte-exact vs POSIX reference ──────

def _ring_stream(mem, n_bytes: int) -> bytes:
    frames = (n_bytes + 15) // 16
    return b"".join(
        int(mem[w]).to_bytes(4, "little")
        for w in range(GH23_WRITE_RING_BASE, GH23_WRITE_RING_BASE + frames * 4)
    )


@pytest.mark.parametrize("tool", COREUTILS2_TOOLS)
@pytest.mark.skipif(shutil.which(_GCC) is None,
                    reason="riscv64-unknown-elf-gcc not installed")
def test_volume2_tool_streams_byte_exact(tool: str):
    for fixture_name in sorted(COREUTILS2_FIXTURES[tool]):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            fx = COREUTILS2_FIXTURES[tool][fixture_name]
            want = fx["output"].encode("ascii")
            frames = (len(want) + 15) // 16

            elf_bytes = coreutils2_tool_elf(tool, fixture_name, tmp)
            program = _load_posix_program(elf_bytes)
            out = tmp / "vol2.npy"
            libc_runtime_kernel_image(build_default_atlas(), out_path=out,
                                      user_program=program)
            runner = GlyphRunner(out, ram_words=16384)
            receipt = runner.run(max_instructions=300000, trace=True)
            assert receipt["halted"] is True, receipt.get("error", receipt)
            assert receipt["faulted"] is False, receipt
            mem = receipt["memory"]

            assert mem[GH23_EXIT_CODE] == int(fx.get("exit", 0)), (
                f"{tool}/{fixture_name}: exit {mem[GH23_EXIT_CODE]}")

            if len(want) == 0:
                # zero-output edge (grep with no hits): NO write ECALLs —
                # cursor must sit exactly at the ring base.
                assert mem[GH23_WRITE_CURSOR] == GH23_WRITE_RING_BASE, hex(
                    mem[GH23_WRITE_CURSOR])
                continue

            stream = _ring_stream(mem, len(want))
            assert stream[:len(want)] == want, (
                f"{tool}/{fixture_name}: glyph stream "
                f"{stream[:len(want)]!r} != POSIX reference {want!r}")
            # the last frame's tail pad is zero (single flush contract)
            assert stream[len(want):] == b"\0" * (frames * 16 - len(want)), (
                f"{tool}/{fixture_name}: non-zero frame tail pad")
            # cursor advanced by exactly the frames the stream consumed
            assert mem[GH23_WRITE_CURSOR] == (
                GH23_WRITE_RING_BASE + frames * 4), hex(
                mem[GH23_WRITE_CURSOR])


@pytest.mark.skipif(shutil.which(_GCC) is None,
                    reason="riscv64-unknown-elf-gcc not installed")
def test_volume2_over_window_output_lands_beyond_the_legacy_window():
    """The item-19 point, pinned concretely: a 48-byte tee passthrough
    delivers bytes 17..48 — which the BK-11 fixed window physically
    could not hold — and the legacy 718..721 mirror keeps the LAST 16
    bytes (the documented BK-24 mirror contract)."""
    tool, fixture = "tee", "passthrough_48"
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        fx = COREUTILS2_FIXTURES[tool][fixture]
        want = fx["output"].encode("ascii")
        assert len(want) == 48
        elf_bytes = coreutils2_tool_elf(tool, fixture, tmp)
        program = _load_posix_program(elf_bytes)
        out = tmp / "vol2_tee.npy"
        libc_runtime_kernel_image(build_default_atlas(), out_path=out,
                                  user_program=program)
        runner = GlyphRunner(out, ram_words=16384)
        receipt = runner.run(max_instructions=300000, trace=True)
        assert receipt["halted"] is True and receipt["faulted"] is False
        mem = receipt["memory"]
        stream = _ring_stream(mem, len(want))
        assert stream == want, (stream[:16], want[:16])
        assert mem[GH23_WRITE_CURSOR] == GH23_WRITE_RING_BASE + 12
        window = b"".join(
            int(mem[w]).to_bytes(4, "little") for w in (718, 719, 720, 721))
        assert window == want[32:48]     # last 16 bytes, mirror contract


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
