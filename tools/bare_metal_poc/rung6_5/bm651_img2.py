#!/usr/bin/env python3
"""BM651 build half: assemble the four executed images, from one source.

Four builds of `bm651_img2.asm` are the row's legs:

  green        banner + echo + mailbox + retf          -> EXEC=OK
  no-echo      prints the banner, never records the NID -> EXEC=NO-BANNER
  no-mailbox   does everything except the contract word -> EXEC=BAD-MAILBOX
  halt         banners, echoes, hangs                  -> host-side TIMEOUT

The three failures are the non-vacuity proof: each is a different way for the
image to be alive but not to have kept its side of the contract, and each is
caught by a different loader check. None is a compile error or a missing
file, so the gate cannot be satisfied by an absent test.

Cross-checks, all before any boot:
  * the arg-block offsets are parsed out of BOTH sources (loader asm and image
    asm) and must agree -- the contract is verified as text, not as a comment;
  * EXEC_ARGS must sit above both image windows, or the copy-down walks over
    the block it is about to hand over;
  * every variant is exactly IMG2_LEN bytes, which the consts emitter asserts
    from the other side.

  usage: python3 bm651_img2.py            # writes img2_<variant>.bin
"""
import re
import subprocess
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
IMG2_LEN = 2048
SCALE = 65536

VARIANTS = {
    'green': [],
    'noecho': ['-DNO_ECHO'],
    'nombox': ['-DNO_MAILBOX'],
    'halt': ['-DHALT'],
}

EQU = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s+equ\s+([^;]+?)\s*(?:;.*)?$')
# deliberately narrow: identifiers, decimal/hex literals, + - * / and parens.
SAFE = re.compile(r'^[-+*/() A-Za-z0-9_]+$')
IDENT = re.compile(r'\b[A-Za-z_][A-Za-z0-9_]*\b')


def equs(path, known=None):
    """Numeric `NAME equ <expr>` table for one file, resolved to fixpoint.

    `known` seeds names that arrive on the nasm command line instead of in
    the text (IMG2_LEN). Anything still unresolved is LEFT OUT rather than
    guessed at, so a caller that needs a name asserts on its presence.
    """
    raw = dict(known or {})
    for line in path.read_text().splitlines():
        m = EQU.match(line)
        if m:
            raw.setdefault(m.group(1), m.group(2))
    out = dict(raw)
    for _ in range(len(raw) + 1):
        changed = False
        for name, expr in list(out.items()):
            if isinstance(expr, int):
                continue
            assert SAFE.match(expr), f'{name}: unsupported equ text {expr!r}'
            ids = set(IDENT.findall(expr))
            if ids and not all(isinstance(out.get(i), int) for i in ids):
                continue
            sub = expr
            for i in sorted(ids, key=len, reverse=True):
                sub = re.sub(rf'\b{i}\b', str(out[i]), sub)
            out[name] = int(eval(sub, {'__builtins__': {}}, {}))  # SAFE-gated
            changed = True
        if not changed:
            break
    return {k: v for k, v in out.items() if isinstance(v, int)}


def nid_of(crc):
    return ((crc & 0xFFFF) ^ (crc >> 16)) & 0xFFFF


def main() -> int:
    loader = equs(HERE / 'bm651_stage2.asm', {'IMG2_LEN': IMG2_LEN})
    image = equs(HERE / 'bm651_img2.asm')

    fails = []
    shared = ['ARG_NID', 'ARG_MBOX', 'ARG_ECHO']
    for name in shared:
        if name not in loader or name not in image:
            fails.append(f'{name} missing from '
                         f"{'bm651_stage2.asm' if name not in loader else 'bm651_img2.asm'}")
        elif loader[name] != image[name]:
            fails.append(f'contract drift: {name} = {loader[name]} in the loader '
                         f'but {image[name]} in the image')
    if 'EXEC_MAILBOX' not in loader or 'MAILBOX' not in image:
        fails.append('mailbox word equ missing from one of the two sources')
    elif loader['EXEC_MAILBOX'] != image['MAILBOX']:
        fails.append(f"mailbox word drift: {loader['EXEC_MAILBOX']:#06x} vs "
                     f"{image['MAILBOX']:#06x}")
    if 'EXEC_ARGS' not in loader:
        fails.append('EXEC_ARGS not resolvable out of bm651_stage2.asm')
    elif loader['EXEC_ARGS'] < 2 * IMG2_LEN:
        fails.append(f"EXEC_ARGS={loader['EXEC_ARGS']} lies inside the copy-down "
                     f'windows [0,{2 * IMG2_LEN}): the block gets clobbered')

    for variant, flags in VARIANTS.items():
        out = HERE / f'img2_{variant}.bin'
        subprocess.run(['nasm', '-f', 'bin', str(HERE / 'bm651_img2.asm'),
                        *flags, '-o', str(out)], check=True)
        b = out.read_bytes()
        if len(b) != IMG2_LEN:
            fails.append(f'{variant}: {len(b)} B != {IMG2_LEN} B')
            continue
        crc = zlib.crc32(b) & 0xFFFFFFFF
        print(f'{variant:8s} {len(b):5d} B  crc32={crc:08X}  exec_nid={nid_of(crc):04X}')

    # distinct images, or a "failure" leg is the green leg under another name.
    crcs = {v: zlib.crc32((HERE / f'img2_{v}.bin').read_bytes()) & 0xFFFFFFFF
            for v in VARIANTS}
    dupes = sorted({f'{c:08X}' for c in crcs.values()
                    if list(crcs.values()).count(c) > 1})
    if dupes:
        fails.append(f'variant images collide: {dupes}')

    if fails:
        for f in fails:
            print(f'[RED] {f}')
        return 1
    print('contract offsets agree in both sources: '
          + ', '.join(f'{n}={loader[n]}' for n in shared)
          + f", mailbox={loader['EXEC_MAILBOX']:#06x}")
    print(f"EXEC_ARGS={loader['EXEC_ARGS']} >= {2 * IMG2_LEN}: above both "
          'image windows, out of reach of the copy-down')
    return 0


if __name__ == '__main__':
    sys.exit(main())
