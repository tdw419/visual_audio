#!/usr/bin/env python3
"""
ROADMAP item 5: characterise the cost of the glyph SHA-256 dispatch path.

What this measures (all real, on this machine):
  * hashlib.sha256          -- native C baseline
  * sha256_glyph on GlyphCPUv2 -- the Glyph ISA kernel run by the *Python*
    reference interpreter (NOT the GPU)
  * static + dynamic Glyph ISA instruction counts per 512-bit block
  * (optional) the full real-core round trip from item 4, if a GPU is present

What this deliberately does NOT produce: a "speedup vs the RISC-V interpreter"
number. That needs (a) the Glyph kernel running on GPU via wgsl_glyph_isa_v2
across many parallel hashes, and (b) a measured RISC-V-SHA-256 instruction
count on SPATIAL_RV64I. Neither exists yet. See bench/RESULTS.md for the
analysis and the reasoned RISC-V estimate.
"""

import hashlib
import sys
import time
from pathlib import Path

_GD_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_GD_ROOT), str(_REPO_ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from src.glyph.glyph_isa_v2 import OpcodeMapV2, GlyphAssemblerV2, GlyphCPUv2
from src.glyph.sha256_kernel import (
    build_sha256_glyph_program, sha256_glyph, _K, _pad,
    K_BASE, BCNT_ADDR, BLK_BASE,
)

WIDTH = 64


def _time(fn, iters):
    fn()  # warm
    t = time.perf_counter()
    for _ in range(iters):
        fn()
    return (time.perf_counter() - t) / iters


def dynamic_instr_count(msg: bytes) -> tuple[int, int]:
    op = OpcodeMapV2()
    asm = GlyphAssemblerV2(op)
    img = asm.assemble(build_sha256_glyph_program(WIDTH), width_instrs=WIDTH)
    cpu = GlyphCPUv2(op, WIDTH)
    for i, k in enumerate(_K):
        cpu.memory[K_BASE + i] = k
    p = _pad(msg)
    nb = len(p) // 64
    cpu.memory[BCNT_ADDR] = nb
    for w in range(nb * 16):
        cpu.memory[BLK_BASE + w] = int.from_bytes(p[4 * w:4 * w + 4], "big")
    n = cpu.run(img, max_instructions=1_000_000)
    op.close()
    return nb, n


def main():
    print("=" * 72)
    print("glyph SHA-256 dispatch path -- cost characterisation")
    print("=" * 72)

    static = len(build_sha256_glyph_program(WIDTH))
    nb1, dyn1 = dynamic_instr_count(b"")
    nb4, dyn4 = dynamic_instr_count(b"z" * 200)
    per_block = dyn4 // nb4
    print(f"\nGlyph ISA instruction count")
    print(f"  static program            {static:>10}")
    print(f"  dynamic, 1 block          {dyn1:>10}")
    print(f"  dynamic, {nb4} blocks         {dyn4:>10}  ({per_block}/block)")

    hl = _time(lambda: hashlib.sha256(b"abc").digest(), 20000)
    gp = _time(lambda: sha256_glyph(b"abc"), 15)
    print(f"\nwall time, 1-block message (b'abc')")
    print(f"  hashlib.sha256            {hl * 1e6:>10.3f} us")
    print(f"  sha256_glyph / GlyphCPUv2 {gp * 1e3:>10.2f} ms   "
          f"({gp / per_block * 1e9:.0f} ns / glyph instr, Python interpreter)")
    print(f"  ratio                     {gp / hl:>10.0f}x   (Python-interpreter tax, not GPU)")

    # optional: real-core round trip (item 4 path) with timing
    try:
        from rv64i_asm import assemble
        from spatial_rv64i_cpu import SpatialRV64ICore
        from src.offload.run_with_glyph_dispatch import run_with_offload_glyph
        from qemu_gpu_offload import GpuRam
    except Exception as e:
        print(f"\nreal-core round trip: SKIP ({e})")
        print("\n" + "=" * 72)
        return

    RAM_BASE, RAM_SIZE = 0x80000000, 64 * 1024 * 1024
    asm_path = _GD_ROOT / "tests" / "integration" / "guest_sha256_dispatch.s"
    try:
        core = SpatialRV64ICore(RAM_SIZE)
    except Exception as e:
        print(f"\nreal-core round trip: SKIP (no GPU device: {e})")
        print("\n" + "=" * 72)
        return
    core.load_program(assemble(asm_path.read_text()),
                      entry_point=RAM_BASE, ram_base=RAM_BASE)
    t = time.perf_counter()
    res = run_with_offload_glyph(core, disk_path=None, ram_base=RAM_BASE,
                                 slice_steps=2000, max_steps=400_000)
    dt = time.perf_counter() - t
    ram = GpuRam(core, RAM_BASE)
    ok = ram.read_bytes(0x81004000, 32) == hashlib.sha256(b"abc").digest()
    print(f"\nreal-core round trip (item 4 path, GPU + host)")
    print(f"  wall time                 {dt * 1e3:>10.1f} ms   "
          f"(shader compile + {res['total_steps']} core steps + kernel + readback)")
    print(f"  glyph offloads / errors   {res['glyph']['glyph_offloads']} / {res['glyph']['glyph_errors']}")
    print(f"  digest matches hashlib    {ok}")

    print("\n" + "=" * 72)


if __name__ == "__main__":
    main()
