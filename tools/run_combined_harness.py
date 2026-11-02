#!/usr/bin/env python3
"""Run the combined inflate+FSM harness: the EXACT kernel pipeline (gzip ->
zlib inflate with real per-call chunk boundaries -> cpio FSM, VFS stubbed) on
the emulator. If this reproduces "broken padding", the trigger is the
inflate-chunk-boundary interaction with the parser FSM.

Expected (host): 184 entry boundaries [112, 232, ...], final state Reset,
this_header 11,600,900, NO message.

Usage: python3 tools/run_combined_harness.py
"""
import gzip
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.spatial_rv64i_cpu import SpatialRV64ICore
from tools.elf_to_pixel_loader import ELFLoader

ELF = '/tmp/inflate_harness/fsm_combined.elf'
LNX = '/home/jericho/projects/zion/apps/linux/alpine/alpine-riscv64.lnx.bin'
MARKER_ADDR = 0x00100000
GZIP_ADDR = 0x00600000
RESULTS_ADDR = 0x00800000
MARKER_MAGIC = 0xC0FFEE5
MAX_STEPS = 400_000_000
POLL_EVERY = 5_000_000


def load_gzip() -> bytes:
    data = Path(LNX).read_bytes()
    for m in re.finditer(b'\x1f\x8b\x08', data):
        off = m.start()
        if off > 0x1000000:
            return data[off:off + 5289441]
    raise SystemExit('no initrd gzip found')


def main() -> int:
    gz = load_gzip()
    print(f'gzip input: {len(gz):,} bytes')

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
    core.write_mem_bytes(GZIP_ADDR - ram_base, gz)
    print('harness loaded, gzip written')

    t0 = time.time()
    total = 0
    while total < MAX_STEPS:
        core.step(POLL_EVERY)
        total += POLL_EVERY
        core.get_state()
        m0 = core.read_mem_word(MARKER_ADDR - ram_base)
        if m0 == MARKER_MAGIC:
            break
        if m0 != 0 and m0 & 0xBAD00000 == 0xBAD00000:
            print(f'HARNESS FAILED code 0x{m0:x} at {total:,} steps')
            return 1
    dt = time.time() - t0
    print(f'{total:,} steps in {dt:.1f}s ({total / dt:,.0f} steps/s)')

    m0 = core.read_mem_word(MARKER_ADDR - ram_base)
    if m0 != MARKER_MAGIC:
        print(f'marker not set (0x{m0:x})')
        return 1
    n = core.read_mem_word(MARKER_ADDR - ram_base + 8)
    state = core.read_mem_word(MARKER_ADDR - ram_base + 16)
    bc = core.read_mem_word(MARKER_ADDR - ram_base + 24)
    th = core.read_mem_word(MARKER_ADDR - ram_base + 32)
    msg = core.read_mem_word(MARKER_ADDR - ram_base + 40)
    tfb = core.read_mem_word(MARKER_ADDR - ram_base + 48)
    ret = core.read_mem_word(MARKER_ADDR - ram_base + 56)
    print(f'n_results={n} state={state} byte_count={bc} this_header={th} '
          f'message_ptr={msg:#x} total_file_bytes={tfb} inflate_ret={ret}')

    core.step(1)
    import numpy as np
    buf = core.queue.read_buffer(core.memory.buffer)
    spatial = np.frombuffer(buf, dtype=np.uint32)
    linear = spatial[core.hilbert_lut_np]
    off = RESULTS_ADDR - ram_base
    n_words = n * 2
    raw = linear[off // 4:off // 4 + n_words]
    got = [(int(raw[i]) | (int(raw[i + 1]) << 32)) for i in range(0, n_words, 2)]

    # expected = the clean-parse boundary sequence (same as the FSM harness)
    # recompute from the reference listing (entry next positions)
    import json
    entries = json.load(open('/tmp/ref_cpio_entries.json'))
    exp = [e['next'] for e in entries]
    print(f'expected: {len(exp)} boundaries, final this_header={exp[-1]}')

    ndiff = 0
    for i in range(min(len(got), len(exp))):
        if got[i] != exp[i]:
            ndiff += 1
            if ndiff <= 10:
                print(f'  DIVERGE at boundary {i}: emu={got[i]} exp={exp[i]} (delta {got[i] - exp[i]})')
    print(f'{ndiff} divergent boundaries of {min(len(got), len(exp))} compared')

    if msg != 0:
        print('*** HARNESS REPRODUCED THE PARSER FAILURE (message set) ***')
        return 1
    if ndiff == 0:
        print('COMBINED PIPELINE CLEAN — inflate chunk boundaries do NOT trigger the bug')
        return 0
    print('boundaries diverge without message — unexpected')
    return 1


if __name__ == '__main__':
    sys.exit(main())
