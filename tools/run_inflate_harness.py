#!/usr/bin/env python3
"""Run the bare-metal inflate harness on the GPU RV64I emulator.

Decompresses the Alpine initrd gzip with the kernel's zlib_inflate compiled
for bare-metal RV64, then compares the emulator-produced output against the
host reference byte-for-byte. This discriminates:
  H1: the inflate corrupts output (first-divergence byte found) vs
  H2: the inflate is correct and the boot failure is in the cpio parser.

Usage: python3 tools/run_inflate_harness.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.spatial_rv64i_cpu import SpatialRV64ICore
from tools.elf_to_pixel_loader import ELFLoader

ELF = '/tmp/inflate_harness/inflate_harness.elf'
LNX = '/home/jericho/projects/zion/apps/linux/alpine/alpine-riscv64.lnx.bin'
INPUT_ADDR = 0x00800000
MARKER_ADDR = 0x00100000
OUTPUT_ADDR = 0x01000000
MARKER_MAGIC = 0xC0FFEE
MAX_STEPS = 400_000_000
POLL_EVERY = 5_000_000


def load_gzip() -> bytes:
    import re
    data = Path(LNX).read_bytes()
    for m in re.finditer(b'\x1f\x8b\x08', data):
        off = m.start()
        if off > 0x1000000:
            return data[off:off + 5289441]
    raise SystemExit('no initrd gzip found')


def load_reference() -> bytes:
    import gzip
    import re
    data = Path(LNX).read_bytes()
    for m in re.finditer(b'\x1f\x8b\x08', data):
        off = m.start()
        if off > 0x1000000:
            return gzip.decompress(data[off:off + 5400000])
    raise SystemExit('no initrd found')


def main() -> int:
    elf = ELFLoader(ELF)
    ram_base = min((s['vaddr'] for s in elf.segments if s['type'] == ELFLoader.PT_LOAD), default=0)
    print(f'ELF entry 0x{elf.entry_point:x}, ram_base 0x{ram_base:x}')

    core = SpatialRV64ICore(memory_size_bytes=64 * 1024 * 1024)
    core.load_program(b'', entry_point=elf.entry_point, ram_base=ram_base)
    for seg in elf.segments:
        if seg['type'] != ELFLoader.PT_LOAD or seg['filesz'] == 0:
            continue
        data = elf.data[seg['offset']:seg['offset'] + seg['filesz']]
        core.write_mem_bytes(seg['vaddr'] - ram_base, data)
    print('harness loaded')

    gz = load_gzip()
    print(f'writing {len(gz):,} bytes gzip input at guest phys 0x{INPUT_ADDR:x}')
    core.write_mem_bytes(INPUT_ADDR - ram_base, gz)

    t0 = time.time()
    total = 0
    while total < MAX_STEPS:
        core.step(POLL_EVERY)
        total += POLL_EVERY
        # get_state() issues a blocking GPU buffer read — the only reliable
        # sync point (core.step() alone only measures async submit rate).
        core.get_state()
        m0 = core.read_mem_word(MARKER_ADDR - ram_base)
        if m0 == MARKER_MAGIC:
            break
        if m0 != 0 and m0 & 0xBAD00000 == 0xBAD00000:
            m1 = core.read_mem_word(MARKER_ADDR - ram_base + 4)
            m2 = core.read_mem_word(MARKER_ADDR - ram_base + 8)
            print(f'HARNESS FAILED code 0x{m0:x} a={m1} b={m2} at {total:,} steps')
            return 1
    dt = time.time() - t0
    print(f'{total:,} steps in {dt:.1f}s ({total / dt:,.0f} steps/s)')

    m0 = core.read_mem_word(MARKER_ADDR - ram_base)
    if m0 != MARKER_MAGIC:
        print(f'marker not set (0x{m0:x}) — harness did not finish')
        return 1
    total_out = core.read_mem_word(MARKER_ADDR - ram_base + 8)
    ret = core.read_mem_word(MARKER_ADDR - ram_base + 16)
    print(f'total_out={total_out:,} inflate_ret={ret}')

    ref = load_reference()
    print(f'reference output: {len(ref):,} bytes')
    if total_out != len(ref):
        print(f'SIZE MISMATCH: emulator {total_out:,} vs reference {len(ref):,}')
        return 1

    # dump the harness output region (guest phys OUTPUT_ADDR..+total_out)
    # linear dump: word 0 = ram_base, so guest phys G -> offset G - ram_base
    core.step(1)  # ensure queue drained
    import numpy as np
    buf = core.queue.read_buffer(core.memory.buffer)
    spatial = np.frombuffer(buf, dtype=np.uint32)
    linear = spatial[core.hilbert_lut_np]
    off = OUTPUT_ADDR - ram_base
    out = linear[off // 4:(off + total_out) // 4].tobytes()
    print(f'dumped {len(out):,} bytes of harness output')

    # byte compare
    ndiff = 0
    first = None
    for i in range(min(len(out), len(ref))):
        if out[i] != ref[i]:
            ndiff += 1
            if first is None:
                first = i
    print(f'comparison: {ndiff:,} differing bytes of {min(len(out), len(ref)):,}')
    if first is not None:
        print(f'FIRST DIVERGENCE at output byte {first:,} ({first / len(ref) * 100:.2f}%): '
              f'emu=0x{out[first]:02x} ref=0x{ref[first]:02x}')
        print('context:')
        print(f'  emu: {out[max(0, first - 16):first + 16].hex()}')
        print(f'  ref: {ref[max(0, first - 16):first + 16].hex()}')
        return 1
    print('OUTPUT BYTE-IDENTICAL — inflate is correct; bug is in the cpio parser')
    return 0


if __name__ == '__main__':
    sys.exit(main())
