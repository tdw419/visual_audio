#!/usr/bin/env python3
"""
ROADMAP item 3 oracle: the host-side MMIO dispatch bridge for the Route B loop.

Route B (tools/qemu_gpu_offload.py :: run_with_offload) runs RISC-V on the GPU
and, when the guest triggers a yield (state `halted == 2`), the host loop gets a
servicing turn: it walks the VirtIO queue, then resumes the core. This item adds
a second thing the host does on that turn -- check the glyph dispatch request
struct and, if BUSY is set, run the kernel and write the result back.

`GlyphDispatchHost.on_yield()` is exactly that per-turn hook. This oracle models
the Route B contract with a MockGpuRam standing in for GpuRam and a bounded
poll loop standing in for the guest spin-wait:

    guest: lay out request struct + input bytes, set BUSY   (as the asm would)
    guest: write 0x8800_0000  -> core yields (halted == 2)
    host : on_yield()         -> GlyphDispatcher.check_dispatch()
    guest: poll BUSY; when clear, read the digest

Verified: digest == hashlib.sha256(input); bridge is a no-op on a yield with no
pending glyph request (so it never disturbs a VirtIO-only yield); error
accounting is correct. The real RISC-V-guest-on-real-core end-to-end is item 4.

FAILS LOUDLY: AssertionError -> non-zero exit. (Fails at import until item 3 is
implemented -- oracles-first.)
"""

import hashlib
import sys
from pathlib import Path

_GD_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_GD_ROOT))

from tests.mock_ram import MockGpuRam
from src.dispatch.request_struct import (
    REQUEST_STRUCT_BASE,
    OFFSET_GLYPH_ID, OFFSET_INPUT_BUF_PTR, OFFSET_INPUT_BUF_LEN,
    OFFSET_OUTPUT_BUF_PTR, OFFSET_OUTPUT_BUF_LEN, OFFSET_RESULT_STATUS,
    FLAG_BUSY, FLAG_ERROR, RESULT_SUCCESS,
    GLYPH_ID_SHA256,
)
# The bridge under test -- does not exist yet (oracles-first).
from src.offload.glyph_dispatch_host import GlyphDispatchHost

INPUT_PTR = 0x8100_2000
OUTPUT_PTR = 0x8100_4000
MAX_POLLS = 4


def _guest_submit(ram, glyph_id, msg, out_len=32):
    """Write the request struct + input buffer exactly as the guest asm would
    (see request_struct.generate_guest_request_code): glyph_id at +0x04,
    64-bit ptr/len fields at +0x08.. , BUSY bit last."""
    ram.write_bytes(INPUT_PTR, msg)
    ram.write_u32(REQUEST_STRUCT_BASE + OFFSET_GLYPH_ID, glyph_id)
    ram.write_u64(REQUEST_STRUCT_BASE + OFFSET_INPUT_BUF_PTR, INPUT_PTR)
    ram.write_u64(REQUEST_STRUCT_BASE + OFFSET_INPUT_BUF_LEN, len(msg))
    ram.write_u64(REQUEST_STRUCT_BASE + OFFSET_OUTPUT_BUF_PTR, OUTPUT_PTR)
    ram.write_u64(REQUEST_STRUCT_BASE + OFFSET_OUTPUT_BUF_LEN, out_len)
    ram.write_u32(REQUEST_STRUCT_BASE, FLAG_BUSY)


def _guest_poll_until_done(ram, host):
    """Bounded spin-wait: each poll, the host loop gets one servicing turn."""
    for _ in range(MAX_POLLS):
        if (ram.read_u32(REQUEST_STRUCT_BASE) & FLAG_BUSY) == 0:
            return True
        host.on_yield()
    return (ram.read_u32(REQUEST_STRUCT_BASE) & FLAG_BUSY) == 0


def test_bridge_round_trip():
    for msg in (b"", b"abc", b"x" * 56, b"z" * 200):
        ram = MockGpuRam()
        host = GlyphDispatchHost(ram)
        _guest_submit(ram, GLYPH_ID_SHA256, msg)

        assert _guest_poll_until_done(ram, host), f"BUSY never cleared len={len(msg)}"

        flags = ram.read_u32(REQUEST_STRUCT_BASE)
        status = ram.read_u32(REQUEST_STRUCT_BASE + OFFSET_RESULT_STATUS)
        assert (flags & FLAG_ERROR) == 0, f"ERROR set len={len(msg)}"
        assert status == RESULT_SUCCESS, f"status={status} len={len(msg)}"

        got = ram.read_bytes(OUTPUT_PTR, 32)
        assert got == hashlib.sha256(msg).digest(), (
            f"digest mismatch len={len(msg)}\n  bridge  {got.hex()}\n"
            f"  hashlib {hashlib.sha256(msg).hexdigest()}")
        assert host.offload_count == 1 and host.error_count == 0, (
            f"stats off: offload={host.offload_count} error={host.error_count}")
        print(f"  len={len(msg):<4} {got.hex()}  OK")


def test_yield_without_glyph_request_is_noop():
    """A VirtIO-only yield: no BUSY set. on_yield must return False and touch
    nothing (no result_status write, no counter bump)."""
    ram = MockGpuRam()
    host = GlyphDispatchHost(ram)
    before = ram.read_bytes(REQUEST_STRUCT_BASE, 64)

    assert host.on_yield() is False
    assert host.offload_count == 0 and host.error_count == 0
    assert ram.read_bytes(REQUEST_STRUCT_BASE, 64) == before, "bridge mutated RAM on a no-op yield"
    print("  no pending request -> on_yield() no-op  OK")


def test_error_accounting():
    ram = MockGpuRam()
    host = GlyphDispatchHost(ram)
    _guest_submit(ram, 0xDEADBEEF, b"abc")   # unknown glyph id

    assert host.on_yield() is True
    flags = ram.read_u32(REQUEST_STRUCT_BASE)
    assert (flags & FLAG_ERROR) != 0, "ERROR flag not set"
    assert (flags & FLAG_BUSY) == 0, "BUSY not cleared on error"
    assert host.error_count == 1 and host.offload_count == 0, (
        f"stats off: offload={host.offload_count} error={host.error_count}")
    print("  unknown glyph id -> error_count incremented  OK")


def main():
    print("=" * 70)
    print("ITEM 3 - host MMIO dispatch bridge (Route B on_yield hook)")
    print("=" * 70)
    test_bridge_round_trip()
    test_yield_without_glyph_request_is_noop()
    test_error_accounting()
    print("-" * 70)
    print("ITEM 3: ALL CHECKS PASSED")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"\nITEM 3 FAILED: {e}")
        sys.exit(1)
    sys.exit(0)
