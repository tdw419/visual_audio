#!/usr/bin/env python3
"""Analyze a linear guest-memory dump from monitor_rv64i.py --dump-mem.

Goals:
1. Sanity-check the dump mapping (initrd gzip must sit at guest phys 0x82000000
   = dump offset 0x2000000).
2. Find each reference decompressed-output 32KB chunk in the dump (the kernel
   gunzip's malloc'd out_buf chunks are freed-but-not-zeroed after the
   "broken padding" failure, so they should still be findable).
3. Byte-compare found chunks against the reference; report the first
   divergence — the exact corrupted output byte localizes the emulator bug.

Usage:
    python3 tools/analyze_mem_dump.py DUMP.bin [REF_OUT.bin]
"""
import hashlib
import sys
from pathlib import Path

RAM_BASE = 0x80000000
INITRD_PHYS = 0x82800000


def load_ref(path: str) -> bytes:
    import gzip
    import re
    data = Path(path).read_bytes()
    for m in re.finditer(b'\x1f\x8b\x08', data):
        off = m.start()
        if off > 0x1000000:
            return gzip.decompress(data[off:off + 5400000])
    raise SystemExit('no initrd gzip found in LNX image')


def main() -> int:
    dump_path = sys.argv[1]
    lnx_path = sys.argv[2] if len(sys.argv) > 2 else \
        '/home/jericho/projects/zion/apps/linux/alpine/alpine-riscv64.lnx.bin'

    dump = Path(dump_path).read_bytes()
    print(f'dump: {len(dump):,} bytes ({len(dump)//(1024*1024)}MB)')

    ref = load_ref(lnx_path)
    print(f'ref decompressed: {len(ref):,} bytes')

    # 1. sanity: initrd gzip at 0x2000000 in dump
    initrd_off = INITRD_PHYS - RAM_BASE
    gz = dump[initrd_off:initrd_off + 16]
    print(f'initrd gzip @ dump+0x{initrd_off:x}: {gz[:4].hex()} (expect 1f8b08xx)')

    # 2. search for each reference 32KB chunk head (64 bytes)
    chunk_size = 32768
    heads = [ref[i:i + 64] for i in range(0, len(ref), chunk_size)]
    print(f'reference chunks: {len(heads)}')

    found = []
    for ci, head in enumerate(heads):
        pos = dump.find(head)
        if pos >= 0:
            found.append((ci, pos))
            print(f'chunk {ci}: found at dump+0x{pos:x} (guest phys 0x{RAM_BASE + pos:08x})')
        elif ci < 6 or ci >= len(heads) - 6:
            print(f'chunk {ci}: NOT FOUND')

    if not found:
        print('NO reference chunks found — decompressed output not retained (or corruption early).')
        print('Trying a wider net: search for cpio magic 070701 occurrences:')
        import re
        hits = [m.start() for m in re.finditer(re.escape(b'070701'), dump)]
        print(f'  {len(hits)} "070701" occurrences in dump (first 20):')
        for h in hits[:20]:
            print(f'    dump+0x{h:x}')
        return 1

    # 3. compare found chunks byte-by-byte
    first_div = None
    for ci, pos in sorted(found):
        chunk_ref = ref[ci * chunk_size:(ci + 1) * chunk_size]
        chunk_dump = dump[pos:pos + chunk_size]
        if len(chunk_dump) < chunk_size:
            print(f'chunk {ci}: truncated in dump ({len(chunk_dump)} bytes)')
            continue
        if chunk_dump == chunk_ref:
            print(f'chunk {ci}: byte-identical')
            continue
        # find first divergence
        for b in range(chunk_size):
            if chunk_dump[b] != chunk_ref[b]:
                print(f'chunk {ci}: DIVERGES at byte {b} (stream offset {ci * chunk_size + b:,}) '
                      f'-> dump=0x{chunk_dump[b]:02x} ref=0x{chunk_ref[b]:02x}')
                first_div = ci * chunk_size + b
                break
    if first_div is not None:
        print(f'\nFIRST DIVERGENCE at decompressed stream offset {first_div:,} '
              f'({first_div / len(ref) * 100:.2f}% into output)')
    else:
        print('\nAll found chunks identical — corruption (if any) is outside retained chunks.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
