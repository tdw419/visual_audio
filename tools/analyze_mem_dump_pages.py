#!/usr/bin/env python3
"""Full-page-match presence map: which file pages exist ANYWHERE in the dump.

For each 4096-byte file page, probes are searched at ALL occurrences and a page
counts as present only if a FULL-page byte-identical match is found. Reports the
per-file presence frontier — the last file with any content in the dump, which
bounds where the cpio parser stopped extracting.

Usage: python3 tools/analyze_mem_dump_pages.py DUMP.bin
"""
import gzip
import json
import re
import sys
import time
from pathlib import Path

LNX = '/home/jericho/projects/zion/apps/linux/alpine/alpine-riscv64.lnx.bin'
ENTRIES = '/tmp/ref_cpio_entries.json'
PAGE = 4096


def load_ref() -> bytes:
    data = Path(LNX).read_bytes()
    for m in re.finditer(b'\x1f\x8b\x08', data):
        off = m.start()
        if off > 0x1000000:
            return gzip.decompress(data[off:off + 5400000])
    raise SystemExit('no initrd gzip found')


def full_page_match(dump, seg):
    tried = 0
    for poff in (0, 128, 256, 512, 1024, 2048, 3072):
        if poff + 64 > len(seg):
            continue
        probe = seg[poff:poff + 64]
        if sum(1 for b in probe if b) < 8:
            continue
        s = 0
        while tried < 12:
            pos = dump.find(probe, s)
            if pos < 0:
                break
            tried += 1
            base = pos - poff
            if base >= 0 and dump[base:base + len(seg)] == seg:
                return True
            s = pos + 1
    return False


def main() -> int:
    t0 = time.time()
    dump = Path(sys.argv[1]).read_bytes()
    ref = load_ref()
    entries = json.load(open(ENTRIES))
    print(f'dump: {len(dump):,} bytes; ref: {len(ref):,} bytes; entries: {len(entries)}')

    files = [(e['pos'], e['name'], e['data_start'], e['size']) for e in entries if e['size'] > 0]

    last_present = -1
    report = []
    for fi, (epos, name, data_start, size) in enumerate(files):
        n_pages = (size + PAGE - 1) // PAGE
        present = 0
        first_missing = None
        for p in range(n_pages):
            seg = ref[data_start + p * PAGE:data_start + min((p + 1) * PAGE, size)]
            if full_page_match(dump, seg):
                present += 1
            elif first_missing is None:
                first_missing = p * PAGE
        if present:
            last_present = fi
        report.append((fi, name, size, n_pages, present, first_missing))

    for fi, name, size, npg, pres, fm in report:
        flag = 'FULL' if pres == npg else ('PART' if pres else '----')
        print(f'{fi:>3} {flag} {name:<50} {size:>9} pages {pres:>3}/{npg}')
        if pres and pres != npg:
            print(f'       first missing at file offset {fm}')

    print()
    print(f'extraction frontier: last file with any page present = index {last_present} '
          f'({files[last_present][1] if last_present >= 0 else "none"}, stream {files[last_present][2]:,})')
    print(f'elapsed {time.time() - t0:.1f}s')
    return 0


if __name__ == '__main__':
    sys.exit(main())
