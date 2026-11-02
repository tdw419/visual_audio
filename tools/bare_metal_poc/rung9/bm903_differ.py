#!/usr/bin/env python3
"""BM903 step 1: differ — executed handoff vs the BM902 constructed artifact.

Shaped from bm902_differ.py (that file is LOCKED and untouched; this is a copy
whose BASELINE moved from the oracle dumps to BM902's own artifacts, which is
the strictest available bar: bm902_zp.bin already differs from the oracle at
every whitelisted offset we chose, so comparing against it re-checks our
loader's choices instead of re-checking the oracle against itself).

Legs:
  L1 zeropage  — byte diff vs bm902_zp.bin; any differing offset outside
                 (BM902 whitelist UNION addendum whitelist) FAILS, naming it.
  L2 cmdline   — must be byte-identical to bm902_cmdline.bin, all 512 B.
  L2b initrd   — the constructed ramdisk_image/size must equal the values the
                 layout declares (proves the two whitelisted bytes carry OUR
                 numbers, not a lucky zero).
  L3 registers — every register in the oracle table must match, INCLUDING rsp
                 (BM902 whitelisted rsp; our stage2 lands it exactly, so this
                 differ is stricter than the one it replaces).

Usage: bm903_differ.py <zp.bin> <cmdline.bin> <regs.json> [--expect-fail]
Exit 0 green / 1 red. --expect-fail inverts (RED legs L5).
"""
import json
import re
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE_ZP = HERE / 'bm902_zp.bin'
BASE_CMDLINE = HERE / 'bm902_cmdline.bin'
PLAN = HERE / 'BM902_FIELD_PLAN.md'
ADDENDUM = HERE / 'BM903_FIELD_PLAN_ADDENDUM.md'
LAYOUT = HERE / 'bm903_layout.json'

ORACLE_REGS = {
    'rip': 0x100000, 'rax': 0x100000, 'rbx': 0, 'rcx': 0, 'rdx': 0,
    'rsi': 0x13ab0, 'rdi': 0, 'rbp': 0, 'rsp': 0x1f784,
    'r8': 0, 'r9': 0, 'r10': 0, 'r11': 0, 'r12': 0, 'r13': 0,
    'r14': 0, 'r15': 0,
    'eflags': 0x46, 'cs': 0x10, 'ss': 0x18, 'ds': 0x18, 'es': 0x18,
    'cr0': 0x11, 'cr3': 0x0, 'cr4': 0x0,
}


def first_block(text: str) -> str:
    m = re.search(r'```\n(.*?)```', text, re.S)
    assert m, 'no fenced whitelist block found'
    return m.group(1)


def parse_offsets(text: str) -> set:
    """Same grammar the BM902 differ uses: bands/offsets, INCLUSIVE."""
    offsets = set()
    for line in first_block(text).splitlines():
        line = line.split('#')[0].strip()
        if not line:
            continue
        pm = re.match(r'^(0x[0-9a-fA-F]+)\s*-\s*(0x[0-9a-fA-F]+)', line)
        if pm:
            lo, hi = int(pm.group(1), 16), int(pm.group(2), 16)
            assert hi >= lo, f'bad band {line}'
            offsets.update(range(lo, hi + 1))
            continue
        ps = re.match(r'^(0x[0-9a-fA-F]+)\b', line)
        if ps:
            offsets.add(int(ps.group(1), 16))
    return offsets


def main() -> int:
    argv = [a for a in sys.argv[1:] if a != '--expect-fail']
    invert = '--expect-fail' in sys.argv[1:]
    zp_path, cmd_path, regs_path = Path(argv[0]), Path(argv[1]), Path(argv[2])

    plan = PLAN.read_text()
    add = ADDENDUM.read_text()
    wl_plan = parse_offsets(plan)
    wl_add = parse_offsets(add)
    wl = wl_plan | wl_add
    # non-vacuity of the addendum: it may only re-license, never widen
    new = sorted(wl_add - wl_plan)
    if new:
        print(f'ADDENDUM FAIL: addendum whitelists {len(new)} offset(s) the '
              f'BM902 plan does not: ' + ', '.join(f'0x{o:x}' for o in new[:20]))
        return 1
    # BM902's own differ adds the 0x000-0x1e7 STAGE2-CHOICE band unconditionally;
    # the plan's block already lists it, so the union is identical either way.
    assert 0x000 in wl and 0x1e7 in wl, 'whitelist lost the STAGE2-CHOICE band'

    fails = []

    # ---- L1: zeropage vs BM902's constructed artifact ----
    ours = zp_path.read_bytes()
    base = BASE_ZP.read_bytes()
    assert len(ours) == len(base) == 4096, 'zeropage size'
    diffs = [i for i in range(4096) if ours[i] != base[i]]
    outside = [i for i in diffs if i not in wl]
    if outside:
        fails.append(f'L1 FAIL: {len(outside)} zeropage diff(s) vs {BASE_ZP.name} '
                     f'outside whitelist: ' + ', '.join(f'0x{i:x}' for i in outside[:20]))
    else:
        print(f'L1 PASS: {len(diffs)} zeropage byte(s) differ from '
              f'{BASE_ZP.name}, all inside the whitelist union '
              f'({len(wl)} offsets): ' +
              (', '.join(f'0x{i:x}' for i in diffs) or 'none'))

    # ---- L2: cmdline ----
    ours_cmd = cmd_path.read_bytes()
    base_cmd = BASE_CMDLINE.read_bytes()
    if ours_cmd != base_cmd:
        first = next((i for i in range(512) if ours_cmd[i] != base_cmd[i]), None)
        fails.append(f'L2 FAIL: cmdline differs from {BASE_CMDLINE.name} '
                     f'at byte {first}')
    else:
        s = base_cmd.split(b'\0', 1)[0]
        print(f'L2 PASS: cmdline byte-identical all 512 B ({len(s)} chars)')

    # ---- L2b: the constructed initrd pair carries OUR layout numbers ----
    lay = json.loads(LAYOUT.read_text())
    img = struct.unpack_from('<I', ours, 0x218)[0]
    size = struct.unpack_from('<I', ours, 0x21c)[0]
    if (img, size) != (lay['initrd_addr'], lay['initrd_bytes']):
        fails.append(f'L2b FAIL: ramdisk_image/size = {img:#x}/{size:#x}, '
                     f'layout says {lay["initrd_addr"]:#x}/{lay["initrd_bytes"]:#x}')
    else:
        print(f'L2b PASS: ramdisk_image={img:#x} ramdisk_size={size:#x} '
              f'== bm903_layout.json (constructed, not copied)')

    # ---- L3: registers (rsp included: stricter than BM902) ----
    regs = json.loads(regs_path.read_text())
    for name, want in ORACLE_REGS.items():
        got = regs.get(name)
        if got != want:
            fails.append(f'L3 FAIL: reg {name} = '
                         f'{got if got is None else hex(got)} want {hex(want)}')
    if not any(f.startswith('L3') for f in fails):
        print(f'L3 PASS: all {len(ORACLE_REGS)} registers match the oracle, '
              f'including rsp={hex(regs.get("rsp"))} (BM902 whitelisted it)')

    if fails:
        for f in fails:
            print(f)
        if invert:
            print('RED LEG OK: differ exited non-zero as required')
            return 0
        return 1
    if invert:
        print('RED LEG FAIL: mutated artifact still compared EQUAL — the '
              'differ is decoration')
        return 1
    print('BM903 DIFFER PASS: L1+L2+L2b+L3 green')
    return 0


if __name__ == '__main__':
    sys.exit(main())
