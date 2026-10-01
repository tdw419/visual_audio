#!/usr/bin/env python3
"""
ROADMAP item 4: real RISC-V guest, real GPU core, end-to-end glyph dispatch.

Assembles guest_sha256_dispatch.s, loads it into a real SpatialRV64ICore, and
drives it with run_with_offload_glyph(). The guest lays out the request struct,
writes 0x8800_0000, spins on BUSY, then halts via SYSCON. The host loop's
servicing turn runs the Glyph ISA SHA-256 kernel and writes the digest back to
guest RAM. We then read the output buffer and compare to hashlib.

This is NOT in verify.py's fast gate: it needs a GPU + wgpu and a shader
compile. It SKIPS (exit 0, printed reason) when wgpu / a device / the assembler
is unavailable, and FAILS LOUDLY otherwise.

Run directly:  python3 glyph_dispatch/tests/integration/test_item4_real_core.py
"""

import hashlib
import sys
from pathlib import Path

_GD_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[3]
for p in (str(_GD_ROOT), str(_REPO_ROOT / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

RAM_BASE = 0x80000000
RAM_SIZE = 64 * 1024 * 1024         # /4 == 4096**2 (Hilbert perfect-square); fits GPU binding limits
ENTRY = 0x80000000
REQ_BASE = 0x81001000
OUT_PTR = 0x81004000
MESSAGE = b"abc"
SLICE_STEPS = 2000
MAX_STEPS = 400_000


def _skip(msg: str):
    print(f"SKIP: {msg}")
    sys.exit(0)


def main():
    try:
        from rv64i_asm import assemble
    except Exception as e:                       # pragma: no cover
        _skip(f"rv64i_asm unavailable: {e}")

    try:
        from spatial_rv64i_cpu import SpatialRV64ICore
    except Exception as e:                       # pragma: no cover
        _skip(f"spatial_rv64i_cpu import failed: {e}")

    from src.offload.run_with_glyph_dispatch import run_with_offload_glyph

    asm_path = Path(__file__).with_name("guest_sha256_dispatch.s")
    binary = assemble(asm_path.read_text())
    print(f"  assembled payload: {len(binary)} bytes")

    try:
        core = SpatialRV64ICore(RAM_SIZE)
    except Exception as e:                       # pragma: no cover
        _skip(f"no GPU device for SpatialRV64ICore: {e}")

    core.load_program(binary, entry_point=ENTRY, ram_base=RAM_BASE)

    result = run_with_offload_glyph(
        core, disk_path=None, ram_base=RAM_BASE,
        slice_steps=SLICE_STEPS, max_steps=MAX_STEPS,
    )
    print(f"  loop result: {result.get('glyph')}  total_steps={result.get('total_steps')}")

    from qemu_gpu_offload import GpuRam
    ram = GpuRam(core, RAM_BASE)
    digest = ram.read_bytes(OUT_PTR, 32)
    want = hashlib.sha256(MESSAGE).digest()

    assert result["glyph"]["glyph_offloads"] == 1, (
        f"expected 1 glyph offload, got {result['glyph']}")
    assert result["glyph"]["glyph_errors"] == 0, result["glyph"]
    assert digest == want, (
        f"digest mismatch\n  core    {digest.hex()}\n  hashlib {want.hex()}")

    print(f"  digest {digest.hex()}  == hashlib  OK")
    print("-" * 70)
    print("ITEM 4: REAL-CORE END-TO-END PASSED")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"\nITEM 4 FAILED: {e}")
        sys.exit(1)
    sys.exit(0)
