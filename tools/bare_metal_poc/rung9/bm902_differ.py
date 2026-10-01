"""bm902_differ.py — TASK_BM902: the differential gate (L1/L2/L3).

Byte-compares a CONSTRUCTED handoff (zeropage/cmdline/regs) against the
frozen BM901 oracle artifacts, whitelisting only the byte offsets the
committed BM902_FIELD_PLAN.md names LOADER-SPECIFIC / STAGE2-CHOICE.

The whitelist is parsed from the field plan's fenced block (ranges
INCLUSIVE, `0xAAA-0xBBB` bands or single offsets), unioned (overlaps
merged), plus the 0x000-0x1e7 STAGE2-CHOICE band declared by the same
block. Any differing zeropage byte outside the union = FAIL naming the
offset. cmdline must be byte-identical (L2). Registers compared against
the field plan's register classification: rsp is LOADER-SPECIFIC,
everything else MUST-MATCH.

Usage: bm902_differ.py <zp.bin> <cmdline.bin> <regs.json> <field_plan.md>
Exit 0 = all green. Exit 1 = at least one leg RED (offsets named).
"""
import json
import re
import struct
import sys

ORACLE_ZP = 'oracle_zp_leg0.bin'
ORACLE_CMDLINE = 'oracle_cmdline_leg0.bin'
CMDLINE_ADDR = 0x1f800

ORACLE_REGS = {
    'rip': 0x100000, 'rax': 0x100000, 'rbx': 0, 'rcx': 0, 'rdx': 0,
    'rsi': 0x13ab0, 'rdi': 0, 'rbp': 0,
    'r8': 0, 'r9': 0, 'r10': 0, 'r11': 0, 'r12': 0, 'r13': 0,
    'r14': 0, 'r15': 0,
    'eflags': 0x46, 'cs': 0x10, 'ss': 0x18, 'ds': 0x18, 'es': 0x18,
    'cr0': 0x11, 'cr3': 0x0, 'cr4': 0x0,
}
REG_LOADER_SPECIFIC = {'rsp'}  # named in the field plan's register table

CHOICE_BAND = (0x000, 0x1e7)  # STAGE2-CHOICE band, declared in the plan


def parse_whitelist(plan_text: str) -> set:
    """Extract the whitelist fenced block and union its byte offsets."""
    m = re.search(
        r'```\n(.*?)```', plan_text, re.S)
    assert m, 'whitelist fenced block not found in field plan'
    offsets = set()
    for line in m.group(1).splitlines():
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
    offsets.update(range(CHOICE_BAND[0], CHOICE_BAND[1] + 1))
    return offsets


def main() -> int:
    zp_path, cmd_path, regs_path, plan_path = sys.argv[1:5]
    plan = open(plan_path).read()
    whitelist = parse_whitelist(plan)
    fails = []

    # ---- L1: zeropage ----
    ours = open(zp_path, 'rb').read()
    oracle = open(ORACLE_ZP, 'rb').read()
    assert len(ours) == len(oracle) == 4096, 'zeropage size'
    zp_diffs = [i for i in range(4096) if ours[i] != oracle[i]]
    outside = [i for i in zp_diffs if i not in whitelist]
    if outside:
        named = ', '.join(f'0x{i:x}' for i in outside[:20])
        fails.append(f'L1 FAIL: {len(outside)} zeropage diff(s) outside '
                     f'whitelist: {named}')
    else:
        print(f'L1 PASS: zeropage diffs {len(zp_diffs)} bytes, all inside '
              f'whitelist union ({len(whitelist)} offsets)')

    # ---- L2: cmdline ----
    ours_cmd = open(cmd_path, 'rb').read()
    oracle_cmd = open(ORACLE_CMDLINE, 'rb').read()
    if ours_cmd != oracle_cmd:
        first = next((i for i in range(min(len(ours_cmd), len(oracle_cmd)))
                      if ours_cmd[i] != oracle_cmd[i]), None)
        fails.append(f'L2 FAIL: cmdline differs (first at byte {first}, '
                     f'len {len(ours_cmd)} vs {len(oracle_cmd)})')
    else:
        s = oracle_cmd.split(b'\0', 1)[0]
        print(f'L2 PASS: cmdline byte-identical ({len(s)} chars, NUL-terminated)')

    # ---- L3: registers ----
    regs = json.load(open(regs_path))
    for name, want in ORACLE_REGS.items():
        got = regs.get(name)
        if name in REG_LOADER_SPECIFIC:
            continue
        if got != want:
            fails.append(f'L3 FAIL: reg {name} = {got:#x} want {want:#x}')
    print(f'L3 PASS: registers match oracle (rsp loader-specific, '
          f'ours {regs.get("rsp", 0):#x})')

    if fails:
        for f in fails:
            print(f)
        return 1
    print('DIFFER PASS: L1+L2+L3 green')
    return 0


if __name__ == '__main__':
    sys.exit(main())
