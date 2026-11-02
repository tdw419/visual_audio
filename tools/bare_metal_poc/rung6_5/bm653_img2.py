#!/usr/bin/env python3
"""BM653 build half: BM651's four executed images REUSED, plus one new leg.

`rung6_5/bm651_img2.asm` is this lane's own landed artifact and BM651's gate
asserts its four variant CRCs against `evidence/img2_variants.txt`. Option C's
claim is about where the image's BYTES CAME FROM, not about the image, so the
reuse has to be proven rather than stated:

  * the four variants are reassembled here, from the unchanged source, and each
    crc32/nid is compared against the landed evidence file. A variant that
    drifted would make BM653's green leg a different experiment than BM651's;
  * the contract offsets are parsed out of BOTH texts -- the forked loader and
    the image -- with rung6_5's own `equs()` imported, not re-typed, and the
    build refuses if they disagree;
  * one named, round-tripping delta adds the fifth image: the SCRIBBLER. It
    keeps every word of the contract (banner, echo, mailbox) and, in between,
    writes four bytes into the kernel header band the loader is about to copy
    into the zero page. That is the leg the row cannot skip: it says what
    BM651's receipt already conceded -- the contract is a LIVENESS promise, not
    a sandbox -- and it can only be shown on a base where the handoff is still
    pending after the image returns, which is precisely what option C is.

  usage: python3 bm653_img2.py        # writes img2_<variant>.bin + the asm fork
"""
import subprocess
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bm651_img2 as bm651                                          # noqa: E402
import bm653_construct as bm653_construct                           # noqa: E402

SRC = HERE / 'bm651_img2.asm'
INC = HERE / 'bm653_px_layout.inc'
EVID = HERE / 'evidence' / 'img2_variants.txt'
FORKED = HERE / 'bm653_img2_scribbler.asm'
LOADER = HERE / 'bm653_stage2_px.asm'

VARIANTS = bm651.VARIANTS                      # green / noecho / nombox / halt
IMG2_LEN = bm651.IMG2_LEN

# one delta, on the proven text: the scribble lands after the echo and before
# the contract word, so the image still returns having kept both checks.
SCRIBBLE = ('the scribbler: contract kept, machine poisoned',
            """%ifndef NO_MAILBOX
    mov word [es:bx+ARG_MBOX], MAILBOX     ; "I finished", per the contract
%endif""",
            """%ifdef SCRIBBLE
    ; Between the echo and the contract word: four bytes into the kernel
    ; header band at linear 0x201f1, which is exactly the band
    ; bm602_stage2_px.asm copies into the zero page AFTER this image returns
    ; (mov esi, HDR_SCRATCH+0x1f1 / mov ecx, 0x268-0x1f1). Nothing here is a
    ; bug or a crash: the image does what the contract asks and also writes
    ; where it was never promised it could not.
    push ax
    push ds
    mov ax, 0x2000                 ; 0x2000:0x1f1 == linear 0x201f1
    mov ds, ax
    mov dword [0x1f1], 0xDEADBEEF
    pop ds
    pop ax
%endif

%ifndef NO_MAILBOX
    mov word [es:bx+ARG_MBOX], MAILBOX     ; "I finished", per the contract
%endif""")


def build(src, flags, out):
    r = subprocess.run(['nasm', '-f', 'bin', str(src), *flags, '-o', str(out)],
                       capture_output=True, text=True)
    if r.returncode or r.stderr.strip():
        raise SystemExit(f'nasm {src} {flags} failed:\n{r.stdout}{r.stderr}')
    b = Path(out).read_bytes()
    assert len(b) == IMG2_LEN, f'{out}: {len(b)} B, want {IMG2_LEN}'
    crc = zlib.crc32(b) & 0xFFFFFFFF
    return b, crc, bm651.nid_of(crc)


def landed_record():
    """The four variant crc/nid pairs BM651 landed, parsed out of its evidence."""
    out = {}
    for line in EVID.read_text().splitlines():
        f = line.split()
        # BM651's own print: `<variant> 2048 B crc32=<hex> exec_nid=<hex>`.
        # The record is matched by its SHAPE, not by line number, so a summary
        # line that happens to sit at the top cannot pass for a variant.
        if len(f) == 5 and f[1] == '2048' and f[2] == 'B' \
           and f[3].startswith('crc32=') and f[4].startswith('exec_nid='):
            out[f[0]] = (f[3].split('=')[1], f[4].split('=')[1])
    assert set(out) == set(VARIANTS), \
        f'evidence/{EVID.name} names {sorted(out)}, want {sorted(VARIANTS)}'
    return out


def main() -> int:
    fails = []
    # 1. the contract is text, checked across the two sources that share it.
    # The loader's geometry arrives as %define from the generated .inc, so the
    # same parser BM653's construct stage uses seeds equs(): one source for
    # both, and an .inc that stopped carrying a define fails here rather than
    # assembling a loader that reads the wrong group.
    known = bm653_construct.consts(INC.read_text())
    loader = bm651.equs(LOADER, known)
    image = bm651.equs(SRC)
    for name in ('ARG_NID', 'ARG_MBOX', 'ARG_ECHO'):
        if loader.get(name) != image.get(name) or name not in loader:
            fails.append(f'contract drift on {name}: loader {loader.get(name)} '
                         f'image {image.get(name)}')
    if loader.get('EXEC_MAILBOX') != image.get('MAILBOX'):
        fails.append(f'mailbox word: loader {loader.get("EXEC_MAILBOX")} '
                     f'image {image.get("MAILBOX")}')
    # R-SCOPE-7: the block sits at the TOP of the group window, not above the
    # image -- so the check is that it is inside the group and clear of an
    # image the group could hold, not that it clears two image windows.
    gb = known['PX_GROUP_BYTES']
    if not (loader['IMG2_LEN'] <= loader.get('EXEC_ARGS', 0) <= gb - 14):
        fails.append(f'EXEC_ARGS={loader.get("EXEC_ARGS")} is not inside the '
                     f'group window above a {loader["IMG2_LEN"]} B image')
    if loader.get('IMG2_SEG') != known['IMG2_DST'] // 16:
        fails.append(f'IMG2_SEG={loader.get("IMG2_SEG")} is not the paragraph '
                     f'the sub-image table hands the walk ({known["IMG2_DST"]:#x})')

    # 2. BM651's four variants, from its unchanged source, against its evidence
    want = landed_record()
    got = {}
    for variant, flags in VARIANTS.items():
        _, crc, nid = build(SRC, flags, HERE / f'img2_{variant}.bin')
        got[variant] = (f'{crc:08X}', f'{nid:04X}')
        if got[variant] != want[variant]:
            fails.append(f'{variant}: rebuilt {got[variant]}, landed '
                         f'{want[variant]} -- BM653 would not be running BM651\'s image')

    # 3. the fifth image, by one named delta that round-trips
    src = SRC.read_text()
    n = src.count(SCRIBBLE[1])
    assert n == 1, f'scribbler delta matched {n} times in {SRC.name}'
    fork = src.replace(SCRIBBLE[1], SCRIBBLE[2], 1)
    assert fork.replace(SCRIBBLE[2], SCRIBBLE[1], 1) == src, \
        'the scribbler delta is not invertible'
    FORKED.write_text(fork)
    _, crc, nid = build(FORKED, ['-DSCRIBBLE'], HERE / 'img2_scribbler.bin')
    got['scribbler'] = (f'{crc:08X}', f'{nid:04X}')
    dupes = sorted({c for c, _ in got.values()
                    if [x[0] for x in got.values()].count(c) > 1})
    if dupes:
        fails.append(f'images collide: {dupes}')
    # the scribbler is a contract-keeping image, and that has to be checked in
    # the BYTES rather than asserted in a comment: the one instruction that
    # writes the mailbox word must still be there, still name the offsets the
    # loader writes into the arg block, and the banner string it prints must be
    # the same string. The encoding is derived from the parsed equates, so an
    # ARG_MBOX or MAILBOX that moved fails here instead of assembling a leg
    # that silently stops meaning what its name says.
    scr = (HERE / 'img2_scribbler.bin').read_bytes()
    grn = (HERE / 'img2_green.bin').read_bytes()
    assert len(scr) == len(grn) == IMG2_LEN
    contract = bytes([0x26, 0xC7, 0x47, image['ARG_MBOX']]) \
        + image['MAILBOX'].to_bytes(2, 'little')
    # ; mov word [es:bx+ARG_MBOX], MAILBOX -- ES prefix, C7 /0 with a word imm
    banner = b'IMG2EXEC BANNER NID='
    for label, img in (('green', grn), ('scribbler', scr)):
        if img.count(contract) != 1:
            fails.append(f'{label}: the mailbox-store instruction {contract.hex()} '
                         f'appears {img.count(contract)} times, not once')
        if img.count(banner) != 1:
            fails.append(f'{label}: banner string {banner!r} found '
                         f'{img.count(banner)} times')
    # 120 differing bytes, which is not 18 and needs saying out loud: the
    # scribble itself is 18 bytes of code, every relative branch after it is
    # re-encoded for the shifted target, and everything below the insertion
    # moves. A "same except for the scribble" claim would be false here; what
    # is true, and what the leg needs, is that both images keep the contract.
    nd = sum(1 for a, b in zip(scr, grn) if a != b)
    if nd == 0:
        fails.append('the scribbler is byte-identical to green: -DSCRIBBLE did nothing')
    if scr[:9] != grn[:9]:
        fails.append('the scribble moved code BEFORE its own insertion point -- '
                     'the delta is not the only change in the file')

    for v, (c, i) in got.items():
        print(f'{v:10s} 2048 B  crc32={c}  exec_nid={i}'
              + ('' if v not in want else '  == landed'))
    print(f'scribbler vs green: {nd} bytes differ inside the same {IMG2_LEN} B, '
          'and the delta undoes to bm651_img2.asm byte-for-byte')
    if fails:
        for f in fails:
            print(f'[RED] {f}')
        return 1
    print(f'contract offsets agree across the two sources: '
          + ', '.join(f'{n}={loader[n]}' for n in
                      ('ARG_NID', 'ARG_MBOX', 'ARG_ECHO', 'IMG2_LEN'))
          + f', mailbox={loader["EXEC_MAILBOX"]:#06x}, '
          f'EXEC_ARGS={loader["EXEC_ARGS"]} in a {gb} B group')
    print(f'reused BM651: 4 variants, all matching evidence/{EVID.name}; '
          f'1 new leg (scribbler) from 1 named delta -> {FORKED.name}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
