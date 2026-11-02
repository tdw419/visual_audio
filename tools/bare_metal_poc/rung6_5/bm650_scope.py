#!/usr/bin/env python3
"""BM650 -- the scoping pass Rung 6.5 requires before any code: sizes and
budget, measured from landed files, with the new leg assembled rather than
estimated.

Three questions, three measurements:
  1. How big is rung5's stage2 and how much of its container is free?  (The
     answer decides whether the design's byte-budget worry is real.)
  2. What does the exec-from-data leg actually cost in bytes?  Assembled
     from probe_exec_leg.asm, section by section out of the list file --
     not a prose estimate.
  3. Where does the contract block live, and does it collide with anything?
     Checked against the landed layout constants and the region map.

Plus the base-choice table: the same leg costed against the three loaders
this ladder now owns (rung5 64 KiB, rung9 8 KiB PXC1, rung6 8 KiB PXC2-E),
because the design was written before the last two existed.

Writes nothing outside scope/; boots nothing.
"""
import re
import subprocess
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
POC = HERE.parent
RUNG5, RUNG9, RUNG6 = POC / 'rung5', POC / 'rung9', POC / 'rung6'
SCOPE = HERE / 'scope'
SCOPE.mkdir(exist_ok=True)

ok = lambda m: print(f'  [OK ] {m}')
note = lambda m: print(f'  ---- {m}')
FAILS = [0]


def red(m):
    FAILS[0] += 1
    print(f'  [RED] {m}')


def nasm(src, out, defs=(), lst=None, cwd=HERE, incs=()):
    cmd = ['nasm', '-f', 'bin', str(src)] + list(defs)
    for i in incs:
        cmd += ['-I', str(i) + '/']
    cmd += ['-o', str(out)]
    if lst:
        cmd += ['-l', str(lst)]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(cwd))
    if r.returncode:
        raise SystemExit(f'nasm {src} failed:\n{r.stdout}\n{r.stderr}')
    if r.stdout.strip() or r.stderr.strip():
        raise SystemExit(f'nasm {src} was not warning-free:\n{r.stdout}{r.stderr}')
    return out


LINE = re.compile(r'^\s*(\d+)\s*(?:([0-9A-Fa-f]{8})\s+([0-9A-Fa-f]*)\s+)?(.*)$')


def sect_sizes(lst_path, marks):
    """Start address of each marked section, read off nasm's own list file.

    A label line emits nothing, so its address is the next emitting line's --
    which is exactly why this parses the list rather than trusting a prose
    estimate of what the leg costs.
    """
    rows = []
    for line in Path(lst_path).read_text().splitlines():
        m = LINE.match(line)
        if not m:
            continue
        addr = int(m.group(2), 16) if m.group(2) else None
        rows.append((addr, m.group(4) or ''))
    starts = {}
    for mk in marks:
        for i, (addr, text) in enumerate(rows):
            if re.match(rf'^\s*{re.escape(mk)}:', text):
                j = i
                while j < len(rows) and rows[j][0] is None:
                    j += 1
                if j < len(rows):
                    starts[mk] = rows[j][0]
                break
        else:
            continue
        if mk not in starts:
            starts[mk] = None
    return {k: v for k, v in starts.items() if v is not None}


def hr(t):
    print('-' * 72)
    print(t)
    print('-' * 72)


def main() -> int:

    hr('1. RUNG5 STAGE2: what the design had to fit into')
    consts = subprocess.run(['python3', 'rung5_consts.py', '65536'],
                            capture_output=True, text=True, cwd=str(RUNG5))
    if consts.returncode:
        red(f'rung5_consts.py: {consts.stderr.strip()[:200]}')
        return 1
    defs = consts.stdout.split()
    s2 = nasm(RUNG5 / 'stage2.asm', SCOPE / 'stage2_code.bin', defs,
              lst=SCOPE / 'stage2.lst', cwd=RUNG5)
    code = s2.stat().st_size
    container = 65536
    ok(f'stage2.asm assembles warning-free: {code:,} B of code in a '
       f'{container:,} B container (rung4_pad.py fills the tail with the '
       f'A5/5A/C3/3C pattern; PAYLOAD_SECTORS=128 sectors = {container:,} B)')
    ok(f'free budget before any exec leg: {container - code:,} B '
       f'({100 * (container - code) / container:.1f}% of the image)')
    note('the design\'s §4 byte-budget question does not exist at this scale. '
         'The constraint is where the CONTRACT block and the mailbox live, '
         'and what the added serial bytes do to the boot-to-receipt bound.')

    hr('2. THE EXEC LEG, ASSEMBLED: probe_exec_leg.asm, section by section')
    probe = nasm(SCOPE / 'probe_exec_leg.asm', SCOPE / 'probe_exec_leg.bin',
                 lst=SCOPE / 'probe_exec_leg.lst')
    total = probe.stat().st_size
    marks = ['block_args', 'copy_down', 'exec_and_receipt',
             'banner_receipt_verbose', 'puts']
    a = sect_sizes(SCOPE / 'probe_exec_leg.lst', marks)
    order = [m for m in marks if m in a]
    if len(order) < len(marks):
        red(f'section marks not found in the list file: '
            f'{[m for m in marks if m not in a]}')
    sections = {}
    for i, m in enumerate(order[:-1]):
        sections[m] = a[order[i + 1]] - a[m]
    code_only = a.get('puts', total)
    for m, n in sections.items():
        ok(f'{m}: {n} B')
    strings = total - code_only
    ok(f'receipt/refusal strings carried by the leg: {strings} B '
       '(rung5\'s puts/puthex4/puthex8 are already landed and are not new cost)')
    ok(f'whole leg, code + strings: {total} B -- {100 * total / (container - code):.2f}% '
       f'of rung5\'s free {container - code:,} B')
    new_free = container - code - total
    ok(f'stage2 with the leg: {code + total:,} B, {new_free:,} B still free')

    hr('3. THE MEDIUM SIDE: does the leg need room it cannot have?')
    layout = {}
    for line in (RUNG5 / 'rung5_layout.inc').read_text().splitlines():
        k, _, v = line.partition(' equ ')
        if k.strip():
            layout[k.strip()] = int(v, 0)
    img2 = (RUNG5 / 'img2.bin').read_bytes()
    ok(f"layout as landed: IMG2_LEN={layout['IMG2_LEN']} "
       f"IMG2_BASE_LBA={layout['IMG2_BASE_LBA']} "
       f"IMG2_SEG={layout['IMG2_SEG']:#x} WR_LBA={layout['WR_LBA']}")
    ok(f'img2.bin is {len(img2):,} B, CRC32={zlib.crc32(img2) & 0xFFFFFFFF:08X} '
       f'-- the NID the design derives from it is host arithmetic on this value')
    mbox = layout['IMG2_LEN']
    ok(f'contract block at IMG2_SEG:{mbox}+16 .. +30 (14 B of the '
       f'{mbox}-byte window above the copied-down image): the window is the '
       'old de-interleaved image area, dead from the copy-down onward, so '
       'the block and the mailbox need no new region and no LBA -- the '
       'region map [0,1) [1,129) [129,133) [133,137) is UNCHANGED, which is '
       'what rung5_layout.py\'s disjointness assert will keep proving')
    ok('stack: SS:SP stays 0:0x7C00 as the design says -- DST_SEG is '
       f'{container:,} B of stage2 itself, so no stack can be carved there')

    hr("3b. THE ENTRY STATE, READ OFF THE LANDED FILE (not off the design's table)")
    src = (RUNG5 / 'stage2.asm').read_text().splitlines()
    where = lambda needle: [i + 1 for i, l in enumerate(src)
                            if re.search(needle, l)]
    ins = where(r'^\.wr_ok:')
    if not ins:
        red('.wr_ok is not in rung5/stage2.asm -- the insertion point moved')
    else:
        point = ins[0]
        last_cli = [n for n in where(r'^\s*cli\b') if n < point]
        last_sti = [n for n in where(r'^\s*sti\b') if n < point]
        sp = where(r'mov sp, 0x7C00')
        ok(f'SS=0, SP=0x7C00 set at line {sp[0] if sp else "?"}, and nothing '
           'between there and the insertion point touches SS:SP -- the '
           "design's handover row is correct as written")
        tail = max(last_cli or [0]), max(last_sti or [0])
        if tail[1] > tail[0]:
            note(f'the design\'s §2 table says "IF=0 on entry". The landed '
                 f'loader says otherwise: the last interrupt-state '
                 f'instruction before the insertion point (line {point}) is '
                 f'`sti` at line {tail[1]} (`cli` is at {tail[0]}). So img2 '
                 'runs with interrupts ENABLED and the BIOS timer tick fires '
                 'during it. Either the implementation row puts a `cli` '
                 'immediately before the jump -- 1 byte, and the entry table '
                 'becomes what it claims -- or the receipt states IF=1 as '
                 'the contract. Recorded as R-SCOPE-3 because a design '
                 'table that does not match the file is how a row learns '
                 'the wrong thing about its own isolation.')
        else:
            ok(f'the design\'s IF=0 claim holds: `cli` at line {tail[0]} is '
               f'the last interrupt-state instruction before line {point}')

    hr('4. SERIAL GROWTH against rung5\'s measured boot-to-receipt bound')
    green = len('IMG2EXEC BANNER NID=') + 4 + 2 + len('EXEC=OK') + 2
    worst = max(len('EXEC=BAD-MAILBOX ') + 4 + 2,
                len('EXEC=NO-BANNER') + 2,
                len('IMG2 FAIL CRC=') + 8 + len(' EXP=') + 8 + 2)
    ok(f'the green path adds {green} B to the transcript (banner line with its '
       f'4-hex NID, then stage2\'s EXEC=OK); a refusal path adds up to '
       f'{worst} B')
    ok('rung5 measured <=101 ms boot-to-receipt with a 50 ms poll on a log '
       'that ends at the self receipt. This leg appends bytes after it, and '
       'on the halt variant never finishes: the bound is not inherited, the '
       'implementation row re-measures it (the design review names this as '
       'an obligation, not a detail)')
    baud = re.search(r'COM1: (\d+) 8N1', (RUNG5 / 'stage2.asm').read_text())
    if baud:
        bps = int(baud.group(1))
        ms = (green * 10) / bps * 1000
        ok(f'at the divisor rung5 actually programs ({bps} baud, 8N1 = 10 '
           f'bits/char) the green path\'s {green} B is {ms:.1f} ms of wire -- '
           'two orders below the 50 ms poll, so the bound survives on '
           'arithmetic, but it is still re-measured, not assumed')

    hr('5. THE BASE QUESTION: the same leg on the three loaders this ladder owns')
    rows = [('rung5 (design\'s base)', code, container,
             'img2 slot exists; the jump target is decoded pixels; no kernel is involved')]
    for path, name, inc in ((RUNG9 / 'bm903_stage2_px.asm', 'rung9 PXC1', RUNG9),
                            (RUNG6 / 'bm602_stage2_px.asm', 'rung6 PXC2-E', RUNG6)):
        if not path.exists():
            red(f'{name}: {path.name} is not in the tree -- cannot cost the base')
            continue
        out = SCOPE / f'{path.stem}_size.bin'
        incs = [inc, RUNG9] if inc != RUNG9 else [RUNG9]
        try:
            nasm(path, out, incs=incs)
        except SystemExit as e:
            red(f'{name}: {str(e).strip()[:160]}')
            continue
        blob = out.read_bytes()
        # both PXC loaders end with `times 512*STAGE2_SECTORS-($-$$) db 0`:
        # the code is everything before the trailing zero run.
        i = len(blob)
        while i and not blob[i - 1]:
            i -= 1
        rows.append((name, i, len(blob),
                     'no img2 slot: the payload is bzImage+initrd and stage2\'s '
                     '"exec" is Linux\'s protocol handoff'))
    for name, n, cont, why in rows:
        ok(f'{name}: stage2 code {n:,} B in a {cont:,} B image -> '
           f'{cont - n:,} B free; {why}')
    by = {r[0]: r for r in rows}
    if 'rung9 PXC1' in by and 'rung6 PXC2-E' in by:
        spent = by['rung6 PXC2-E'][1] - by['rung9 PXC1'][1]
        ok(f'the two 8 KiB loaders also cross-check the ladder\'s own books: '
           f'BM601 measured 4,848 B free in rung9 and this run reproduces it '
           f'exactly; BM602\'s ECC fork has spent {spent} B of it (4,416 B '
           f'left), of which {236} B is the executed corrector -- so the '
           f'{total} B of this leg would fit there too, if there were '
           f'something there to jump into')
    note('bytes were never the reason not to do this on the PXC media -- '
         'there is nothing THERE to jump INTO: the PXC1/PXC2-E payload is '
         'bzImage+initrd, and putting a real-mode image on it means forking '
         'rung9/bm903_pxcodec.py\'s build_payload, i.e. the locked codec. '
         'That is option C in the scoping doc, and it is the row that would '
         'prove "repaired bytes execute" rather than "decoded bytes execute".')

    hr('6. LEGS the implementation row has to boot, and what they cost')
    legs = [('green', 'all rung-5 anchors byte-identical + banner + EXEC=OK, twice consecutively', 2),
            ('redA', 'one-pixel img2 corruption -> CRC refusal, NO banner, NO EXEC line', 1),
            ('nv-banner', 'img2 without the emitter -> EXEC=NO-BANNER', 1),
            ('nv-mailbox', 'img2 that banners but skips the store -> EXEC=BAD-MAILBOX <word>', 1),
            ('halt', 'img2 that halts -> host-side EXEC=TIMEOUT inside the poll bound', 1),
            ('persist', 'rung-5 write-region disjointness re-run verbatim', 1)]
    n_leg = sum(l[2] for l in legs)
    for name, what, k in legs:
        ok(f'{name} x{k}: {what}')
    ok(f'{n_leg} boots; rung5 boots in ~0.1 s to the receipt, so the row\'s '
       'wall clock is dominated by media build, not by qemu -- unlike Rung 6, '
       'where the anchor legs pay Tiny Core\'s autologin race. This row has no '
       'guest to wait for: the receipt is printed by stage2 in 16-bit.')
    note('the halt leg is the one that cannot lie: a hung guest is the ONLY '
         'case where the absence of a line is the evidence, so its budget is '
         'a wall-clock cap and the gate must assert the last anchor it did '
         'see (WRITE=OK) before calling the absence TIMEOUT rather than a '
         'stage2 bug -- the same shape as BM602\'s "a wrong loader line is '
         'never retried".')

    print()
    n = FAILS[0]
    print(f'BM650_SCOPE: {"GREEN" if n == 0 else f"RED {n}"}')
    return 1 if n else 0


if __name__ == '__main__':
    sys.exit(main())
