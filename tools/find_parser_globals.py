#!/usr/bin/env python3
"""Find the initramfs cpio-parser globals in a linear memory dump.

The parser globals are __initdata, declared adjacently in init/initramfs.c:
    victim (char*), byte_count (ulong), this_header (loff_t), next_header (loff_t)
    + state/next_state enums, name_len, body_len, message...
They live in the kernel's .init.data section. The kernel image is loaded at
0x80200000 (dump offset 0x200000), size ~20.9MB, so .init.data is around
physical 0x81400000-0x81600000 (dump offset 0x1400000-0x1600000). At the
"broken padding" error, this_header should be near the stream end (~11,600,000)
and byte_count small.

Usage: python3 tools/find_parser_globals.py DUMP.bin
"""
import struct
import sys
from pathlib import Path

STREAM_END = 11_600_900


def main() -> int:
    dump = Path(sys.argv[1]).read_bytes()
    print(f'dump: {len(dump):,} bytes')

    # scan the whole dump; the parser globals have:
    #   this_header/next_header as 8B LE in [0, STREAM_END+4096]
    #   byte_count as 8B LE in [0, 65536]
    #   victim as 8B ptr into guest RAM [0x80000000, 0x84000000]
    hits = []
    for i in range(0, len(dump) - 32, 4):
        victim = struct.unpack_from('<Q', dump, i)[0]
        bc = struct.unpack_from('<Q', dump, i + 8)[0]
        th = struct.unpack_from('<Q', dump, i + 16)[0]
        nh = struct.unpack_from('<Q', dump, i + 24)[0]
        if (0x80000000 <= victim <= 0x84000000 and bc <= 65536
                and 0 <= th <= STREAM_END + 4096 and 0 <= nh <= STREAM_END + 4096
                and th != 0):
            hits.append((i, victim, bc, th, nh))

    print(f'{len(hits)} candidate clusters (victim, byte_count, this_header, next_header):')
    for pos, victim, bc, th, nh in hits[:30]:
        print(f'  dump+0x{pos:x} (phys 0x{0x80000000 + pos:08x}): '
              f'victim=0x{victim:x} bc={bc} this={th} next={nh}')
        # also show state u32 and nearby fields
        st = struct.unpack_from('<I', dump, pos + 32)[0]
        print(f'    state-ish u32 @ +32: {st}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
