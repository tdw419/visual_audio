#!/usr/bin/env python3
"""Compare the full-boot memory dump's initrd region against the source gzip.

The dump is a linear (physical) image: word 0 = guest phys ram_base
(0x80000000 for the alpine boot). The initrd was written at physical
0x82000000 (offset 0x2000000 in the dump).

If the region matches initrd.gz.bin byte-for-byte, the kernel's page tables /
linear-map VA translation must be delivering different bytes (MMU/TLB bug) —
OR the kernel copied the initrd elsewhere and reads from that copy.
If it differs, something overwrote 0x82000000 during early boot.

Usage: python3 compare_fullboot_initrd.py [dump.bin]
"""
import sys
from pathlib import Path

RAM_BASE = 0x80000000
INITRD_PHYS = 0x82800000
INITRD_OFFSET = INITRD_PHYS - RAM_BASE
GZ = Path(__file__).parent / 'initrd.gz.bin'


def main():
    dump_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / 'fullboot_dump.bin'
    if not dump_path.exists():
        print(f"ERROR: dump not found at {dump_path}")
        return 1
    if not GZ.exists():
        print(f"ERROR: initrd.gz.bin not found at {GZ}")
        return 1

    gz = GZ.read_bytes()
    dump = dump_path.read_bytes()

    print(f"dump size: {len(dump):,} bytes")
    print(f"initrd.gz.bin: {len(gz):,} bytes")
    print(f"initrd region in dump: 0x{INITRD_PHYS:016x} + {len(gz):,} bytes")

    if INITRD_OFFSET + len(gz) > len(dump):
        print(f"ERROR: initrd region extends past dump end")
        return 1

    region = dump[INITRD_OFFSET:INITRD_OFFSET + len(gz)]

    # byte-by-byte comparison
    diffs = [i for i, (a, b) in enumerate(zip(region, gz)) if a != b]

    if not diffs:
        print("RESULT: initrd region MATCHES source byte-for-byte")
        print("=> kernel's MMU/TLB linear-map translation delivers wrong bytes,")
        print("   or the kernel reads from a relocated copy. Page-walk the")
        print("   kernel's VA for phys 0x82000000 vs QEMU.")
        return 0

    n = len(diffs)
    pct = 100.0 * n / len(gz)
    print(f"RESULT: {n:,} differing bytes ({pct:.2f}%)")
    print(f"first 16 diffs:")
    for i in diffs[:16]:
        print(f"  +0x{i:x} (phys 0x{INITRD_PHYS + i:x}): dump=0x{region[i]:02x} source=0x{gz[i]:02x}")

    # characterize: all-zero? all-same? random?
    nonzero = sum(1 for b in region if b != 0)
    print(f"  dump region nonzero bytes: {nonzero:,}/{len(region):,}")
    # check if the region looks like it was zeroed
    if nonzero == 0:
        print("  => region is ALL ZEROS (someone zeroed it — memblock allocator?)")
    # check if it looks like a shifted copy
    import collections
    first = gz[:64]
    if first in region:
        print(f"  => source prefix found at dump offset 0x{region.index(first):x} (shifted copy?)")

    return 1


if __name__ == '__main__':
    sys.exit(main())
