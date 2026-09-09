#!/usr/bin/env python3
"""Build a truncated initrd: reference decompressed cpio cut at entry K's end.

The kernel's cpio parser runs do_reset's alignment check at every entry
boundary (state Reset after SkipIt). Truncating the reference stream at a
clean entry boundary (then re-gzipping so it's a valid gzip) exercises the
parser through exactly K entries; if the parser mis-executes on entry K's
header math, the run reports "broken padding" — bisecting K finds the failing
entry.

Usage: python3 tools/make_truncated_initrd.py K out_path
"""
import gzip
import json
import re
import sys
from pathlib import Path

LNX = '/home/jericho/projects/zion/apps/linux/alpine/alpine-riscv64.lnx.bin'
ENTRIES = '/tmp/ref_cpio_entries.json'


def main() -> int:
    k = int(sys.argv[1])
    out = Path(sys.argv[2])

    data = Path(LNX).read_bytes()
    ref = None
    for m in re.finditer(b'\x1f\x8b\x08', data):
        off = m.start()
        if off > 0x1000000:
            ref = gzip.decompress(data[off:off + 5400000])
            break
    if ref is None:
        print('no initrd found')
        return 1

    entries = json.load(open(ENTRIES))
    if k < 0 or k >= len(entries):
        print(f'K must be 0..{len(entries) - 1}')
        return 1

    cut = entries[k]['next']
    truncated = ref[:cut]
    while len(truncated) % 4:
        truncated += b'\x00'
    gz = gzip.compress(truncated, compresslevel=9)
    out.write_bytes(gz)
    print(f'entry {k}: {entries[k]["name"]} (size {entries[k]["size"]})')
    print(f'truncated at stream offset {cut:,} -> {len(truncated):,} bytes cpio, '
          f'{len(gz):,} bytes gzip -> {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
