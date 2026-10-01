#!/usr/bin/env python3
"""Run the simple_strtoul harness: parse all cpio header fields (and a full
1-4 hex digit sweep) with the kernel's exact digit-conversion code, then
compare every result against the host-computed expected value.

A mismatch pinpoints the exact input string the emulator mis-parses — the
fingerprint of the mis-executed instruction in the cpio parser's field parse.

Usage: python3 tools/run_strtoul_harness.py
"""
import gzip
import json
import re
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.spatial_rv64i_cpu import SpatialRV64ICore
from tools.elf_to_pixel_loader import ELFLoader

ELF = '/tmp/inflate_harness/strtoul_harness.elf'
LNX = '/home/jericho/projects/zion/apps/linux/alpine/alpine-riscv64.lnx.bin'
ENTRIES = '/tmp/ref_cpio_entries.json'
MARKER_ADDR = 0x00100000
INPUT_ADDR = 0x00400000
RESULTS_ADDR = 0x00800000
MARKER_MAGIC = 0x5C0FFEE
MAX_STEPS = 50_000_000
POLL_EVERY = 1_000_000


def load_ref() -> bytes:
    data = Path(LNX).read_bytes()
    for m in re.finditer(b'\x1f\x8b\x08', data):
        off = m.start()
        if off > 0x1000000:
            return gzip.decompress(data[off:off + 5400000])
    raise SystemExit('no initrd gzip found')


def expected():
    """The expected results in the same order the harness writes them."""
    ref = load_ref()
    entries = json.load(open(ENTRIES))
    exp = []
    for e in entries:
        hdr = ref[e['pos']:e['pos'] + 110]
        for i in range(6, 110, 8):
            exp.append(int(hdr[i:i + 8], 16))
    hexc = '0123456789abcdef'
    for a in hexc:
        exp.append(int(a, 16))
    for a in hexc:
        for b in hexc:
            exp.append(int(a + b, 16))
    for a in hexc:
        for b in hexc:
            for c in hexc:
                exp.append(int(a + b + c, 16))
    for a in hexc:
        for b in hexc:
            for c in hexc:
                for d in hexc:
                    exp.append(int(a + b + c + d, 16))
    return exp


def main() -> int:
    ref = load_ref()
    entries = json.load(open(ENTRIES))

    # build the input field strings (184 entries x 13 fields x 8 bytes)
    fields = bytearray()
    for e in entries:
        hdr = ref[e['pos']:e['pos'] + 110]
        for i in range(6, 110, 8):
            fields += hdr[i:i + 8]
    print(f'{len(entries)} entries, {len(fields)} bytes of field strings')

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
    core.write_mem_bytes(INPUT_ADDR - ram_base, bytes(fields))
    print('harness loaded, fields written')

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
    print(f'{total:,} steps in {dt:.1f}s')

    m0 = core.read_mem_word(MARKER_ADDR - ram_base)
    if m0 != MARKER_MAGIC:
        print(f'marker not set (0x{m0:x})')
        return 1
    count = core.read_mem_word(MARKER_ADDR - ram_base + 8)
    print(f'harness wrote {count:,} results')

    exp = expected()
    print(f'expected {len(exp):,} results')
    if count != len(exp):
        print(f'COUNT MISMATCH: harness {count} vs expected {len(exp)}')

    # read results from guest memory
    core.step(1)
    import numpy as np
    buf = core.queue.read_buffer(core.memory.buffer)
    spatial = np.frombuffer(buf, dtype=np.uint32)
    linear = spatial[core.hilbert_lut_np]
    off = RESULTS_ADDR - ram_base
    n_words = min(count, len(exp)) * 2  # u64 = 2 words
    raw = linear[off // 4:off // 4 + n_words]
    got = [(int(raw[i]) | (int(raw[i + 1]) << 32)) for i in range(0, n_words, 2)]

    ndiff = 0
    for i in range(min(len(got), len(exp))):
        if got[i] != exp[i]:
            ndiff += 1
            if ndiff <= 20:
                # map result index back to a description
                if i < len(entries) * 13:
                    ei = i // 13
                    fi = i % 13
                    desc = f'entry[{ei}] field[{fi}] ({entries[ei]["name"]})'
                else:
                    desc = f'sweep[{i - len(entries) * 13}]'
                print(f'  MISMATCH #{ndiff}: idx {i} {desc}: emu={got[i]} (0x{got[i]:x}) exp={exp[i]} (0x{exp[i]:x})')
    print(f'{ndiff} mismatches of {min(len(got), len(exp))} compared')
    if ndiff == 0:
        print('ALL FIELD PARSES CORRECT — simple_strtoul is not the culprit')
        return 0
    print('simple_strtoul MIS-PARSES — likely the root cause')
    return 1


if __name__ == '__main__':
    sys.exit(main())
