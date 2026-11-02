#!/usr/bin/env python3
"""BM802: name the three live bytes in the setup header, so the map's 10% row is
explained by a mechanism and not by a guess.

The sweep measured setup-header (payload 0x1f1..0x268, the window
bm903_stage2_px.asm:183 copies into the zero page) at 3 fatal in 30 samples.
Which bytes, and why only those, comes from the loader itself: grep its
`mov dword [ZP_ADDR + ...]` writes and you get the set of fields the handoff
RE-PINS from its own constants. Those cannot be reached by a medium fault,
because the loader overwrites whatever arrived. The rest of the window is
copied verbatim from the medium, and the kernel reads what it reads.

So the test here is: for each fatal offset, is it inside the re-pinned set (it
must NOT be -- that would mean the sweep misattributed it), and what value does
the medium actually carry there?

  usage: python3 bm802_header_fields.py
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNG9 = HERE.parent / 'rung9'
sys.path.insert(0, str(HERE))
from bm802_fixture import FAULT        # noqa: E402  the sweep's fault value
ROWS = HERE / 'bm802_sweep_rows.txt'
HEADER_REGION = 'setup-header'
CENSUS_REGION = 'setup-header-census'
sys.path.insert(0, str(RUNG9))
import bm903_pxcodec as codec          # noqa: E402

# fields stage2 overwrites after the copy, from its own source, with widths
PIN_SRC = (RUNG9 / 'bm903_stage2_px.asm').read_text()
PINNED = {}
for m in re.finditer(r'mov\s+(byte|word|dword)\s+\[ZP_ADDR\s*\+\s*(0x[0-9A-Fa-f]+)\],\s*([-\w]+)',
                     PIN_SRC):
    width, off, val = m.group(1), int(m.group(2), 0), m.group(3)
    n = {'byte': 1, 'word': 2, 'dword': 4}[width]
    PINNED[off] = (width, n, val)

ZP_LO, ZP_HI = 0x1f1, 0x268
_m = re.search(r'mov\s+ecx,\s*(0x[0-9A-Fa-f]+)\s*-\s*(0x[0-9A-Fa-f]+)', PIN_SRC, re.I)
COPY_HI, COPY_LO = int(_m.group(1), 0), int(_m.group(2), 0)

# Field names for the fatal bytes come from the kernel's own boot header. That
# mapping is not asserted on memory -- three of these offsets hold values only
# the kernel puts there (PINS below), and they lock the tail layout the naming
# depends on. If a pin ever stops holding, this script says so instead of
# naming a field it can no longer justify.
LAYOUT = [(0x202, 4, "header magic 'HdrS'"),
          (0x206, 2, 'version'),
          (0x210, 1, 'type_of_loader'),
          (0x211, 1, 'loadflags'),
          (0x214, 4, 'code32_start'),
          (0x218, 4, 'ramdisk_image'),
          (0x21C, 4, 'ramdisk_size'),
          (0x228, 4, 'cmd_line_ptr'),
          (0x22C, 4, 'initrd_addr_max'),
          (0x230, 4, 'kernel_alignment'),
          (0x234, 1, 'relocatable_kernel'),
          (0x238, 2, 'cmdline_size'),
          (0x23C, 4, 'hardware_subarch'),
          (0x240, 8, 'hardware_subarch_data'),
          (0x248, 4, 'payload_offset'),
          (0x24C, 4, 'payload_length'),
          (0x250, 8, 'setup_data'),
          (0x258, 8, 'pref_address'),
          (0x260, 4, 'init_size'),
          (0x264, 4, 'handover_offset')]
PINS = {0x202: 0x53726448,                # 'HdrS'
        0x22C: 0x7FFFFFFF,                # x86-64 initrd_addr_max
        0x238: 2047}                      # cmdline_size for protocol >= 2.08
_WIDTH = {lo: size for lo, size, _n in LAYOUT}


def field_of(offset):
    for lo, size, name in LAYOUT:
        if lo <= offset < lo + size:
            return f'{name} ({size} B at {lo:#x}), byte {offset - lo}'
    return 'not a named field of the boot header'


def check_pins(hdr):
    bad = []
    for o, want in PINS.items():
        got = int.from_bytes(hdr[o:o + _WIDTH[o]], 'little')
        if got != want:
            bad.append('%#x reads %#x, not %#x' % (o, got, want))
    align = int.from_bytes(hdr[0x230:0x234], 'little')
    if not (align >= 0x10000 and align & (align - 1) == 0):
        bad.append('0x230 kernel_alignment %#x is not a power of 2 >= 64 KiB' % align)
    return bad


def main() -> int:
    payload = codec.build_payload()[0]
    hdr = payload[:16384]
    assert (COPY_LO, COPY_HI) == (ZP_LO, ZP_HI), \
        f'stage2 copies {COPY_HI - COPY_LO} B from {COPY_LO:#x} to {COPY_HI:#x}, ' \
        f'not the {ZP_HI - ZP_LO} B window sampled at {ZP_LO:#x}..{ZP_HI:#x}'
    rows = [json.loads(ln) for ln in ROWS.read_text().splitlines() if ln.startswith('{')]
    # The census region, once it exists, covers the bytes the 4-byte stride
    # skipped; both are the same window, so the fatal set is their union.
    regions = [d for d in rows if d['region'] in (HEADER_REGION, CENSUS_REGION)
               and d['phase'] == 'map']
    assert regions, f'no {HEADER_REGION} rows in {ROWS.name} -- run the sweep first'
    fatal = sorted(d['payload_off'] for d in regions if d['verdict'] != 'INERT')
    sampled = len({d['payload_off'] for d in regions})
    print(f'{HEADER_REGION}+census: {sampled} of {ZP_HI - ZP_LO} window bytes booted, '
          f'{len(fatal)} fatal '
          f'({", ".join(hex(o) for o in fatal)})')
    bad = check_pins(hdr)
    print('layout pins ' + ('HOLD' if not bad else 'BROKEN: ' + '; '.join(bad)) +
          ' -- HdrS at 0x202, initrd_addr_max=0x7FFFFFFF at 0x22C, '
          'cmdline_size=2047 at 0x238, kernel_alignment a power of 2 at 0x230. '
          'They are what license the field names below.')
    rc = int(bool(bad))
    print(f'\nwindow: payload {COPY_LO:#x}..{COPY_HI:#x} ({COPY_HI - COPY_LO} B) copied to the '
          f'zero page; stage2 re-pins {len(PINNED)} fields inside it:')
    for off in sorted(PINNED):
        w, n, val = PINNED[off]
        inside = 'inside ' if ZP_LO <= off < ZP_HI else 'OUTSIDE'
        print(f'  {off:#05x} {w:5} <- {val:14} ({inside} the sampled window)')
    print('\nthe fatal offsets, against the re-pinned set:')
    for o in fatal:
        pinned = any(other <= o < other + n for other, (_w, n, _v) in PINNED.items())
        rc |= int(pinned)
        fld = next((x for x in LAYOUT if x[0] <= o < x[0] + x[1]), None)
        if fld:
            lo, size, name = fld
            clean = int.from_bytes(hdr[lo:lo + size], 'little')
            after = list(hdr[lo:lo + size])
            after[o - lo] ^= FAULT
            hurt = int.from_bytes(bytes(after), 'little')
            what = (f'{name} ({size} B at {lo:#x}) byte {o - lo}: '
                    f'{clean:#x} -> {hurt:#x}')
        else:
            what = f'no named field here: byte reads {hdr[o]:#04x}'
        print(f'  {o:#05x}  re-pinned by the loader? {pinned}  {what}')
    magic = [o for o in fatal if 0x202 <= o <= 0x205]
    print(f'\nHdrS magic bytes 0x202..0x205 = {hdr[0x202:0x206]!r}: the sweep hit '
          f'{[hex(o) for o in magic] or "none of them"}.')
    print('rc=0 means no fatal offset fell inside a field the loader overwrites: the fatal '
          'bytes are reachable by design, not a misattribution of the fixture.')
    return rc


if __name__ == '__main__':
    sys.exit(main())
