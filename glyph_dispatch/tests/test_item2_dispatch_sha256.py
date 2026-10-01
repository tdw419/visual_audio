#!/usr/bin/env python3
"""
ROADMAP item 2 oracle: end-to-end SHA-256 through the dispatch ABI.

Exercises the full host-side round trip:
  guest lays out the request struct + input bytes in shared RAM and sets BUSY
    -> GlyphDispatcher.check_dispatch() detects it
    -> runs the real Glyph ISA SHA-256 kernel on GlyphCPUv2
    -> writes the 32-byte digest to the guest output buffer
    -> clears BUSY, sets result_status = 0
  guest reads the digest back.

Verified against hashlib.sha256 for several lengths (incl. multi-block), plus
the ABI error paths (unknown glyph id, undersized output buffer, no BUSY).

FAILS LOUDLY: any mismatch raises AssertionError; script exits non-zero.
"""

import hashlib
import sys
from pathlib import Path

_GD_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_GD_ROOT))

from tests.mock_ram import MockGpuRam
from src.dispatch.dispatcher import GlyphDispatcher
from src.dispatch.request_struct import (
    REQUEST_STRUCT_BASE,
    OFFSET_GLYPH_ID, OFFSET_INPUT_BUF_PTR, OFFSET_INPUT_BUF_LEN,
    OFFSET_OUTPUT_BUF_PTR, OFFSET_OUTPUT_BUF_LEN, OFFSET_RESULT_STATUS,
    FLAG_BUSY, FLAG_ERROR,
    RESULT_SUCCESS, RESULT_ERROR, RESULT_OUTPUT_TOO_SMALL,
    GLYPH_ID_SHA256,
)

INPUT_PTR = 0x8100_2000
OUTPUT_PTR = 0x8100_4000


def _s32(u: int) -> int:
    return u - 0x1_0000_0000 if u >= 0x8000_0000 else u


def _submit(ram, glyph_id, msg, out_len):
    ram.write_bytes(INPUT_PTR, msg)
    ram.write_u32(REQUEST_STRUCT_BASE + OFFSET_GLYPH_ID, glyph_id)
    ram.write_u64(REQUEST_STRUCT_BASE + OFFSET_INPUT_BUF_PTR, INPUT_PTR)
    ram.write_u64(REQUEST_STRUCT_BASE + OFFSET_INPUT_BUF_LEN, len(msg))
    ram.write_u64(REQUEST_STRUCT_BASE + OFFSET_OUTPUT_BUF_PTR, OUTPUT_PTR)
    ram.write_u64(REQUEST_STRUCT_BASE + OFFSET_OUTPUT_BUF_LEN, out_len)
    ram.write_u32(REQUEST_STRUCT_BASE, FLAG_BUSY)


def test_sha256_round_trip():
    ram = MockGpuRam()
    disp = GlyphDispatcher(ram)

    messages = [
        b"",
        b"abc",
        b"The quick brown fox jumps over the lazy dog",
        b"x" * 56,          # 2 blocks after padding
        b"z" * 200,         # 4 blocks
    ]
    for msg in messages:
        _submit(ram, GLYPH_ID_SHA256, msg, out_len=32)

        assert disp.check_dispatch() is True, f"dispatch not processed len={len(msg)}"

        flags = ram.read_u32(REQUEST_STRUCT_BASE)
        status = _s32(ram.read_u32(REQUEST_STRUCT_BASE + OFFSET_RESULT_STATUS))
        assert (flags & FLAG_BUSY) == 0, "BUSY not cleared"
        assert (flags & FLAG_ERROR) == 0, f"ERROR set len={len(msg)}"
        assert status == RESULT_SUCCESS, f"status={status} len={len(msg)}"

        got = ram.read_bytes(OUTPUT_PTR, 32)
        want = hashlib.sha256(msg).digest()
        assert got == want, (
            f"digest mismatch len={len(msg)}\n  glyph   {got.hex()}\n  hashlib {want.hex()}"
        )
        print(f"  len={len(msg):<4} digest={got.hex()}  OK")


def test_unknown_glyph_id():
    ram = MockGpuRam()
    disp = GlyphDispatcher(ram)
    _submit(ram, 0xDEADBEEF, b"abc", out_len=32)

    assert disp.check_dispatch() is True
    flags = ram.read_u32(REQUEST_STRUCT_BASE)
    status = _s32(ram.read_u32(REQUEST_STRUCT_BASE + OFFSET_RESULT_STATUS))
    assert (flags & FLAG_ERROR) != 0, "ERROR flag not set for unknown glyph id"
    assert (flags & FLAG_BUSY) == 0, "BUSY not cleared on error"
    assert status == RESULT_ERROR, f"status={status}, expected RESULT_ERROR"
    print("  unknown glyph id -> ERROR/RESULT_ERROR  OK")


def test_output_buffer_too_small():
    ram = MockGpuRam()
    disp = GlyphDispatcher(ram)
    _submit(ram, GLYPH_ID_SHA256, b"abc", out_len=16)   # digest needs 32

    assert disp.check_dispatch() is True
    flags = ram.read_u32(REQUEST_STRUCT_BASE)
    status = _s32(ram.read_u32(REQUEST_STRUCT_BASE + OFFSET_RESULT_STATUS))
    assert (flags & FLAG_ERROR) != 0, "ERROR flag not set for small output buf"
    assert status == RESULT_OUTPUT_TOO_SMALL, (
        f"status={status}, expected RESULT_OUTPUT_TOO_SMALL")
    print("  undersized output buffer -> RESULT_OUTPUT_TOO_SMALL  OK")


def test_no_busy_flag_is_noop():
    ram = MockGpuRam()
    disp = GlyphDispatcher(ram)
    ram.write_u32(REQUEST_STRUCT_BASE + OFFSET_GLYPH_ID, GLYPH_ID_SHA256)
    # BUSY deliberately not set
    assert disp.check_dispatch() is False, "dispatch ran without BUSY set"
    print("  no BUSY flag -> no-op  OK")


def main():
    print("=" * 70)
    print("ITEM 2 - SHA-256 end-to-end through the dispatch ABI")
    print("=" * 70)
    test_sha256_round_trip()
    test_unknown_glyph_id()
    test_output_buffer_too_small()
    test_no_busy_flag_is_noop()
    print("-" * 70)
    print("ITEM 2: ALL CHECKS PASSED")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"\nITEM 2 FAILED: {e}")
        sys.exit(1)
    sys.exit(0)
